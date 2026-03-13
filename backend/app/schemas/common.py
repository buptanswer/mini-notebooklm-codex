from typing import Any

from pydantic import BaseModel, ConfigDict, RootModel, field_validator


class RawBaseModel(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        validate_assignment=True,
    )


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class BBoxNorm1000(RootModel[list[float]]):
    @field_validator("root")
    @classmethod
    def validate_root(cls, value: list[float]) -> list[float]:
        if len(value) != 4:
            raise ValueError("bbox_norm1000 must contain 4 coordinates")
        coordinates = [float(item) for item in value]
        if any(item < 0 or item > 1000 for item in coordinates):
            raise ValueError("bbox_norm1000 must stay within 0-1000")
        if coordinates[2] < coordinates[0] or coordinates[3] < coordinates[1]:
            raise ValueError("bbox_norm1000 must satisfy x1 >= x0 and y1 >= y0")
        return coordinates


class BBoxPage(RootModel[list[float]]):
    @field_validator("root")
    @classmethod
    def validate_root(cls, value: list[float]) -> list[float]:
        if len(value) != 4:
            raise ValueError("bbox_page must contain 4 coordinates")
        coordinates = [float(item) for item in value]
        if any(item < 0 for item in coordinates):
            raise ValueError("bbox_page coordinates must be non-negative")
        if coordinates[2] < coordinates[0] or coordinates[3] < coordinates[1]:
            raise ValueError("bbox_page must satisfy x1 >= x0 and y1 >= y0")
        return coordinates


class PageSpan(RootModel[list[int]]):
    @field_validator("root")
    @classmethod
    def validate_root(cls, value: list[int]) -> list[int]:
        if len(value) != 2:
            raise ValueError("page_span must contain 2 positions")
        pages = [int(item) for item in value]
        if pages[0] < 0 or pages[1] < 0:
            raise ValueError("page_span must be non-negative")
        if pages[1] < pages[0]:
            raise ValueError("page_span must satisfy end >= start")
        return pages


def json_friendly(value: Any) -> Any:
    if isinstance(value, RootModel):
        return value.root
    return value
