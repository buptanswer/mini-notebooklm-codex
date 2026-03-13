from __future__ import annotations

import argparse
import json
import mimetypes
import shutil
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUTS_ROOT = PROJECT_ROOT / "test_inputs"
DEFAULT_STORAGE_ROOT = PROJECT_ROOT / "storage"


@dataclass(slots=True)
class Stage1Summary:
    storage_ready: bool
    database_ready: bool
    qdrant_ready: bool
    warnings: list[str]


@dataclass(slots=True)
class PipelineJobsSummary:
    total_jobs: int
    parse_jobs: int
    enrich_jobs: int
    chunk_jobs: int
    index_jobs: int
    failed_jobs: int


@dataclass(slots=True)
class Stage2DocumentSummary:
    source_filename: str
    source_relative_path: str
    review_status: str
    parser_warning_count: int
    unknown_block_count: int
    parsing_status: str
    ir_exists: bool
    enriched_ir_exists: bool
    content_list_exists: bool
    layout_exists: bool
    origin_pdf_exists: bool
    image_block_count: int
    table_block_count: int
    equation_block_count: int
    image_vlm_coverage: float | None
    table_summary_coverage: float | None


@dataclass(slots=True)
class Stage3Summary:
    document_count: int
    parent_chunk_count: int
    child_chunk_count: int
    qdrant_points: int
    all_chunking_completed: bool
    all_indexing_completed: bool


@dataclass(slots=True)
class Stage4QuestionSummary:
    question: str
    answer_preview: str
    source_count: int
    retrieval_trace_count: int
    expected_source_filename: str
    first_source_filename: str | None
    answer_contains_expected_hint: bool
    source_has_anchor_blocks: bool


@dataclass(slots=True)
class Stage4StreamSummary:
    question: str
    event_names: list[str]
    delta_event_count: int
    answer_preview: str
    source_count: int
    retrieval_trace_count: int
    answer_contains_expected_hint: bool


