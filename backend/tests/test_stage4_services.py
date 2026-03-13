import json
from pathlib import Path

import httpx

from app.services.chat_client import DashScopeChatClient
from app.services.qa_service import QAService
from app.services.rerank_client import DashScopeRerankClient
from app.services.retrieval_service import RetrievedCandidate
from app.repositories.chunks import ChunkSearchRecord


def test_rerank_client_parses_dashscope_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["model"] == "qwen3-rerank"
        assert payload["parameters"]["top_n"] == 2
        return httpx.Response(
            200,
            json={
                "request_id": "req-rerank-1",
                "output": {
                    "results": [
                        {"index": 1, "relevance_score": 0.92},
                        {"index": 0, "relevance_score": 0.61},
                    ]
                },
                "usage": {"total_tokens": 42},
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    rerank_client = DashScopeRerankClient(
        settings=type(
            "S",
            (),
            {
                "dashscope_api_key": "test-key",
                "dashscope_rerank_base": "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank",
                "rerank_model": "qwen3-rerank",
                "rerank_top_n": 8,
            },
        )(),
        http_client=client,
    )

    result = rerank_client.rerank(
        query="测试问题",
        documents=["a", "b"],
        top_n=2,
    )

    assert result.request_id == "req-rerank-1"
    assert result.total_tokens == 42
    assert [(item.index, item.relevance_score) for item in result.items] == [
        (1, 0.92),
        (0, 0.61),
    ]


def test_chat_client_parses_openai_compatible_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["model"] == "qwen3.5-plus"
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-123",
                "object": "chat.completion",
                "created": 1741766400,
                "model": "qwen3.5-plus",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "这是一个测试回答 [S1]",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                },
            },
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    chat_client = DashScopeChatClient(
        settings=type(
            "S",
            (),
            {
                "dashscope_api_key": "test-key",
                "dashscope_chat_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "qa_model": "qwen3.5-plus",
            },
        )(),
        http_client=client,
    )

    result = chat_client.chat(
        messages=[{"role": "system", "content": "你是助手"}, {"role": "user", "content": "你好"}]
    )

    assert result.content == "这是一个测试回答 [S1]"
    assert result.total_tokens == 120
    assert result.model == "qwen3.5-plus"


def test_qa_service_builds_source_and_multimodal_message(tmp_path: Path) -> None:
    bundle_root = tmp_path / "bundle"
    image_dir = bundle_root / "images"
    image_dir.mkdir(parents=True)
    image_path = image_dir / "sample.jpg"
    image_path.write_bytes(b"\xff\xd8\xff\xd9")

    ir_path = bundle_root / "document_ir.json"
    ir_path.write_text(
        json.dumps(
            {
                "blocks": [
                    {
                        "block_id": "b1",
                        "type": "image",
                        "page_idx": 1,
                        "bbox_page": [10, 20, 30, 40],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    record = ChunkSearchRecord(
        child_chunk_id="cc1",
        qdrant_point_id="qp1",
        chunk_type="image",
        document_id="doc1",
        source_sha1="sha1",
        source_filename="sample.pptx",
        document_title="样本文档",
        bundle_root=str(bundle_root),
        origin_pdf_path=str(bundle_root / "origin.pdf"),
        ir_path=str(ir_path),
        review_status="ok",
        parent_chunk_id="pc1",
        parent_text="父级上下文内容",
        header_path=["sample", "目录"],
        source_block_ids=["b1"],
        page_start=1,
        page_end=1,
        retrieval_text="image: images/sample.jpg",
        embedding_text="sample > 目录\nimage: images/sample.jpg",
        assets=[
            {
                "asset_id": "asset-1",
                "asset_type": "image",
                "path": "images/sample.jpg",
            }
        ],
        metadata={},
    )
    candidate = RetrievedCandidate(
        chunk=record,
        channels={"vector"},
        vector_rank=1,
        vector_score=0.9,
        fusion_score=0.8,
        rerank_score=0.95,
    )

    service = QAService(
        settings=type(
            "S",
            (),
            {
                "qa_max_parent_chars": 1600,
                "qa_max_assets": 4,
                "qa_model": "qwen3.5-plus",
            },
        )()
    )
    context_source = service._build_source(candidate, 1)
    messages = service._build_messages("这张图是什么？", [context_source], max_assets=1)

    assert context_source.source.anchor_blocks[0].block_id == "b1"
    assert context_source.source.assets[0].absolute_path == str(image_path.resolve())
    user_content = messages[1].content
    assert isinstance(user_content, list)
    assert any(item.type == "image_url" for item in user_content)
