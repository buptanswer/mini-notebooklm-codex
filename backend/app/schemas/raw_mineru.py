from typing import Any

from pydantic import Field, model_validator

from app.schemas.common import RawBaseModel


class RawMineruInlinePart(RawBaseModel):
    type: str
    content: str | None = None


class RawMineruImageSource(RawBaseModel):
    path: str | None = None


class RawContentListV2TitleContent(RawBaseModel):
    level: int | None = None
    title_content: list[RawMineruInlinePart] = Field(default_factory=list)


class RawContentListV2ParagraphContent(RawBaseModel):
    paragraph_content: list[RawMineruInlinePart] = Field(default_factory=list)


class RawContentListV2ImageContent(RawBaseModel):
    image_source: RawMineruImageSource | None = None
    image_caption: list[RawMineruInlinePart] = Field(default_factory=list)
    image_footnote: list[RawMineruInlinePart] = Field(default_factory=list)


class RawContentListV2TableContent(RawBaseModel):
    html: str | None = None
    image_source: RawMineruImageSource | None = None
    table_caption: list[RawMineruInlinePart] = Field(default_factory=list)
    table_footnote: list[RawMineruInlinePart] = Field(default_factory=list)
    table_nest_level: int | None = None
    table_type: str | None = None


class RawContentListV2EquationContent(RawBaseModel):
    math_content: str | None = None
    math_type: str | None = None
    image_source: RawMineruImageSource | None = None


class RawContentListV2ListItem(RawBaseModel):
    item_type: str
    item_content: list[RawMineruInlinePart] = Field(default_factory=list)


class RawContentListV2ListContent(RawBaseModel):
    list_type: str | None = None
    list_items: list[RawContentListV2ListItem] = Field(default_factory=list)


class RawContentListV2CodeContent(RawBaseModel):
    code_content: list[RawMineruInlinePart] = Field(default_factory=list)
    code_caption: list[RawMineruInlinePart] = Field(default_factory=list)
    code_language: str | None = None


class RawContentListV2PageHeaderContent(RawBaseModel):
    page_header_content: list[RawMineruInlinePart] = Field(default_factory=list)


class RawContentListV2PageFooterContent(RawBaseModel):
    page_footer_content: list[RawMineruInlinePart] = Field(default_factory=list)


class RawContentListV2PageNumberContent(RawBaseModel):
    page_number_content: list[RawMineruInlinePart] = Field(default_factory=list)


class RawContentListV2PageFootnoteContent(RawBaseModel):
    page_footnote_content: list[RawMineruInlinePart] = Field(default_factory=list)


class RawContentListV2Block(RawBaseModel):
    type: str
    bbox: list[float] | None = None
    content: (
        RawContentListV2TitleContent
        | RawContentListV2ParagraphContent
        | RawContentListV2ImageContent
        | RawContentListV2TableContent
        | RawContentListV2EquationContent
        | RawContentListV2ListContent
        | RawContentListV2CodeContent
        | RawContentListV2PageHeaderContent
        | RawContentListV2PageFooterContent
        | RawContentListV2PageNumberContent
        | RawContentListV2PageFootnoteContent
        | dict[str, Any]
        | list[Any]
        | str
        | None
    ) = None

    @model_validator(mode="before")
    @classmethod
    def coerce_content_by_type(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        block_type = data.get("type")
        content = data.get("content")
        if not isinstance(content, dict):
            return data

        content_model_map = {
            "title": RawContentListV2TitleContent,
            "text": RawContentListV2ParagraphContent,
            "paragraph": RawContentListV2ParagraphContent,
            "image": RawContentListV2ImageContent,
            "table": RawContentListV2TableContent,
            "equation_interline": RawContentListV2EquationContent,
            "list": RawContentListV2ListContent,
            "code": RawContentListV2CodeContent,
            "page_header": RawContentListV2PageHeaderContent,
            "page_footer": RawContentListV2PageFooterContent,
            "page_number": RawContentListV2PageNumberContent,
            "page_footnote": RawContentListV2PageFootnoteContent,
            "footnote": RawContentListV2PageFootnoteContent,
        }

        content_model = content_model_map.get(block_type)
        if content_model is None:
            return data

        cloned = dict(data)
        cloned["content"] = content_model.model_validate(content)
        return cloned


class RawLayoutSpan(RawBaseModel):
    type: str | None = None
    content: str | None = None
    html: str | None = None
    image_path: str | None = None
    text: str | None = None
    bbox: list[float] | None = None
    score: float | int | None = None


class RawLayoutLine(RawBaseModel):
    bbox: list[float] | None = None
    spans: list[RawLayoutSpan] = Field(default_factory=list)


class RawLayoutBlock(RawBaseModel):
    type: str
    bbox: list[float] | None = None
    angle: float | int | None = None
    index: int | None = None
    sub_type: str | None = None
    guess_lang: str | None = None
    cross_page: bool | None = None
    lines_deleted: Any | None = None
    lines: list[RawLayoutLine] = Field(default_factory=list)
    blocks: list["RawLayoutBlock"] = Field(default_factory=list)


RawLayoutBlock.model_rebuild()


class RawLayoutPage(RawBaseModel):
    para_blocks: list[RawLayoutBlock] = Field(default_factory=list)
    discarded_blocks: list[RawLayoutBlock] = Field(default_factory=list)
    page_size: list[float] = Field(default_factory=list)
    page_idx: int


class RawLayoutRoot(RawBaseModel):
    pdf_info: list[RawLayoutPage]
    backend: str | None = Field(default=None, alias="_backend")
    ocr_enable: bool | None = Field(default=None, alias="_ocr_enable")
    vlm_ocr_enable: bool | None = Field(default=None, alias="_vlm_ocr_enable")
    version_name: str | None = Field(default=None, alias="_version_name")


class RawCompatContentBlock(RawBaseModel):
    type: str
    bbox: list[float] | None = None
    page_idx: int | None = None
    text: str | None = None
    text_level: int | None = None
    img_path: str | None = None
    image_caption: list[Any] = Field(default_factory=list)
    image_footnote: list[Any] = Field(default_factory=list)
    table_body: str | None = None
    table_caption: list[Any] = Field(default_factory=list)
    table_footnote: list[Any] = Field(default_factory=list)
    text_format: str | None = None
    sub_type: str | None = None
    list_items: list[Any] = Field(default_factory=list)
    code_body: str | list[Any] | None = None
    code_caption: list[Any] = Field(default_factory=list)
    guess_lang: str | None = None


class RawModelBlock(RawBaseModel):
    type: str
    bbox: list[float] | None = None
    angle: float | int | None = None
    content: str | None = None
    poly: list[float] | None = None
