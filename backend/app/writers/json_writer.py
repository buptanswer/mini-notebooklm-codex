import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def write_json(path: str | Path, payload: BaseModel | dict[str, Any] | list[Any]) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(payload, BaseModel):
        serializable: Any = payload.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        )
    else:
        serializable = payload

    output_path.write_text(
        json.dumps(serializable, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path
