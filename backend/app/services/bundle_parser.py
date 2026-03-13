from __future__ import annotations

import hashlib
import html
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from zipfile import ZipFile

from pydantic import BaseModel

from app.schemas.common import BBoxNorm1000, BBoxPage, PageSpan
from app.schemas.ir import (
    DocumentIR,
    IRAnchor,
    IRAnchorRenderFormula,
    IRAsset,
    IRBlock,
    IRBlockMetadata,
    IRBlockSegment,
    IRBundle,
    IRBundleRootFiles,
    IRDocument,
    IRPage,
    IRPageAuxiliary,
    IRPageAuxiliaryRef,
    IRPageFootnote,
    IRPageSize,
    IRQuality,
    IRRawSource,
    IRSection,
    IRSource,
    IRTextRef,
)
from app.schemas.raw_mineru import RawContentListV2Block, RawLayoutRoot
from app.validators import validate_document_ir

logger = logging.getLogger(__name__)


BLOCK_TYPE_MAP = {
    "title": "title",
    "text": "paragraph",
    "paragraph": "paragraph",
    "list": "list",
    "code": "code",
    "image": "image",
    "table": "table",
    "equation_interline": "equation",
    "page_header": "page_header",
    "page_footer": "page_footer",
    "page_number": "page_number",
    "footnote": "page_footnote",
    "page_footnote": "page_footnote",
}

AUXILIARY_TYPES = {"page_header", "page_footer", "page_number", "page_footnote"}


@dataclass(slots=True)
class MineruBundleFiles:
    bundle_root: Path
    content_list_v2: Path
    layout: Path
    full_md: Path
    origin_pdf: Path
    compat_content_list: Path | None = None
    model_raw: Path | None = None
    images_dir: Path | None = None


@dataclass(slots=True)
class SectionState:
    section_id: str
    parent_section_id: str | None
    level: int
    title: str | None
    header_path: list[str]
    synthetic: bool
    level_gap: bool
    page_start: int | None = None
    page_end: int | None = None
    order_start: int | None = None
    order_end: int | None = None
    block_ids: list[str] = field(default_factory=list)
    child_section_ids: list[str] = field(default_factory=list)

    def touch(self, page_idx: int, order_in_doc: int, block_id: str) -> None:
        if self.page_start is None:
            self.page_start = page_idx
        self.page_end = page_idx
        if self.order_start is None:
            self.order_start = order_in_doc
        self.order_end = order_in_doc
        self.block_ids.append(block_id)


