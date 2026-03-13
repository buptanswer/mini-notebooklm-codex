from typing import Any, Literal

from pydantic import Field, model_validator

from app.schemas.common import BBoxNorm1000, BBoxPage, PageSpan, StrictBaseModel

SourceFormat = Literal["pdf", "doc", "docx", "ppt", "pptx", "png", "jpg", "jpeg"]
BlockType = Literal[
    "title",
    "paragraph",
    "list",
    "code",
    "table",
    "image",
    "equation",
    "page_header",
    "page_footer",
    "page_number",
    "page_footnote",
    "unknown",
]
BlockRole = Literal["main", "auxiliary"]
AssetType = Literal["image", "table_image", "equation_image"]
LanguageType = Literal["zh", "en", "mixed", "unknown"]


class IRSource(StrictBaseModel):
    doc_id: str
    source_filename: str
    source_format: SourceFormat
    mineru_request_model: str
    mineru_actual_backend: str
    mineru_version_name: str | None = None
    origin_pdf_path: str


class IRBundleRootFiles(StrictBaseModel):
    content_list_v2: str
    layout: str
    full_md: str
    content_list_compat: str | None = None
    model_raw: str | None = None
    origin_pdf: str


class IRBundle(StrictBaseModel):
    root_files: IRBundleRootFiles
    asset_root: str = "images/"
    asset_count: int = 0


class IRDocument(StrictBaseModel):
    title: str | None = None
    language: LanguageType = "unknown"
    page_count: int = Field(ge=0)
    reading_order: Literal["page_then_block"] = "page_then_block"
    has_multimodal: bool = False
    has_code: bool = False
    has_table: bool = False
    has_equation: bool = False
    has_footnote: bool = False


class IRPageSize(StrictBaseModel):
    width: float = Field(ge=0)
    height: float = Field(ge=0)
    unit: Literal["origin_pdf_native"] = "origin_pdf_native"


class IRTextRef(StrictBaseModel):
    text: str
    block_id: str


class IRPageAuxiliary(StrictBaseModel):
    page_headers: list[IRTextRef] = Field(default_factory=list)
    page_footers: list[IRTextRef] = Field(default_factory=list)
    page_numbers: list[IRTextRef] = Field(default_factory=list)


class IRPageFootnote(StrictBaseModel):
    block_id: str
    text: str
    orphan_footnote: bool = False


class IRPage(StrictBaseModel):
    page_id: str
    page_idx: int = Field(ge=0)
    page_size: IRPageSize
    auxiliary: IRPageAuxiliary = Field(default_factory=IRPageAuxiliary)
    footnotes: list[IRPageFootnote] = Field(default_factory=list)
    block_ids: list[str] = Field(default_factory=list)


class IRSection(StrictBaseModel):
    section_id: str
    parent_section_id: str | None = None
    level: int = Field(ge=0)
    title: str | None = None
    header_path: list[str] = Field(default_factory=list)
    synthetic: bool = False
    level_gap: bool = False
    page_span: PageSpan
    child_section_ids: list[str] = Field(default_factory=list)
    block_ids: list[str] = Field(default_factory=list)
    order_start: int = Field(ge=0)
    order_end: int = Field(ge=0)


class IRBlockSegment(StrictBaseModel):
    type: str
    content: str | None = None


class IRAsset(StrictBaseModel):
    asset_id: str
    asset_type: AssetType
    path: str
    usage: str
    mime: str | None = None


class IRAnchorRenderFormula(StrictBaseModel):
    x: str
    y: str


class IRAnchor(StrictBaseModel):
    page_id: str
    origin_pdf_path: str
    coord_space: Literal["origin_pdf_native"] = "origin_pdf_native"
    render_formula: IRAnchorRenderFormula


class IRPageAuxiliaryRef(StrictBaseModel):
    header_block_ids: list[str] = Field(default_factory=list)
    footer_block_ids: list[str] = Field(default_factory=list)
    page_number_block_ids: list[str] = Field(default_factory=list)


class IRBlockMetadata(StrictBaseModel):
    title_level: int | None = Field(default=None, ge=1)
    code_language: str | None = None
    list_type: str | None = None
    math_type: str | None = None
    table_type: str | None = None
    page_auxiliary_ref: IRPageAuxiliaryRef = Field(default_factory=IRPageAuxiliaryRef)


