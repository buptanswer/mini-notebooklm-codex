from __future__ import annotations

import argparse
from dataclasses import dataclass, asdict
from datetime import datetime

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.writers import write_json


@dataclass(slots=True)
class QuestionSummary:
    question: str
    answer_preview: str
    source_count: int
    retrieval_trace_count: int
    answer_model: str
    rerank_model: str
    embedding_model: str
    first_source_filename: str | None = None


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage4 QA smoke test")
    parser.add_argument(
        "--knowledge-base-name",
        default="Stage2 联调样本",
        help="Knowledge base name used by stage2/stage3 smoke data",
    )
    args = parser.parse_args()

    questions = [
        "智能推荐测试样本PPT用于什么测试？",
        "这个Word模板的指导教师是什么？",
    ]

    settings = get_settings()
    run_root = settings.storage_root / "stage4_runs" / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_root.mkdir(parents=True, exist_ok=True)

    summaries: list[QuestionSummary] = []
    with TestClient(app) as client:
        kb_response = client.get("/api/v1/knowledge-bases")
        kb_response.raise_for_status()
        knowledge_bases = kb_response.json()
        target = next(
            (item for item in knowledge_bases if item["name"] == args.knowledge_base_name),
            None,
        )
        if target is None:
            raise ValueError(f"knowledge base `{args.knowledge_base_name}` not found")

        knowledge_base_id = target["id"]
        for question in questions:
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

            summaries.append(
                QuestionSummary(
                    question=question,
                    answer_preview=payload["answer"][:240],
                    source_count=len(payload["sources"]),
                    retrieval_trace_count=len(payload["retrieval_trace"]),
                    answer_model=payload["answer_model"],
                    rerank_model=payload["rerank_model"],
                    embedding_model=payload["embedding_model"],
                    first_source_filename=payload["sources"][0]["source_filename"],
                )
            )

    summary_path = write_json(
        run_root / "summary.json",
        {
            "generated_at": datetime.now().isoformat(),
            "knowledge_base_name": args.knowledge_base_name,
            "questions": [asdict(item) for item in summaries],
        },
    )
    print(f"[stage4] summary -> {summary_path}")
    for item in summaries:
        print(asdict(item))


if __name__ == "__main__":
    main()
