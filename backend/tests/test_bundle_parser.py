import json
from pathlib import Path

from app.services.bundle_parser import MineruBundleParser
from app.services.document_review import inspect_document_ir


def test_bundle_parser_builds_document_ir(tmp_path: Path) -> None:
    bundle_root = tmp_path / "bundle"
    images_dir = bundle_root / "images"
    images_dir.mkdir(parents=True)

    (bundle_root / "full.md").write_text("# 示例文档\n\n第一段", encoding="utf-8")
    (bundle_root / "123_origin.pdf").write_bytes(b"%PDF-1.4\n%fake\n")
    (images_dir / "sample.jpg").write_bytes(b"jpg")

    content_list_v2 = [
        [
            {
                "type": "title",
                "bbox": [0, 0, 1000, 120],
                "content": {
                    "level": 1,
                    "title_content": [{"type": "text", "content": "示例文档"}],
                },
            },
            {
                "type": "paragraph",
                "bbox": [0, 150, 1000, 260],
                "content": {
                    "paragraph_content": [{"type": "text", "content": "第一段内容"}]
                },
            },
            {
                "type": "image",
                "bbox": [100, 300, 900, 850],
                "content": {
                    "image_source": {"path": "images/sample.jpg"},
                    "image_caption": [{"type": "text", "content": "图1"}],
                    "image_footnote": [{"type": "text", "content": "来源"}],
                },
            },
        ]
    ]
    (bundle_root / "content_list_v2.json").write_text(
        json.dumps(content_list_v2, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    layout = {
        "_backend": "pipeline",
        "_version_name": "test-version",
        "pdf_info": [
            {
                "page_idx": 0,
                "page_size": [595, 842],
                "para_blocks": [],
                "discarded_blocks": [],
            }
        ],
    }
    (bundle_root / "layout.json").write_text(
        json.dumps(layout, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    parser = MineruBundleParser()
    bundle_files = parser.inspect_bundle(bundle_root)

    source_path = tmp_path / "source.pdf"
    source_path.write_bytes(b"source")
    document_ir = parser.build_document_ir(bundle_files, source_path=source_path)

    assert document_ir.document.title == "示例文档"
    assert document_ir.document.page_count == 1
    assert document_ir.document.has_multimodal is True
    assert document_ir.blocks[0].type == "title"
    assert document_ir.blocks[1].bbox_page is not None
    assert document_ir.blocks[2].assets[0].path == "images/sample.jpg"
    assert document_ir.source.origin_pdf_path == "123_origin.pdf"
    assert document_ir.sections[1].header_path == ["source", "示例文档"]
    assert document_ir.quality.parser_warnings == []


def test_bundle_parser_warns_and_preserves_unknown_payload(tmp_path: Path) -> None:
    bundle_root = tmp_path / "bundle"
    bundle_root.mkdir(parents=True)

    (bundle_root / "full.md").write_text("fallback", encoding="utf-8")
    (bundle_root / "123_origin.pdf").write_bytes(b"%PDF-1.4\n%fake\n")
    (bundle_root / "content_list_v2.json").write_text(
        json.dumps(
            [
                [
                    {
                        "type": "mystery_block",
                        "bbox": [0, 0, 1000, 100],
                        "future_field": "unexpected",
                        "content": {"surprise": "payload"},
                    }
                ]
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (bundle_root / "layout.json").write_text(
        json.dumps(
            {
                "pdf_info": [
                    {
                        "page_idx": 0,
                        "page_size": [595, 842],
                        "para_blocks": [],
                        "discarded_blocks": [],
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    parser = MineruBundleParser()
    bundle_files = parser.inspect_bundle(bundle_root)
    source_path = tmp_path / "source.pdf"
    source_path.write_bytes(b"source")

    document_ir = parser.build_document_ir(bundle_files, source_path=source_path)

    assert document_ir.blocks[0].type == "unknown"
    assert document_ir.blocks[0].raw_source.extra_fields == {"future_field": "unexpected"}
    assert document_ir.blocks[0].raw_source.content_snapshot is not None
    assert document_ir.blocks[0].raw_source.content_snapshot["surprise"] == "payload"
    assert len(document_ir.quality.parser_warnings) >= 2
    assert "raw_schema_warning" in document_ir.quality.degraded_modes

    review = inspect_document_ir(document_ir)
    assert review.review_status == "needs_review"
    assert review.parser_warning_count >= 2
    assert review.unknown_block_count == 1
