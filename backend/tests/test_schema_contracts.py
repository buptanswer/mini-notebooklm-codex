import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.chunk import ChildChunk, ChildChunkMetadata
from app.schemas.common import BBoxNorm1000
from app.schemas.ir import DocumentIR
from app.schemas.raw_mineru import RawContentListV2Block, RawLayoutPage


def test_raw_models_allow_future_fields() -> None:
    block = RawContentListV2Block.model_validate(
        {
            "type": "title",
            "bbox": [0, 0, 1000, 100],
            "content": {
                "level": 1,
                "title_content": [{"type": "text", "content": "Stage 1"}],
            },
            "future_field": "allowed",
        }
    )
    page = RawLayoutPage.model_validate(
        {
            "page_idx": 0,
            "page_size": [595, 842],
            "para_blocks": [],
            "discarded_blocks": [],
            "future_field": {"debug": True},
        }
    )

    assert block.type == "title"
    assert page.page_idx == 0


def test_strict_bbox_rejects_invalid_coordinates() -> None:
    with pytest.raises(ValidationError):
        BBoxNorm1000.model_validate([0, 0, 1200, 10])


def test_document_ir_is_strict() -> None:
    payload = {
        "source": {
            "doc_id": "doc-1",
            "source_filename": "sample.pdf",
            "source_format": "pdf",
            "mineru_request_model": "vlm",
            "mineru_actual_backend": "hybrid",
            "origin_pdf_path": "bundle/sample_origin.pdf",
        },
        "bundle": {
            "root_files": {
                "content_list_v2": "content_list_v2.json",
                "layout": "layout.json",
                "full_md": "full.md",
                "origin_pdf": "sample_origin.pdf",
            },
            "asset_root": "images/",
            "asset_count": 0,
        },
        "document": {
            "title": "Sample",
            "language": "zh",
            "page_count": 1,
            "reading_order": "page_then_block",
            "has_multimodal": False,
            "has_code": False,
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
                    "page_headers": [],
                    "page_footers": [],
                    "page_numbers": [],
                },
                "footnotes": [],
                "block_ids": ["b0001"],
            }
        ],
        "sections": [
            {
                "section_id": "s0001",
                "parent_section_id": None,
                "level": 1,
                "title": "Sample",
                "header_path": ["Sample"],
                "synthetic": False,
                "level_gap": False,
                "page_span": [0, 0],
                "child_section_ids": [],
                "block_ids": ["b0001"],
                "order_start": 0,
                "order_end": 0,
            }
        ],
        "blocks": [
            {
                "block_id": "b0001",
                "page_idx": 0,
                "order_in_page": 0,
                "order_in_doc": 0,
                "section_id": "s0001",
                "header_path": ["Sample"],
                "type": "paragraph",
                "subtype": None,
                "role": "main",
                "bbox_norm1000": [0, 0, 1000, 100],
                "bbox_page": [0, 0, 595, 84.2],
                "anchor": {
                    "page_id": "p0001",
                    "origin_pdf_path": "bundle/sample_origin.pdf",
                    "coord_space": "origin_pdf_native",
                    "render_formula": {
                        "x": "bbox_norm1000.x / 1000 * page_width",
                        "y": "bbox_norm1000.y / 1000 * page_height",
                    },
                },
                "text": "hello",
                "segments": [{"type": "text", "content": "hello"}],
                "assets": [],
                "metadata": {
                    "title_level": None,
                    "code_language": None,
                    "list_type": None,
                    "math_type": None,
                    "table_type": None,
                    "page_auxiliary_ref": {
                        "header_block_ids": [],
                        "footer_block_ids": [],
                        "page_number_block_ids": [],
                    },
                },
                "footnote_links": [],
                "raw_source": {
                    "source_file": "content_list_v2.json",
                    "source_type": "paragraph",
                },
            }
        ],
        "relations": {
            "parent_child": [],
            "footnote_attachment": [],
            "block_neighbors": [],
        },
        "quality": {
            "title_coverage": None,
            "footnote_attach_rate": None,
            "table_summary_coverage": None,
            "image_vlm_coverage": None,
            "ui_anchor_coverage": None,
            "degraded_modes": [],
            "ui_anchor_degraded": False,
        },
    }

    model = DocumentIR.model_validate(payload)
    assert model.blocks[0].text == "hello"


def test_child_chunk_fragment_requires_indices() -> None:
    with pytest.raises(ValidationError):
        ChildChunkMetadata.model_validate(
            {
                "is_atomic_fragment": True,
                "page_numbers": [],
            }
        )

    chunk = ChildChunk.model_validate(
        {
            "child_chunk_id": "cc1",
            "parent_chunk_id": "pc1",
            "doc_id": "doc1",
            "section_id": "s1",
            "header_path": ["第一章"],
            "chunk_type": "paragraph",
            "page_span": [0, 0],
            "source_block_ids": ["b1"],
            "embedding_text": "第一章\n内容",
            "retrieval_text": "内容",
            "assets": [],
            "metadata": {"page_numbers": [], "is_atomic": False},
        }
    )

    assert chunk.parent_chunk_id == "pc1"


def test_stage3_embedding_settings_follow_official_limits() -> None:
    valid = Settings(
        embedding_model="text-embedding-v4",
        embedding_dimensions=2048,
        qdrant_vector_size=2048,
        embedding_batch_size=10,
    )
    assert valid.embedding_dimensions == 2048

    with pytest.raises(ValidationError):
        Settings(
            embedding_model="text-embedding-v4",
            embedding_dimensions=999,
            qdrant_vector_size=999,
        )

    with pytest.raises(ValidationError):
        Settings(embedding_batch_size=11)