class MineruBundleParser:
    def extract_bundle(
        self,
        bundle_zip_path: str | Path,
        extract_dir: str | Path | None = None,
    ) -> Path:
        bundle_path = Path(bundle_zip_path)
        target_dir = Path(extract_dir) if extract_dir else bundle_path.with_suffix("")
        target_dir.mkdir(parents=True, exist_ok=True)
        with ZipFile(bundle_path) as archive:
            archive.extractall(target_dir)
        return target_dir

    def inspect_bundle(self, extracted_dir: str | Path) -> MineruBundleFiles:
        root = Path(extracted_dir)
        content_list_v2 = self._expect_single(root, "content_list_v2.json")
        layout = self._expect_single(root, "layout.json")
        full_md = self._expect_single(root, "full.md")
        origin_pdf = self._find_suffix(root, "_origin.pdf")
        compat = self._find_suffix(root, "_content_list.json", required=False)
        model_raw = self._find_suffix(root, "_model.json", required=False)
        images_dir = root / "images" if (root / "images").exists() else None
        return MineruBundleFiles(
            bundle_root=root,
            content_list_v2=content_list_v2,
            layout=layout,
            full_md=full_md,
            origin_pdf=origin_pdf,
            compat_content_list=compat,
            model_raw=model_raw,
            images_dir=images_dir,
        )

    def build_document_ir(
        self,
        bundle_files: MineruBundleFiles,
        source_path: str | Path,
        mineru_request_model: str = "vlm",
    ) -> DocumentIR:
        source_file = Path(source_path)
        content_pages = self._load_content_pages(bundle_files.content_list_v2)
        layout_root = RawLayoutRoot.model_validate_json(
            bundle_files.layout.read_text(encoding="utf-8")
        )
        warnings: list[str] = []
        self._collect_unknown_fields(layout_root, "layout", warnings)

        page_sizes = {
            page.page_idx: page.page_size for page in layout_root.pdf_info if len(page.page_size) >= 2
        }

        pages: list[IRPage] = []
        for page_idx, blocks in enumerate(content_pages):
            size = page_sizes.get(page_idx, [0.0, 0.0])
            pages.append(
                IRPage(
                    page_id=f"p{page_idx + 1:04d}",
                    page_idx=page_idx,
                    page_size=IRPageSize(width=float(size[0]), height=float(size[1])),
                )
            )

        if not pages:
            pages.append(
                IRPage(
                    page_id="p0001",
                    page_idx=0,
                    page_size=IRPageSize(width=0.0, height=0.0),
                )
            )

        default_header = source_file.stem or "无标题文档"
        root_section = SectionState(
            section_id="s0001",
            parent_section_id=None,
            level=0,
            title=default_header,
            header_path=[default_header],
            synthetic=True,
            level_gap=False,
        )
        section_states: list[SectionState] = [root_section]
        title_stack: list[SectionState] = []

        blocks_out: list[IRBlock] = []
        order_in_doc = 0
        block_index = 1
        section_index = 2
        degraded_modes: list[str] = []
        missing_page_size = False
        unknown_block_seen = False

        for page_idx, raw_blocks in enumerate(content_pages):
            page = pages[page_idx]
            for order_in_page, raw_block in enumerate(raw_blocks):
                self._collect_unknown_fields(
                    raw_block,
                    f"content_list_v2.page[{page_idx}].block[{order_in_page}]",
                    warnings,
                )
                block_type = self._normalize_block_type(raw_block.type)
                if block_type == "unknown":
                    unknown_block_seen = True
                    self._warn(
                        warnings,
                        f"unrecognized MinerU block type `{raw_block.type}` at "
                        f"content_list_v2.page[{page_idx}].block[{order_in_page}]",
                    )
                if isinstance(raw_block.content, (dict, list, str)):
                    self._warn(
                        warnings,
                        f"fallback content shape at content_list_v2.page[{page_idx}].block[{order_in_page}] "
                        f"for raw type `{raw_block.type}`",
                    )

                block_text = self._extract_text(raw_block)
                if block_type == "title":
                    title_level = self._extract_title_level(raw_block)
                    while title_stack and title_stack[-1].level >= title_level:
                        title_stack.pop()
                    parent = title_stack[-1] if title_stack else root_section
                    title_text = block_text or f"未命名标题 {section_index - 1}"
                    section_state = SectionState(
                        section_id=f"s{section_index:04d}",
                        parent_section_id=parent.section_id,
                        level=title_level,
                        title=title_text,
                        header_path=[*parent.header_path, title_text],
                        synthetic=False,
                        level_gap=bool(title_stack and title_level - title_stack[-1].level > 1),
                    )
                    parent.child_section_ids.append(section_state.section_id)
                    section_states.append(section_state)
                    title_stack.append(section_state)
                    active_section = section_state
                    section_index += 1
                else:
                    active_section = title_stack[-1] if title_stack else root_section

                bbox_norm = self._coerce_bbox_norm(raw_block.bbox)
                bbox_page = self._norm_to_page_bbox(bbox_norm, page.page_size.width, page.page_size.height)
                if bbox_page is None:
                    missing_page_size = True

                block_id = f"b{block_index:05d}"
                block_index += 1
                block = IRBlock(
                    block_id=block_id,
                    page_idx=page_idx,
                    order_in_page=order_in_page,
                    order_in_doc=order_in_doc,
                    section_id=active_section.section_id,
                    header_path=active_section.header_path,
                    type=block_type,
                    subtype=raw_block.type,
                    role="auxiliary" if block_type in AUXILIARY_TYPES else "main",
                    bbox_norm1000=bbox_norm,
                    bbox_page=bbox_page,
                    anchor=self._build_anchor(page.page_id, bundle_files.origin_pdf.name)
                    if bbox_page is not None
                    else None,
                    text=block_text,
                    segments=self._extract_segments(raw_block),
                    assets=self._extract_assets(raw_block, bundle_files.images_dir),
                    metadata=self._extract_metadata(raw_block),
                    raw_source=IRRawSource(
                        source_file=bundle_files.content_list_v2.name,
                        source_type=raw_block.type,
                        extra_fields=raw_block.model_extra or {},
                        content_snapshot=self._content_snapshot(raw_block),
                    ),
                )

                blocks_out.append(block)
                page.block_ids.append(block_id)
                active_section.touch(page_idx, order_in_doc, block_id)
                order_in_doc += 1

                if block.type == "page_header" and block.text:
                    page.auxiliary.page_headers.append(IRTextRef(text=block.text, block_id=block.block_id))
                elif block.type == "page_footer" and block.text:
                    page.auxiliary.page_footers.append(IRTextRef(text=block.text, block_id=block.block_id))
                elif block.type == "page_number" and block.text:
                    page.auxiliary.page_numbers.append(IRTextRef(text=block.text, block_id=block.block_id))
                elif block.type == "page_footnote" and block.text:
                    page.footnotes.append(IRPageFootnote(block_id=block.block_id, text=block.text))

        for page in pages:
            aux_ref = IRPageAuxiliaryRef(
                header_block_ids=[item.block_id for item in page.auxiliary.page_headers],
                footer_block_ids=[item.block_id for item in page.auxiliary.page_footers],
                page_number_block_ids=[item.block_id for item in page.auxiliary.page_numbers],
            )
            page_block_ids = set(page.block_ids)
            for block in blocks_out:
                if block.block_id in page_block_ids and block.role == "main":
                    block.metadata.page_auxiliary_ref = aux_ref

        sections = [
            IRSection(
                section_id=state.section_id,
                parent_section_id=state.parent_section_id,
                level=state.level,
                title=state.title,
                header_path=state.header_path,
                synthetic=state.synthetic,
                level_gap=state.level_gap,
                page_span=PageSpan.model_validate(
                    [state.page_start or 0, state.page_end or state.page_start or 0]
                ),
                child_section_ids=state.child_section_ids,
                block_ids=state.block_ids,
                order_start=state.order_start or 0,
                order_end=state.order_end or state.order_start or 0,
            )
            for state in section_states
        ]

        document_title = next((block.text for block in blocks_out if block.type == "title" and block.text), default_header)
        language = self._detect_language([block.text for block in blocks_out if block.text])
        has_multimodal = any(block.type in {"image", "table", "equation"} for block in blocks_out)

        if missing_page_size:
            degraded_modes.append("ui_anchor_degraded")
        if warnings:
            degraded_modes.append("raw_schema_warning")
        if unknown_block_seen:
            degraded_modes.append("unknown_block_type")

        document_ir = DocumentIR(
            source=IRSource(
                doc_id=self._sha1_for_file(source_file),
                source_filename=source_file.name,
                source_format=self._source_format(source_file),
                mineru_request_model=mineru_request_model,
                mineru_actual_backend=layout_root.backend or "unknown",
                mineru_version_name=layout_root.version_name,
                origin_pdf_path=bundle_files.origin_pdf.name,
            ),
            bundle=IRBundle(
                root_files=IRBundleRootFiles(
                    content_list_v2=bundle_files.content_list_v2.name,
                    layout=bundle_files.layout.name,
                    full_md=bundle_files.full_md.name,
                    content_list_compat=(
                        bundle_files.compat_content_list.name
                        if bundle_files.compat_content_list
                        else None
                    ),
                    model_raw=bundle_files.model_raw.name if bundle_files.model_raw else None,
                    origin_pdf=bundle_files.origin_pdf.name,
                ),
                asset_root="images/",
                asset_count=len(list(bundle_files.images_dir.iterdir()))
                if bundle_files.images_dir
                else 0,
            ),
            document=IRDocument(
                title=document_title,
                language=language,
                page_count=len(pages),
                has_multimodal=has_multimodal,
                has_code=any(block.type == "code" for block in blocks_out),
                has_table=any(block.type == "table" for block in blocks_out),
                has_equation=any(block.type == "equation" for block in blocks_out),
                has_footnote=any(block.type == "page_footnote" for block in blocks_out),
            ),
            pages=pages,
            sections=sections,
            blocks=blocks_out,
            quality=IRQuality(
                ui_anchor_coverage=self._ratio(
                    sum(1 for block in blocks_out if block.anchor is not None),
                    len(blocks_out),
                ),
                degraded_modes=degraded_modes,
                ui_anchor_degraded=missing_page_size,
                parser_warnings=warnings,
            ),
        )
        validate_document_ir(document_ir)
        return document_ir

    def _load_content_pages(self, content_list_path: Path) -> list[list[RawContentListV2Block]]:
        payload = json.loads(content_list_path.read_text(encoding="utf-8"))
        pages_raw = payload.get("pages", payload) if isinstance(payload, dict) else payload
        if not isinstance(pages_raw, list):
            raise ValueError("content_list_v2.json must be a page list or a dict with pages")

        pages: list[list[RawContentListV2Block]] = []
        for page in pages_raw:
            if not isinstance(page, list):
                raise ValueError("each content_list_v2 page must be a list of blocks")
            pages.append([RawContentListV2Block.model_validate(item) for item in page])
        return pages

    def _extract_title_level(self, block: RawContentListV2Block) -> int:
        content = block.content
        if hasattr(content, "level") and getattr(content, "level") is not None:
            return max(1, int(getattr(content, "level")))
        if isinstance(block.content, dict) and block.content.get("level") is not None:
            return max(1, int(block.content["level"]))
        return 1

    def _extract_segments(self, block: RawContentListV2Block) -> list[IRBlockSegment]:
        segments = self._collect_segments(block)
        return [IRBlockSegment(type=segment_type, content=text) for segment_type, text in segments if text]

    def _extract_assets(self, block: RawContentListV2Block, images_dir: Path | None) -> list[IRAsset]:
        content = block.content
        image_path = None
        usage = "primary"
        asset_type = "image"

        if hasattr(content, "image_source") and getattr(content, "image_source") is not None:
            image_source = getattr(content, "image_source")
            image_path = getattr(image_source, "path", None)

        if block.type == "table":
            asset_type = "table_image"
            usage = "qa_preferred"
        elif block.type == "equation_interline":
            asset_type = "equation_image"
            usage = "debug_or_render"

        if not image_path:
            return []

        if images_dir:
            asset_path = Path("images") / Path(image_path).name
        else:
            asset_path = Path(image_path)

        return [
            IRAsset(
                asset_id=f"asset-{Path(image_path).stem}",
                asset_type=asset_type,
                path=asset_path.as_posix(),
                usage=usage,
                mime=self._mime_from_suffix(asset_path.suffix),
            )
        ]

    def _extract_metadata(self, block: RawContentListV2Block) -> IRBlockMetadata:
        content = block.content
        metadata = IRBlockMetadata()

        if block.type == "title":
            metadata.title_level = self._extract_title_level(block)

        for attribute, target in (
            ("code_language", "code_language"),
            ("list_type", "list_type"),
            ("math_type", "math_type"),
            ("table_type", "table_type"),
        ):
            if hasattr(content, attribute):
                setattr(metadata, target, getattr(content, attribute))
            elif isinstance(content, dict) and attribute in content:
                setattr(metadata, target, content[attribute])

        return metadata

    def _extract_text(self, block: RawContentListV2Block) -> str | None:
        segments = [text for _, text in self._collect_segments(block) if text]
        if not segments:
            return None
        return "\n".join(segment for segment in segments if segment).strip() or None

    def _collect_segments(self, block: RawContentListV2Block) -> list[tuple[str, str]]:
        content = block.content
        if content is None:
            return []

        if block.type == "title" and hasattr(content, "title_content"):
            return [("text", self._join_inline_parts(getattr(content, "title_content")))]
        if block.type in {"paragraph", "text"} and hasattr(content, "paragraph_content"):
            return [("text", self._join_inline_parts(getattr(content, "paragraph_content")))]
        if block.type == "list" and hasattr(content, "list_items"):
            return [
                ("list_item", self._join_inline_parts(item.item_content))
                for item in getattr(content, "list_items")
            ]
        if block.type == "code" and hasattr(content, "code_content"):
            code_text = self._join_inline_parts(getattr(content, "code_content"))
            caption = self._join_inline_parts(getattr(content, "code_caption"))
            result = [("code", code_text)]
            if caption:
                result.append(("caption", caption))
            return result
        if block.type == "image":
            return [
                ("caption", self._join_inline_parts(getattr(content, "image_caption", []))),
                ("footnote", self._join_inline_parts(getattr(content, "image_footnote", []))),
            ]
        if block.type == "table":
            return [
                ("caption", self._join_inline_parts(getattr(content, "table_caption", []))),
                ("table_html", self._strip_html(getattr(content, "html", None))),
                ("footnote", self._join_inline_parts(getattr(content, "table_footnote", []))),
            ]
        if block.type == "equation_interline":
            return [("math", getattr(content, "math_content", None) or "")]
        if block.type == "page_header" and hasattr(content, "page_header_content"):
            return [("text", self._join_inline_parts(getattr(content, "page_header_content")))]
        if block.type == "page_footer" and hasattr(content, "page_footer_content"):
            return [("text", self._join_inline_parts(getattr(content, "page_footer_content")))]
        if block.type == "page_number" and hasattr(content, "page_number_content"):
            return [("text", self._join_inline_parts(getattr(content, "page_number_content")))]
        if block.type in {"footnote", "page_footnote"} and hasattr(
            content, "page_footnote_content"
        ):
            return [("text", self._join_inline_parts(getattr(content, "page_footnote_content")))]

        if isinstance(content, str):
            return [("text", content)]
        if isinstance(content, dict):
            collected = self._collect_text(content)
            return [("text", collected)] if collected else []
        if isinstance(content, list):
            collected = self._collect_text(content)
            return [("text", collected)] if collected else []
        return []

    def _collect_text(self, value: object) -> str:
        parts: list[str] = []
        if isinstance(value, dict):
            for child in value.values():
                collected = self._collect_text(child)
                if collected:
                    parts.append(collected)
        elif isinstance(value, list):
            for child in value:
                collected = self._collect_text(child)
                if collected:
                    parts.append(collected)
        elif isinstance(value, str):
            parts.append(value)
        return "\n".join(part for part in parts if part).strip()

    def _normalize_block_type(self, raw_type: str) -> str:
        return BLOCK_TYPE_MAP.get(raw_type, "unknown")

    def _content_snapshot(
        self,
        block: RawContentListV2Block,
    ) -> dict[str, object] | list[object] | str | None:
        content = block.content
        if content is None:
            return None
        if isinstance(content, BaseModel):
            dumped = content.model_dump(mode="json", by_alias=True, exclude_none=False)
            return dumped if self._has_payload_warnings(content) else None
        if isinstance(content, (dict, list, str)):
            return content
        return None

    def _coerce_bbox_norm(self, bbox: list[float] | None) -> BBoxNorm1000:
        if not bbox or len(bbox) != 4:
            return BBoxNorm1000.model_validate([0, 0, 0, 0])
        normalized = [min(1000.0, max(0.0, float(item))) for item in bbox]
        return BBoxNorm1000.model_validate(normalized)

    def _norm_to_page_bbox(
        self,
        bbox_norm: BBoxNorm1000,
        page_width: float,
        page_height: float,
    ) -> BBoxPage | None:
        if page_width <= 0 or page_height <= 0:
            return None
        x0, y0, x1, y1 = bbox_norm.root
        return BBoxPage.model_validate(
            [
                x0 / 1000 * page_width,
                y0 / 1000 * page_height,
                x1 / 1000 * page_width,
                y1 / 1000 * page_height,
            ]
        )

    def _build_anchor(self, page_id: str, origin_pdf_path: str) -> IRAnchor:
        return IRAnchor(
            page_id=page_id,
            origin_pdf_path=origin_pdf_path,
            render_formula=IRAnchorRenderFormula(
                x="bbox_norm1000.x / 1000 * page_width",
                y="bbox_norm1000.y / 1000 * page_height",
            ),
        )

    def _source_format(self, source_path: Path) -> str:
        suffix = source_path.suffix.lower().lstrip(".")
        if suffix not in {"pdf", "doc", "docx", "ppt", "pptx", "png", "jpg", "jpeg"}:
            raise ValueError(f"unsupported source format: {source_path.suffix}")
        return suffix

    def _sha1_for_file(self, path: Path) -> str:
        digest = hashlib.sha1()
        with path.open("rb") as file_obj:
            for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _detect_language(self, texts: list[str]) -> str:
        merged = "".join(texts)
        if not merged:
            return "unknown"
        has_cjk = bool(re.search(r"[\u4e00-\u9fff]", merged))
        has_ascii_letters = bool(re.search(r"[A-Za-z]", merged))
        if has_cjk and has_ascii_letters:
            return "mixed"
        if has_cjk:
            return "zh"
        if has_ascii_letters:
            return "en"
        return "unknown"

    def _join_inline_parts(self, parts: list[object] | None) -> str:
        if not parts:
            return ""
        texts: list[str] = []
        for part in parts:
            if hasattr(part, "content") and getattr(part, "content"):
                texts.append(str(getattr(part, "content")))
            elif isinstance(part, dict) and part.get("content"):
                texts.append(str(part["content"]))
            elif isinstance(part, str):
                texts.append(part)
        return "".join(texts).strip()

    def _strip_html(self, value: str | None) -> str:
        if not value:
            return ""
        no_tags = re.sub(r"<[^>]+>", " ", value)
        return re.sub(r"\s+", " ", html.unescape(no_tags)).strip()

    def _mime_from_suffix(self, suffix: str) -> str | None:
        mapping = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }
        return mapping.get(suffix.lower())

    def _expect_single(self, root: Path, name: str) -> Path:
        path = root / name
        if not path.exists():
            raise FileNotFoundError(path)
        return path

    def _find_suffix(self, root: Path, suffix: str, required: bool = True) -> Path | None:
        for candidate in root.iterdir():
            if candidate.is_file() and candidate.name.endswith(suffix):
                return candidate
        if required:
            raise FileNotFoundError(f"missing file with suffix {suffix} in {root}")
        return None

    def _ratio(self, numerator: int, denominator: int) -> float | None:
        if denominator <= 0:
            return None
        return round(numerator / denominator, 4)

    def _collect_unknown_fields(
        self,
        value: object,
        path: str,
        warnings: list[str],
    ) -> None:
        if isinstance(value, BaseModel):
            model_extra = value.model_extra or {}
            for key in model_extra:
                self._warn(warnings, f"unknown field `{path}.{key}` detected in MinerU payload")
            for field_name in type(value).model_fields:
                child = getattr(value, field_name, None)
                if child is not None:
                    self._collect_unknown_fields(child, f"{path}.{field_name}", warnings)
            return

        if isinstance(value, list):
            for index, child in enumerate(value):
                self._collect_unknown_fields(child, f"{path}[{index}]", warnings)
            return

        if isinstance(value, dict):
            for key, child in value.items():
                if child is not None:
                    self._collect_unknown_fields(child, f"{path}.{key}", warnings)

    def _has_payload_warnings(self, value: object) -> bool:
        if isinstance(value, BaseModel):
            if value.model_extra:
                return True
            return any(
                self._has_payload_warnings(getattr(value, field_name, None))
                for field_name in type(value).model_fields
            )
        if isinstance(value, list):
            return any(self._has_payload_warnings(item) for item in value)
        if isinstance(value, dict):
            return True
        return False

    def _warn(self, warnings: list[str], message: str) -> None:
        if message in warnings:
            return
        warnings.append(message)
        logger.warning(message)
