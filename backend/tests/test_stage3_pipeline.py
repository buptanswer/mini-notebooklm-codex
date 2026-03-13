import json
from pathlib import Path

import httpx

from app.schemas.ir import DocumentIR
from app.services.chunking import StructureAwareChunker
from app.services.embedding_client import DashScopeEmbeddingClient
from app.services.stage3_pipeline import Stage3Pipeline
from app.validators import validate_chunks


def _sample_document_ir() -> DocumentIR:
    payload = {
        "source": {
            "doc_id": "doc-stage3",
            "source_filename": "sample.pdf",
            "source_format": "pdf",
            "mineru_request_model": "vlm",
            "mineru_actual_backend": "hybrid",
            "origin_pdf_path": "sample_origin.pdf",
        },
        "bundle": {
            "root_files": {
                "content_list_v2": "content_list_v2.json",
                "layout": "layout.json",
                "full_md": "full.md",
                "origin_pdf": "sample_origin.pdf",
            },
            "asset_root": "images/",
            "asset_count": 1,
        },
        "document": {
            "title": "Sample",
            "language": "en",
            "page_count": 1,
            "has_multimodal": True,
            "has_code": True,
            "has_table": False,
            "has_equation": False,
            "has_footnote": False,
        },
        "pages": [
            {
                "page_id": "p0001",
                "page_idx": 0,
                "page_size": {"width": 595, "height": 842, "unit": "origin_pdf_native"},
                "auxiliary": {
                    "page_headers": [{"text": "Header", "block_id": "aux1"}],
                    "page_footers": [],
                    "page_numbers": [{"text": "1", "block_id": "aux2"}],
                },
                "footnotes": [],
                "block_ids": ["b1", "b2", "b3", "b4"],
            }
        ],
        "sections": [
            {
                "section_id": "s0001",
                "level": 0,
                "title": "Sample",
                "header_path": ["Sample"],
                "synthetic": True,
                "level_gap": False,
                "page_span": [0, 0],
                "child_section_ids": ["s0002"],
                "block_ids": [],
                "order_start": 0,
                "order_end": 0,
            },
            {
                "section_id": "s0002",
                "parent_section_id": "s0001",
                "level": 1,
                "title": "Section 1",
                "header_path": ["Sample", "Section 1"],
                "synthetic": False,
                "level_gap": False,
                "page_span": [0, 0],
                "child_section_ids": [],
                "block_ids": ["b1", "b2", "b3", "b4"],
                "order_start": 0,
                "order_end": 3,
            },
        ],
        "blocks": [
            {
                "block_id": "b1",
                "page_idx": 0,
                "order_in_page": 0,
                "order_in_doc": 0,
                "section_id": "s0002",
                "header_path": ["Sample", "Section 1"],
                "type": "title",
                "role": "main",
                "bbox_norm1000": [0, 0, 1000, 100],
                "bbox_page": [0, 0, 595, 84.2],
                "anchor": {
                    "page_id": "p0001",
                    "origin_pdf_path": "sample_origin.pdf",
                    "coord_space": "origin_pdf_native",
                    "render_formula": {
                        "x": "bbox_norm1000.x / 1000 * page_width",
                        "y": "bbox_norm1000.y / 1000 * page_height",
                    },
                },
                "text": "Section 1",
                "segments": [{"type": "text", "content": "Section 1"}],
                "assets": [],
                "metadata": {"title_level": 1, "page_auxiliary_ref": {}},
                "footnote_links": [],
                "raw_source": {"source_file": "content_list_v2.json", "source_type": "title"},
            },
            {
                "block_id": "b2",
                "page_idx": 0,
                "order_in_page": 1,
                "order_in_doc": 1,
                "section_id": "s0002",
                "header_path": ["Sample", "Section 1"],
                "type": "paragraph",
                "role": "main",
                "bbox_norm1000": [0, 120, 1000, 260],
                "bbox_page": [0, 101.04, 595, 218.92],
                "anchor": {
                    "page_id": "p0001",
                    "origin_pdf_path": "sample_origin.pdf",
                    "coord_space": "origin_pdf_native",
                    "render_formula": {
                        "x": "bbox_norm1000.x / 1000 * page_width",
                        "y": "bbox_norm1000.y / 1000 * page_height",
                    },
                },
                "text": "This is the first paragraph. It should be indexed as a semantic child chunk.",
                "segments": [{"type": "text", "content": "This is the first paragraph."}],
                "assets": [],
                "metadata": {"page_auxiliary_ref": {}},
                "footnote_links": [],
                "raw_source": {"source_file": "content_list_v2.json", "source_type": "paragraph"},
            },
            {
                "block_id": "b3",
                "page_idx": 0,
                "order_in_page": 2,
                "order_in_doc": 2,
                "section_id": "s0002",
                "header_path": ["Sample", "Section 1"],
                "type": "code",
                "role": "main",
                "bbox_norm1000": [0, 270, 1000, 420],
                "bbox_page": [0, 227.34, 595, 353.64],
                "anchor": {
                    "page_id": "p0001",
                    "origin_pdf_path": "sample_origin.pdf",
                    "coord_space": "origin_pdf_native",
                    "render_formula": {
                        "x": "bbox_norm1000.x / 1000 * page_width",
                        "y": "bbox_norm1000.y / 1000 * page_height",
                    },
                },
                "text": "def hello():\n    return 'world'",
                "segments": [{"type": "code", "content": "def hello():"}],
                "assets": [],
                "metadata": {"code_language": "python", "page_auxiliary_ref": {}},
                "footnote_links": [],
                "raw_source": {"source_file": "content_list_v2.json", "source_type": "code"},
            },
            {
                "block_id": "b4",
                "page_idx": 0,
                "order_in_page": 3,
                "order_in_doc": 3,
                "section_id": "s0002",
                "header_path": ["Sample", "Section 1"],
                "type": "image",
                "role": "main",
                "bbox_norm1000": [100, 450, 900, 900],
                "bbox_page": [59.5, 378.9, 535.5, 757.8],
                "anchor": {
                    "page_id": "p0001",
                    "origin_pdf_path": "sample_origin.pdf",
                    "coord_space": "origin_pdf_native",
                    "render_formula": {
                        "x": "bbox_norm1000.x / 1000 * page_width",
                        "y": "bbox_norm1000.y / 1000 * page_height",
                    },
                },
                "text": "Figure 1 architecture",
                "segments": [{"type": "caption", "content": "Figure 1 architecture"}],
                "assets": [
                    {
                        "asset_id": "asset-1",
                        "asset_type": "image",
                        "path": "images/sample.jpg",
                        "usage": "primary",
                    }
                ],
                "metadata": {"page_auxiliary_ref": {}},
                "footnote_links": [],
                "raw_source": {"source_file": "content_list_v2.json", "source_type": "image"},
            },
        ],
    }
    return DocumentIR.model_validate(payload)