@dataclass(slots=True)
class Stage5FileManagementSummary:
    renamed_knowledge_base_name: str
    deleted_temp_knowledge_base_id: str
    moved_document_relative_path: str
    deleted_document_id: str
    renamed_folder_path: str
    bulk_deleted_count: int
    deleted_folder_document_count: int
    remaining_document_count: int
    qa_after_management_ok: bool


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage5 full end-to-end validation runner")
    parser.add_argument(
        "--knowledge-base-name",
        default="Stage5 全流程验收样本",
        help="Knowledge base name created for the clean run",
    )
    parser.add_argument(
        "--inputs-root",
        type=Path,
        default=DEFAULT_INPUTS_ROOT,
        help="Directory containing sample inputs",
    )
    parser.add_argument(
        "--poll-timeout-seconds",
        type=int,
        default=3600,
        help="Maximum time to wait for background ingestion jobs",
    )
    args = parser.parse_args()

    clean_storage(DEFAULT_STORAGE_ROOT)

    from fastapi.testclient import TestClient

    from app.core.config import get_settings
    from app.main import app
    from app.writers import write_json

    settings = get_settings()
    run_root = settings.storage_root / "stage5_runs" / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_root.mkdir(parents=True, exist_ok=True)

    upload_entries = collect_upload_entries(args.inputs_root)
    expected_file_count = len(upload_entries)

    with TestClient(app) as client:
        stage1 = verify_stage1(client)
        knowledge_base = create_knowledge_base(client, args.knowledge_base_name)
        upload_payload = upload_entries_to_request(upload_entries)
        try:
            upload_response = client.post(
                f"/api/v1/knowledge-bases/{knowledge_base['id']}/upload",
                files=upload_payload["files"],
                data=upload_payload["data"],
            )
        finally:
            close_file_handles(upload_payload["handles"])
        upload_response.raise_for_status()
        upload_result = upload_response.json()
        if upload_result["accepted_files"] != expected_file_count:
            raise ValueError(
                f"expected {expected_file_count} uploaded files, got {upload_result['accepted_files']}"
            )

        documents, jobs = poll_until_complete(
            client=client,
            knowledge_base_id=knowledge_base["id"],
            expected_file_count=expected_file_count,
            timeout_seconds=args.poll_timeout_seconds,
        )

        pipeline_jobs = verify_pipeline_jobs(jobs, expected_file_count)
        stage2_docs = verify_stage2(documents)
        stage3 = verify_stage3(client, documents, settings)
        stage4_questions = verify_stage4(client, knowledge_base["id"])
        stage4_stream = verify_stage4_stream(client, knowledge_base["id"])
        stage5 = verify_stage5_file_management(
            client=client,
            knowledge_base=knowledge_base,
            documents=documents,
        )

    summary = {
        "generated_at": datetime.now().isoformat(),
        "knowledge_base": knowledge_base,
        "uploaded_files": [relative_path for _, relative_path in upload_entries],
        "job_count": len(jobs),
        "pipeline_jobs": asdict(pipeline_jobs),
        "stage1": asdict(stage1),
        "stage2": [asdict(item) for item in stage2_docs],
        "stage3": asdict(stage3),
        "stage4": [asdict(item) for item in stage4_questions],
        "stage4_stream": asdict(stage4_stream),
        "stage5": asdict(stage5),
    }
    summary_path = write_json(run_root / "summary.json", summary)
    print(f"[stage5] summary -> {summary_path}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def clean_storage(storage_root: Path) -> None:
    storage_root.mkdir(parents=True, exist_ok=True)
    for folder_name in (
        "knowledge_bases",
        "qdrant",
        "sqlite",
        "stage2_runs",
        "stage3_runs",
        "stage4_runs",
        "stage5_runs",
    ):
        target = storage_root / folder_name
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        (target / ".gitkeep").touch(exist_ok=True)

    legacy_db = storage_root / "app.db"
    if legacy_db.exists():
        legacy_db.unlink()
    (storage_root / ".gitkeep").touch(exist_ok=True)


def collect_upload_entries(inputs_root: Path) -> list[tuple[Path, str]]:
    root_files = [
        inputs_root / "sample.pdf",
        inputs_root / "sample.pptx",
        inputs_root / "sample.docx",
    ]
    image_files = sorted((inputs_root / "sampleJPG").glob("*.jpg"))
    entries: list[tuple[Path, str]] = []
    for path in root_files:
        if not path.exists():
            raise FileNotFoundError(path)
        entries.append((path, path.name))
    if not image_files:
        raise FileNotFoundError(inputs_root / "sampleJPG")
    for path in image_files:
        entries.append((path, f"sampleJPG/{path.name}"))
    return entries


def upload_entries_to_request(entries: list[tuple[Path, str]]) -> dict[str, Any]:
    files = []
    relative_paths: list[str] = []
    handles = []
    for path, relative_path in entries:
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        handle = path.open("rb")
        handles.append(handle)
        files.append(("files", (path.name, handle, mime_type)))
        relative_paths.append(relative_path)
    return {"files": files, "data": {"relative_paths": relative_paths}, "handles": handles}


def close_file_handles(handles: list[Any]) -> None:
    for handle in handles:
        handle.close()


def verify_stage1(client) -> Stage1Summary:
    response = client.get("/api/v1/system/overview")
    response.raise_for_status()
    payload = response.json()
    bootstrap = payload["bootstrap"]
    if not bootstrap["storage_ready"] or not bootstrap["database_ready"] or not bootstrap["qdrant_ready"]:
        raise ValueError(f"bootstrap not ready: {bootstrap}")
    return Stage1Summary(
        storage_ready=bootstrap["storage_ready"],
        database_ready=bootstrap["database_ready"],
        qdrant_ready=bootstrap["qdrant_ready"],
        warnings=list(bootstrap["warnings"]),
    )


def create_knowledge_base(client, knowledge_base_name: str) -> dict[str, Any]:
    response = client.post(
        "/api/v1/knowledge-bases",
        json={
            "name": knowledge_base_name,
            "description": "Stage5 从零开始的完整验收样本",
        },
    )
    response.raise_for_status()
    return response.json()


def poll_until_complete(
    *,
    client,
    knowledge_base_id: str,
    expected_file_count: int,
    timeout_seconds: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    deadline = time.monotonic() + timeout_seconds
    last_documents: list[dict[str, Any]] = []
    last_jobs: list[dict[str, Any]] = []

    while time.monotonic() < deadline:
        documents_response = client.get(f"/api/v1/knowledge-bases/{knowledge_base_id}/documents")
        jobs_response = client.get(f"/api/v1/knowledge-bases/{knowledge_base_id}/jobs")
        documents_response.raise_for_status()
        jobs_response.raise_for_status()

        last_documents = documents_response.json()
        last_jobs = jobs_response.json()
        running_jobs = [job for job in last_jobs if job["state"] in {"pending", "running"}]

        if len(last_documents) == expected_file_count and not running_jobs:
            failed_jobs = [job for job in last_jobs if job["state"] == "failed"]
            if failed_jobs:
                raise ValueError(f"pipeline has failed jobs: {failed_jobs}")
            return last_documents, last_jobs

        time.sleep(5)

    raise TimeoutError(
        f"pipeline did not finish within {timeout_seconds}s; "
        f"documents={len(last_documents)} jobs={len(last_jobs)}"
    )


def verify_pipeline_jobs(jobs: list[dict[str, Any]], expected_file_count: int) -> PipelineJobsSummary:
    parse_jobs = [job for job in jobs if job["stage"] == "parse"]
    enrich_jobs = [job for job in jobs if job["stage"] == "enrich"]
    chunk_jobs = [job for job in jobs if job["stage"] == "chunk"]
    index_jobs = [job for job in jobs if job["stage"] == "index"]
    failed_jobs = [job for job in jobs if job["state"] == "failed"]

    stage_map = {
        "parse": parse_jobs,
        "enrich": enrich_jobs,
        "chunk": chunk_jobs,
        "index": index_jobs,
    }
    for stage_name, stage_jobs in stage_map.items():
        if len(stage_jobs) != expected_file_count:
            raise ValueError(
                f"expected {expected_file_count} `{stage_name}` jobs, got {len(stage_jobs)}"
            )
        incomplete = [job["id"] for job in stage_jobs if job["state"] != "completed"]
        if incomplete:
            raise ValueError(f"{stage_name} jobs not completed: {incomplete}")

    return PipelineJobsSummary(
        total_jobs=len(jobs),
        parse_jobs=len(parse_jobs),
        enrich_jobs=len(enrich_jobs),
        chunk_jobs=len(chunk_jobs),
        index_jobs=len(index_jobs),
        failed_jobs=len(failed_jobs),
    )


def verify_stage2(documents: list[dict[str, Any]]) -> list[Stage2DocumentSummary]:
    summaries: list[Stage2DocumentSummary] = []
    for document in documents:
        ir_path = Path(document["ir_path"])
        enriched_ir_path = Path(document["enriched_ir_path"])
        bundle_root = Path(document["bundle_root"])
        content_list_path = bundle_root / "content_list_v2.json"
        layout_path = bundle_root / "layout.json"
        origin_pdf_path = Path(document["origin_pdf_path"])

        if document["parsing_status"] != "completed":
            raise ValueError(f"document parse not completed: {document['source_filename']}")
        if not ir_path.exists():
            raise FileNotFoundError(ir_path)
        if not enriched_ir_path.exists():
            raise FileNotFoundError(enriched_ir_path)
        if not content_list_path.exists():
            raise FileNotFoundError(content_list_path)
        if not layout_path.exists():
            raise FileNotFoundError(layout_path)
        if not origin_pdf_path.exists():
            raise FileNotFoundError(origin_pdf_path)

        ir_payload = json.loads(ir_path.read_text(encoding="utf-8"))
        enriched_payload = json.loads(enriched_ir_path.read_text(encoding="utf-8"))
        warnings = ir_payload.get("quality", {}).get("parser_warnings", [])
        unknown_blocks = [block for block in ir_payload.get("blocks", []) if block.get("type") == "unknown"]
        if warnings:
            raise ValueError(f"unexpected parser warnings in {document['source_filename']}: {warnings}")
        if unknown_blocks:
            raise ValueError(f"unexpected unknown blocks in {document['source_filename']}")
        if len(ir_payload.get("blocks", [])) != len(enriched_payload.get("blocks", [])):
            raise ValueError(f"block count changed unexpectedly in {document['source_filename']}")

        image_block_count = 0
        table_block_count = 0
        equation_block_count = 0
        for block in enriched_payload.get("blocks", []):
            block_type = block.get("type")
            if block_type == "image":
                image_block_count += 1
            elif block_type == "table":
                table_block_count += 1
            elif block_type == "equation":
                equation_block_count += 1

            if block_type in {"image", "table", "equation"}:
                enrichment = block.get("enrichment")
                if not enrichment:
                    raise ValueError(
                        f"block `{block.get('block_id')}` in {document['source_filename']} missing enrichment"
                    )
                if not (enrichment.get("embedding_text") or "").strip():
                    raise ValueError(
                        f"block `{block.get('block_id')}` in {document['source_filename']} missing embedding_text"
                    )

        quality = enriched_payload.get("quality", {})
        summaries.append(
            Stage2DocumentSummary(
                source_filename=document["source_filename"],
                source_relative_path=document["source_relative_path"],
                review_status=document["review_status"],
                parser_warning_count=document["parser_warning_count"],
                unknown_block_count=document["unknown_block_count"],
                parsing_status=document["parsing_status"],
                ir_exists=True,
                enriched_ir_exists=True,
                content_list_exists=True,
                layout_exists=True,
                origin_pdf_exists=True,
                image_block_count=image_block_count,
                table_block_count=table_block_count,
                equation_block_count=equation_block_count,
                image_vlm_coverage=quality.get("image_vlm_coverage"),
                table_summary_coverage=quality.get("table_summary_coverage"),
            )
        )
    return summaries


def verify_stage3(client, documents: list[dict[str, Any]], settings) -> Stage3Summary:
    all_chunking_completed = all(document["chunking_status"] == "completed" for document in documents)
    all_indexing_completed = all(document["indexing_status"] == "completed" for document in documents)
    if not all_chunking_completed or not all_indexing_completed:
        raise ValueError("stage3 indexing is not complete for all documents")

    parent_chunk_count = sum(int(document["parent_chunk_count"]) for document in documents)
    child_chunk_count = sum(int(document["child_chunk_count"]) for document in documents)
    if parent_chunk_count <= 0 or child_chunk_count <= 0:
        raise ValueError("stage3 chunk counts should be positive")

    qdrant_manager = client.app.state.qdrant_manager
    qdrant_points = qdrant_manager.client.count(
        collection_name=settings.qdrant_collection,
        exact=True,
    ).count

    if qdrant_points != child_chunk_count:
        raise ValueError(
            f"qdrant/doc mismatch: qdrant_points={qdrant_points}, child_chunk_count={child_chunk_count}"
        )

    return Stage3Summary(
        document_count=len(documents),
        parent_chunk_count=parent_chunk_count,
        child_chunk_count=child_chunk_count,
        qdrant_points=qdrant_points,
        all_chunking_completed=all_chunking_completed,
        all_indexing_completed=all_indexing_completed,
    )


def verify_stage4(client, knowledge_base_id: str) -> list[Stage4QuestionSummary]:
    expectations = [
        (
            "智能推荐测试样本PPT用于什么测试？",
            "sample.pptx",
            "文件解析能力测试",
        ),
        (
            "这个Word模板的指导教师是什么？",
            "sample.docx",
            "某某某",
        ),
    ]
    summaries: list[Stage4QuestionSummary] = []
    for question, expected_source_filename, expected_hint in expectations:
        response = client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/ask",
            json={"question": question},
        )
        response.raise_for_status()
        payload = response.json()
        if not payload["answer"].strip():
            raise ValueError(f"empty answer for question: {question}")
        if not payload["sources"]:
            raise ValueError(f"no sources returned for question: {question}")
        if not payload["retrieval_trace"]:
            raise ValueError(f"no retrieval trace returned for question: {question}")

        first_source = payload["sources"][0]
        if first_source["source_filename"] != expected_source_filename:
            raise ValueError(
                f"unexpected first source for `{question}`: {first_source['source_filename']}"
            )

        answer_contains_expected_hint = expected_hint in payload["answer"]
        if not answer_contains_expected_hint:
            raise ValueError(
                f"answer for `{question}` missing expected hint `{expected_hint}`"
            )

        summaries.append(
            Stage4QuestionSummary(
                question=question,
                answer_preview=payload["answer"][:240],
                source_count=len(payload["sources"]),
                retrieval_trace_count=len(payload["retrieval_trace"]),
                expected_source_filename=expected_source_filename,
                first_source_filename=first_source["source_filename"],
                answer_contains_expected_hint=answer_contains_expected_hint,
                source_has_anchor_blocks=bool(first_source["anchor_blocks"]),
            )
        )
    return summaries


def verify_stage4_stream(client, knowledge_base_id: str) -> Stage4StreamSummary:
    question = "智能推荐测试样本PPT用于什么测试？"
    expected_hint = "文件解析能力测试"
    with client.stream(
        "POST",
        f"/api/v1/knowledge-bases/{knowledge_base_id}/ask/stream",
        json={"question": question},
    ) as response:
        response.raise_for_status()
        raw_payload = "".join(response.iter_text())

    events = parse_sse_events(raw_payload)
    event_names = [event["event"] for event in events]
    if "meta" not in event_names or "done" not in event_names:
        raise ValueError(f"unexpected SSE event sequence: {event_names}")

    meta_event = next(event for event in events if event["event"] == "meta")
    done_event = next(event for event in events if event["event"] == "done")
    delta_events = [event for event in events if event["event"] == "delta"]
    done_payload = done_event["payload"]
    if not delta_events:
        raise ValueError("stream response does not contain delta events")
    if expected_hint not in done_payload["answer"]:
        raise ValueError("stream final answer missing expected hint")
    if not meta_event["payload"]["sources"]:
        raise ValueError("stream meta event missing sources")
    if not done_payload["retrieval_trace"]:
        raise ValueError("stream done event missing retrieval trace")

    return Stage4StreamSummary(
        question=question,
        event_names=event_names,
        delta_event_count=len(delta_events),
        answer_preview=done_payload["answer"][:240],
        source_count=len(done_payload["sources"]),
        retrieval_trace_count=len(done_payload["retrieval_trace"]),
        answer_contains_expected_hint=expected_hint in done_payload["answer"],
    )


def verify_stage5_file_management(
    *,
    client,
    knowledge_base: dict[str, Any],
    documents: list[dict[str, Any]],
) -> Stage5FileManagementSummary:
    knowledge_base_id = knowledge_base["id"]
    renamed_name = f"{knowledge_base['name']}-已重命名"
    rename_kb_response = client.patch(
        f"/api/v1/knowledge-bases/{knowledge_base_id}",
        json={
            "name": renamed_name,
            "description": "Stage5 文件管理与流式问答验收",
        },
    )
    rename_kb_response.raise_for_status()
    renamed_kb = rename_kb_response.json()
    if renamed_kb["name"] != renamed_name:
        raise ValueError("knowledge base rename failed")

    documents_by_path = {item["source_relative_path"]: item for item in documents}
    target_document = documents_by_path.get("sample.pdf")
    if target_document is None:
        raise ValueError("sample.pdf not found for document move test")
    old_source_path = Path(target_document["source_path"])
    moved_document_response = client.patch(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{target_document['id']}",
        json={
            "new_name": "sample-renamed.pdf",
            "new_parent_path": "验收归档",
        },
    )
    moved_document_response.raise_for_status()
    moved_document = moved_document_response.json()
    moved_document_relative_path = moved_document["source_relative_path"]
    moved_source_path = Path(moved_document["source_path"])
    if moved_document_relative_path != "验收归档/sample-renamed.pdf":
        raise ValueError(f"unexpected moved path: {moved_document_relative_path}")
    if old_source_path.exists():
        raise ValueError(f"old source path still exists after move: {old_source_path}")
    if not moved_source_path.exists():
        raise FileNotFoundError(moved_source_path)

    delete_document_response = client.delete(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{target_document['id']}"
    )
    delete_document_response.raise_for_status()
    if moved_source_path.exists():
        raise ValueError(f"moved source path still exists after delete: {moved_source_path}")

    rename_folder_response = client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/folders/rename",
        json={
            "folder_path": "sampleJPG",
            "new_folder_path": "图像样本/批次A",
        },
    )
    rename_folder_response.raise_for_status()
    renamed_folder_path = "图像样本/批次A"

    refreshed_documents = client.get(f"/api/v1/knowledge-bases/{knowledge_base_id}/documents")
    refreshed_documents.raise_for_status()
    remaining_documents = refreshed_documents.json()
    renamed_folder_docs = [
        item
        for item in remaining_documents
        if item["source_relative_path"].startswith(f"{renamed_folder_path}/")
    ]
    if not renamed_folder_docs:
        raise ValueError("renamed folder documents not found")

    bulk_deleted_targets = renamed_folder_docs[:2]
    bulk_delete_response = client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/bulk-delete",
        json={"document_ids": [item["id"] for item in bulk_deleted_targets]},
    )
    bulk_delete_response.raise_for_status()
    bulk_delete_payload = bulk_delete_response.json()
    if bulk_delete_payload["deleted_count"] != len(bulk_deleted_targets):
        raise ValueError("bulk delete did not delete expected document count")

    delete_folder_response = client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/folders/delete",
        json={"folder_path": renamed_folder_path},
    )
    delete_folder_response.raise_for_status()
    delete_folder_payload = delete_folder_response.json()
    expected_folder_delete_count = len(renamed_folder_docs) - len(bulk_deleted_targets)
    if delete_folder_payload["deleted_count"] != expected_folder_delete_count:
        raise ValueError(
            "folder delete count mismatch: "
            f"expected {expected_folder_delete_count}, got {delete_folder_payload['deleted_count']}"
        )

    final_documents_response = client.get(f"/api/v1/knowledge-bases/{knowledge_base_id}/documents")
    final_documents_response.raise_for_status()
    final_documents = final_documents_response.json()
    if any(
        item["source_relative_path"].startswith(f"{renamed_folder_path}/")
        for item in final_documents
    ):
        raise ValueError("folder delete did not remove all folder documents")

    qa_after_management_response = client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/ask",
        json={"question": "这个Word模板的指导教师是什么？"},
    )
    qa_after_management_response.raise_for_status()
    qa_after_management_payload = qa_after_management_response.json()
    qa_after_management_ok = "某某某" in qa_after_management_payload["answer"]
    if not qa_after_management_ok:
        raise ValueError("QA degraded after file management operations")

    temp_knowledge_base = create_knowledge_base(client, "Stage5 待删除知识库")
    temp_storage_root = Path(temp_knowledge_base["storage_root"])
    delete_temp_kb_response = client.delete(f"/api/v1/knowledge-bases/{temp_knowledge_base['id']}")
    delete_temp_kb_response.raise_for_status()
    if temp_storage_root.exists():
        raise ValueError(f"temporary knowledge base root still exists: {temp_storage_root}")

    return Stage5FileManagementSummary(
        renamed_knowledge_base_name=renamed_name,
        deleted_temp_knowledge_base_id=temp_knowledge_base["id"],
        moved_document_relative_path=moved_document_relative_path,
        deleted_document_id=target_document["id"],
        renamed_folder_path=renamed_folder_path,
        bulk_deleted_count=bulk_delete_payload["deleted_count"],
        deleted_folder_document_count=delete_folder_payload["deleted_count"],
        remaining_document_count=len(final_documents),
        qa_after_management_ok=qa_after_management_ok,
    )


def parse_sse_events(raw_payload: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in raw_payload.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event_name = "message"
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                data_lines.append(line.removeprefix("data:").strip())
        data = "\n".join(data_lines)
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            payload = data
        events.append({"event": event_name, "payload": payload})
    return events


if __name__ == "__main__":
    main()
