from typing import Literal

from pydantic import Field, HttpUrl

from app.schemas.common import StrictBaseModel


MineruModelVersion = Literal["pipeline", "vlm", "MinerU-HTML"]
MineruTaskState = Literal[
    "waiting-file",
    "pending",
    "running",
    "failed",
    "converting",
    "done",
]


class MineruUrlTaskCreateRequest(StrictBaseModel):
    url: HttpUrl
    model_version: MineruModelVersion = "vlm"
    is_ocr: bool | None = None
    enable_formula: bool | None = None
    enable_table: bool | None = None
    language: str | None = None
    data_id: str | None = None
    callback: HttpUrl | None = None
    seed: str | None = None
    extra_formats: list[Literal["docx", "html", "latex"]] = Field(default_factory=list)
    page_ranges: str | None = None
    no_cache: bool | None = None
    cache_tolerance: int | None = None


class MineruBatchUploadFile(StrictBaseModel):
    name: str
    data_id: str | None = None
    is_ocr: bool | None = None
    page_ranges: str | None = None


class MineruBatchUploadRequest(StrictBaseModel):
    files: list[MineruBatchUploadFile] = Field(min_length=1, max_length=200)
    model_version: MineruModelVersion = "vlm"
    enable_formula: bool | None = None
    enable_table: bool | None = None
    language: str | None = None
    callback: HttpUrl | None = None
    seed: str | None = None
    extra_formats: list[Literal["docx", "html", "latex"]] = Field(default_factory=list)


class MineruBatchUrlFile(StrictBaseModel):
    url: HttpUrl
    data_id: str | None = None
    is_ocr: bool | None = None
    page_ranges: str | None = None


class MineruBatchUrlRequest(StrictBaseModel):
    files: list[MineruBatchUrlFile] = Field(min_length=1, max_length=200)
    model_version: MineruModelVersion = "vlm"
    enable_formula: bool | None = None
    enable_table: bool | None = None
    language: str | None = None
    callback: HttpUrl | None = None
    seed: str | None = None
    extra_formats: list[Literal["docx", "html", "latex"]] = Field(default_factory=list)
    no_cache: bool | None = None
    cache_tolerance: int | None = None


class MineruTaskCreateData(StrictBaseModel):
    task_id: str


class MineruBatchUploadData(StrictBaseModel):
    batch_id: str
    file_urls: list[HttpUrl]


class MineruBatchTaskCreateData(StrictBaseModel):
    batch_id: str


class MineruApiResponseBase(StrictBaseModel):
    code: int
    msg: str
    trace_id: str


class MineruTaskCreateResponse(MineruApiResponseBase):
    data: MineruTaskCreateData


class MineruBatchUploadResponse(MineruApiResponseBase):
    data: MineruBatchUploadData


class MineruBatchTaskCreateResponse(MineruApiResponseBase):
    data: MineruBatchTaskCreateData


class MineruExtractProgress(StrictBaseModel):
    extracted_pages: int
    total_pages: int
    start_time: str


class MineruTaskResultData(StrictBaseModel):
    task_id: str
    data_id: str | None = None
    state: MineruTaskState
    full_zip_url: HttpUrl | None = None
    err_msg: str = ""
    extract_progress: MineruExtractProgress | None = None


class MineruTaskResultResponse(MineruApiResponseBase):
    data: MineruTaskResultData


class MineruBatchTaskResultItem(StrictBaseModel):
    file_name: str
    state: MineruTaskState
    err_msg: str = ""
    full_zip_url: HttpUrl | None = None
    data_id: str | None = None
    extract_progress: MineruExtractProgress | None = None


class MineruBatchTaskResultData(StrictBaseModel):
    batch_id: str
    extract_result: list[MineruBatchTaskResultItem]


class MineruBatchTaskResultResponse(MineruApiResponseBase):
    data: MineruBatchTaskResultData
