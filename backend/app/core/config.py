from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

TEXT_EMBEDDING_V4_DIMENSIONS = {2048, 1536, 1024, 768, 512, 256, 128, 64}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Mini-NotebookLM API"
    api_v1_prefix: str = "/api/v1"
    debug: bool = False
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )

    project_root: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parents[3]
    )
    storage_root: Path | None = None
    sqlite_path: Path | None = None

    qdrant_mode: Literal["local", "remote"] = "local"
    qdrant_path: Path | None = None
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    qdrant_collection: str = "child_chunks"
    qdrant_vector_size: int = 1024
    qdrant_distance: Literal["Cosine", "Dot", "Euclid"] = "Cosine"

    mineru_api_base: str = "https://mineru.net/api/v4"
    mineru_model_version: str = "vlm"
    mineru_api_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("MINERU_API_KEY", "MINERU_API_TOKEN"),
    )
    mineru_poll_interval_seconds: int = 5
    mineru_poll_timeout_seconds: int = 1800
    dashscope_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "DASHSCOPE_API_KEY",
            "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
        ),
    )
    dashscope_embedding_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_chat_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_rerank_base: str = (
        "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
    )
    embedding_model: str = "text-embedding-v4"
    embedding_dimensions: int = 1024
    embedding_batch_size: int = 10
    rerank_model: str = "qwen3-rerank"
    rerank_top_n: int = 8
    qa_model: str = "qwen3.5-plus"
    enrichment_model: str = "qwen3.5-flash"
    retrieval_vector_top_k: int = 12
    retrieval_keyword_top_k: int = 12
    retrieval_fused_top_k: int = 10
    retrieval_rrf_k: int = 60
    qa_max_sources: int = 5
    qa_max_assets: int = 4
    qa_max_parent_chars: int = 1600
    child_chunk_target_chars: int = 900
    child_chunk_overlap_chars: int = 120

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator(
        "project_root",
        "storage_root",
        "sqlite_path",
        "qdrant_path",
        mode="before",
    )
    @classmethod
    def normalize_optional_paths(cls, value: str | Path | None) -> Path | None:
        if value in (None, ""):
            return None
        return Path(value)

    @field_validator("embedding_batch_size")
    @classmethod
    def validate_embedding_batch_size(cls, value: int) -> int:
        if value < 1 or value > 10:
            raise ValueError(
                "EMBEDDING_BATCH_SIZE must stay within 1-10 for text-embedding-v4"
            )
        return value

    @field_validator(
        "rerank_top_n",
        "retrieval_vector_top_k",
        "retrieval_keyword_top_k",
        "retrieval_fused_top_k",
        "retrieval_rrf_k",
        "qa_max_sources",
        "qa_max_assets",
        "qa_max_parent_chars",
    )
    @classmethod
    def validate_positive_stage4_settings(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("stage4 numeric settings must be positive integers")
        return value

    @model_validator(mode="after")
    def resolve_paths(self) -> "Settings":
        if self.storage_root is None:
            self.storage_root = self.project_root / "storage"
        elif not self.storage_root.is_absolute():
            self.storage_root = self.project_root / self.storage_root

        if self.sqlite_path is None:
            self.sqlite_path = self.storage_root / "sqlite" / "mini_notebooklm.db"
        elif not self.sqlite_path.is_absolute():
            self.sqlite_path = self.project_root / self.sqlite_path

        if self.qdrant_path is None:
            self.qdrant_path = self.storage_root / "qdrant"
        elif not self.qdrant_path.is_absolute():
            self.qdrant_path = self.project_root / self.qdrant_path

        if (
            self.embedding_model == "text-embedding-v4"
            and self.embedding_dimensions not in TEXT_EMBEDDING_V4_DIMENSIONS
        ):
            raise ValueError(
                "EMBEDDING_DIMENSIONS must be one of 2048, 1536, 1024, 768, 512, 256, 128, 64 for text-embedding-v4"
            )

        if self.qdrant_vector_size != self.embedding_dimensions:
            raise ValueError(
                "QDRANT_VECTOR_SIZE must match EMBEDDING_DIMENSIONS for child chunk indexing"
            )

        if self.rerank_top_n > self.retrieval_fused_top_k:
            raise ValueError("RERANK_TOP_N must be <= RETRIEVAL_FUSED_TOP_K")

        if self.qa_max_sources > self.rerank_top_n:
            raise ValueError("QA_MAX_SOURCES must be <= RERANK_TOP_N")

        return self

    @property
    def sqlite_url(self) -> str:
        return f"sqlite:///{self.sqlite_path.as_posix()}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