class IRFootnoteLink(StrictBaseModel):
    footnote_block_id: str
    attach_mode: Literal["inline_append", "linked_only"]
    confidence: float = Field(ge=0, le=1)


class IRRawSource(StrictBaseModel):
    source_file: str
    source_type: str
    extra_fields: dict[str, Any] = Field(default_factory=dict)
    content_snapshot: dict[str, Any] | list[Any] | str | None = None


class IRBlockEnrichmentNeighbor(StrictBaseModel):
    prev_paragraphs: list[str] = Field(default_factory=list)
    next_paragraphs: list[str] = Field(default_factory=list)


class IRBlockEnrichment(StrictBaseModel):
    image_caption_text: str | None = None
    image_vlm_description: str | None = None
    table_caption_text: str | None = None
    table_summary: str | None = None
    table_html_available: bool | None = None
    equation_context_text: str | None = None
    neighbor_context: IRBlockEnrichmentNeighbor | None = None
    embedding_text: str | None = None


class IRBlock(StrictBaseModel):
    block_id: str
    page_idx: int = Field(ge=0)
    order_in_page: int = Field(ge=0)
    order_in_doc: int = Field(ge=0)
    section_id: str
    header_path: list[str] = Field(default_factory=list)
    type: BlockType
    subtype: str | None = None
    role: BlockRole
    bbox_norm1000: BBoxNorm1000
    bbox_page: BBoxPage | None = None
    anchor: IRAnchor | None = None
    text: str | None = None
    segments: list[IRBlockSegment] = Field(default_factory=list)
    assets: list[IRAsset] = Field(default_factory=list)
    metadata: IRBlockMetadata = Field(default_factory=IRBlockMetadata)
    footnote_links: list[IRFootnoteLink] = Field(default_factory=list)
    raw_source: IRRawSource
    enrichment: IRBlockEnrichment | None = None

    @model_validator(mode="after")
    def validate_role_and_assets(self) -> "IRBlock":
        if self.role == "main" and self.type not in {
            "page_header",
            "page_footer",
            "page_number",
            "page_footnote",
        } and not self.header_path:
            raise ValueError("main blocks must carry header_path")
        if self.type in {"image", "table"} and not self.assets:
            raise ValueError("image/table blocks must retain at least one asset")
        if self.type == "equation" and not (self.text or self.segments):
            raise ValueError("equation block must retain math content")
        return self


class IRParentChildRelation(StrictBaseModel):
    parent_chunk_id: str
    child_chunk_id: str


class IRFootnoteAttachmentRelation(StrictBaseModel):
    footnote_block_id: str
    target_block_id: str
    attach_mode: Literal["inline_append", "linked_only"]
    confidence: float = Field(ge=0, le=1)


class IRBlockNeighborRelation(StrictBaseModel):
    left_block_id: str
    right_block_id: str


class IRRelations(StrictBaseModel):
    parent_child: list[IRParentChildRelation] = Field(default_factory=list)
    footnote_attachment: list[IRFootnoteAttachmentRelation] = Field(
        default_factory=list
    )
    block_neighbors: list[IRBlockNeighborRelation] = Field(default_factory=list)


class IRQuality(StrictBaseModel):
    title_coverage: float | None = Field(default=None, ge=0, le=1)
    footnote_attach_rate: float | None = Field(default=None, ge=0, le=1)
    table_summary_coverage: float | None = Field(default=None, ge=0, le=1)
    image_vlm_coverage: float | None = Field(default=None, ge=0, le=1)
    ui_anchor_coverage: float | None = Field(default=None, ge=0, le=1)
    degraded_modes: list[str] = Field(default_factory=list)
    ui_anchor_degraded: bool = False
    parser_warnings: list[str] = Field(default_factory=list)


class DocumentIR(StrictBaseModel):
    ir_version: str = "1.0.0"
    pipeline_version: str = "1.0.0"
    source: IRSource
    bundle: IRBundle
    document: IRDocument
    pages: list[IRPage]
    sections: list[IRSection]
    blocks: list[IRBlock]
    relations: IRRelations = Field(default_factory=IRRelations)
    quality: IRQuality = Field(default_factory=IRQuality)
