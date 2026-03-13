from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from app.core.config import get_settings
from app.db.session import init_db, session_scope
from app.repositories.documents import DocumentRepository
from app.repositories.knowledge_bases import KnowledgeBaseRepository
from app.schemas.api import KnowledgeBaseCreateRequest
from app.services.bundle_parser import MineruBundleParser
from app.services.mineru_client import DownloadedBundle, LocalMineruFile, MineruClient
from app.services.storage import StorageManager
from app.writers import write_json


@dataclass(slots=True)
class ScenarioResult:
    scenario: str
    batch_id: str
    uploaded_files: list[str]
    bundle_zips: list[str]
    document_ir_files: list[str]
    review_statuses: list[str]


def main() -> None:
    parser = argparse.ArgumentParser(description="MinerU stage2 smoke test runner")
    parser.add_argument(
        "--inputs-root",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "test_inputs",
        help="Directory containing the sample inputs",
    )
    parser.add_argument(
        "--knowledge-base-name",
        default="Stage2 联调样本",
        help="Knowledge base name used to register smoke test documents",
    )
    args = parser.parse_args()

    settings = get_settings()
    storage_manager = StorageManager(settings)
    storage_manager.ensure_roots()
    init_db()
    run_root = (
        settings.storage_root
        / "stage2_runs"
        / datetime.now().strftime("%Y%m%d-%H%M%S")
    )
    run_root.mkdir(parents=True, exist_ok=True)
    knowledge_base = ensure_knowledge_base(args.knowledge_base_name, storage_manager)

    scenario_results: list[ScenarioResult] = []
    bundle_parser = MineruBundleParser()
    single_targets, mixed_batch_targets, image_batch_targets = collect_inputs(args.inputs_root)

    print(f"[stage2] outputs -> {run_root}")
    with MineruClient(settings=settings) as client:
        for source_file in single_targets:
            scenario_name = f"single-{source_file.stem}-{source_file.suffix.lower().lstrip('.')}"
            print(f"[stage2] upload single: {source_file.name}")
            batch_id, _ = client.submit_single_local_file(source_file)
            result = client.poll_batch(batch_id)
            scenario_results.append(
                process_batch_result(
                    scenario_name=scenario_name,
                    batch_id=batch_id,
                    files=[source_file],
                    downloads=client.download_batch_bundles(
                        result, run_root / scenario_name / "bundle_zips"
                    ),
                    bundle_parser=bundle_parser,
                    output_root=run_root / scenario_name,
                    knowledge_base_id=knowledge_base.id,
                )
            )

        for scenario_name, files in (
            ("batch-mixed", mixed_batch_targets),
            ("batch-images", image_batch_targets),
        ):
            print(f"[stage2] upload batch: {scenario_name} ({len(files)} files)")
            batch_id, prepared = client.submit_local_files(
                [LocalMineruFile(path=file_path) for file_path in files]
            )
            result = client.poll_batch(batch_id)
            scenario_results.append(
                process_batch_result(
                    scenario_name=scenario_name,
                    batch_id=batch_id,
                    files=[file.path for file in prepared],
                    downloads=client.download_batch_bundles(
                        result, run_root / scenario_name / "bundle_zips"
                    ),
                    bundle_parser=bundle_parser,
                    output_root=run_root / scenario_name,
                    knowledge_base_id=knowledge_base.id,
                )
            )

    summary_path = write_json(
        run_root / "summary.json",
        {"generated_at": datetime.now().isoformat(), "scenarios": [asdict(item) for item in scenario_results]},
    )
    print(f"[stage2] summary -> {summary_path}")


def collect_inputs(inputs_root: Path) -> tuple[list[Path], list[Path], list[Path]]:
    required = [
        inputs_root / "sample.pdf",
        inputs_root / "sample.pptx",
        inputs_root / "sample.docx",
        inputs_root / "sampleJPG" / "sample-0.jpg",
    ]
    for path in required:
        if not path.exists():
            raise FileNotFoundError(path)

    image_targets = sorted((inputs_root / "sampleJPG").glob("*.jpg"))
    if not image_targets:
        raise FileNotFoundError(inputs_root / "sampleJPG")

    return required, required, image_targets


def process_batch_result(
    scenario_name: str,
    batch_id: str,
    files: list[Path],
    downloads: list[DownloadedBundle],
    bundle_parser: MineruBundleParser,
    output_root: Path,
    knowledge_base_id: str,
) -> ScenarioResult:
    document_ir_files: list[str] = []
    bundle_zip_paths = [item.bundle_zip_path.as_posix() for item in downloads]
    review_statuses: list[str] = []

    file_by_name = {path.name: path for path in files}

    for download in downloads:
        source_path = file_by_name.get(download.file_name)
        if source_path is None:
            raise KeyError(f"missing source mapping for {download.file_name}")

        bundle_dir = bundle_parser.extract_bundle(
            download.bundle_zip_path,
            output_root / "bundles" / Path(download.bundle_zip_path).stem,
        )
        bundle_files = bundle_parser.inspect_bundle(bundle_dir)
        document_ir = bundle_parser.build_document_ir(bundle_files, source_path=source_path)
        ir_path = write_json(bundle_dir / "document_ir.json", document_ir)
        document_ir_files.append(ir_path.as_posix())
        with session_scope() as session:
            document_repository = DocumentRepository(session)
            record = document_repository.upsert_from_ir(
                knowledge_base_id=knowledge_base_id,
                source_path=source_path,
                bundle_root=bundle_dir,
                ir_path=ir_path,
                document_ir=document_ir,
            )
        review_statuses.append(record.review_status)

        print(
            json.dumps(
                {
                    "scenario": scenario_name,
                    "source": source_path.name,
                    "bundle": download.bundle_zip_path.as_posix(),
                    "document_ir": ir_path.as_posix(),
                    "review_status": record.review_status,
                    "parser_warning_count": record.parser_warning_count,
                    "unknown_block_count": record.unknown_block_count,
                },
                ensure_ascii=False,
            )
        )

    return ScenarioResult(
        scenario=scenario_name,
        batch_id=batch_id,
        uploaded_files=[path.as_posix() for path in files],
        bundle_zips=bundle_zip_paths,
        document_ir_files=document_ir_files,
        review_statuses=review_statuses,
    )


def ensure_knowledge_base(name: str, storage_manager: StorageManager):
    with session_scope() as session:
        repository = KnowledgeBaseRepository(session)
        existing = repository.get_by_name(name)
        if existing is not None:
            return existing
        return repository.create(
            payload=KnowledgeBaseCreateRequest(
                name=name,
                description="Stage2 MinerU 联调与严格模式校验样本",
            ),
            storage_manager=storage_manager,
        )


if __name__ == "__main__":
    main()
