import json
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel


def write_jsonl(path: str | Path, rows: Iterable[BaseModel]) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file_obj:
        for row in rows:
            file_obj.write(
                json.dumps(
                    row.model_dump(mode="json", by_alias=True, exclude_none=True),
                    ensure_ascii=False,
                )
            )
            file_obj.write("\n")

    return output_path