def test_structure_aware_chunker_builds_parent_and_children() -> None:
    document_ir = _sample_document_ir()
    chunker = StructureAwareChunker()

    result = chunker.chunk_document(document_ir)
    validate_chunks(document_ir, result.parents, result.children)

    assert len(result.parents) == 1
    assert len(result.children) == 3
    assert result.parents[0].metadata.page_numbers == ["1"]
    assert result.children[0].embedding_text.startswith("Sample > Section 1")
    assert result.children[1].metadata.code_language == "python"
    assert result.children[2].assets[0].path == "images/sample.jpg"


def test_stage3_pipeline_writes_jsonl_with_fake_embeddings(tmp_path: Path) -> None:
    document_ir = _sample_document_ir()
    ir_path = tmp_path / "document_ir.json"
    ir_path.write_text(
        json.dumps(document_ir.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    pipeline = Stage3Pipeline()
    artifacts = pipeline.process_document(
        document_ir_path=ir_path,
        output_root=tmp_path,
        use_fake_embeddings=True,
    )

    assert artifacts.parent_chunks_path.exists()
    assert artifacts.child_chunks_path.exists()
    assert len(artifacts.children) == len(artifacts.vectors)
    assert len(artifacts.vectors[0]) == 1024
    assert artifacts.embedding_model == "fake-hash-embedding"


def test_embedding_client_parses_openai_compatible_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/embeddings")
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["model"] == "text-embedding-v4"
        assert payload["dimensions"] == 1024
        embedding_a = [0.1] * 1024
        embedding_b = [0.2] * 1024
        return httpx.Response(
            200,
            json={
                "id": "embd-123",
                "object": "list",
                "created": 1741766400,
                "model": "text-embedding-v4",
                "data": [
                    {"object": "embedding", "index": 0, "embedding": embedding_a},
                    {"object": "embedding", "index": 1, "embedding": embedding_b},
                ],
                "usage": {"prompt_tokens": 6, "total_tokens": 6},
            },
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(
        transport=transport,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )

    embedding_client = DashScopeEmbeddingClient(
        settings=type(
            "S",
            (),
            {
                "dashscope_api_key": "test-key",
                "dashscope_embedding_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "embedding_model": "text-embedding-v4",
                "embedding_dimensions": 1024,
                "embedding_batch_size": 10,
            },
        )(),
        http_client=client,
    )
    result = embedding_client.embed_texts(["a", "b"])

    assert result.model == "text-embedding-v4"
    assert result.total_tokens == 6
    assert len(result.vectors) == 2
    assert len(result.vectors[0]) == 1024
    assert result.vectors[0][:2] == [0.1, 0.1]
    assert result.vectors[1][:2] == [0.2, 0.2]
