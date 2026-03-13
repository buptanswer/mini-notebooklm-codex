from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.core.config import Settings, get_settings
from app.schemas.mineru_api import (
    MineruTaskCreateResponse,
    MineruBatchTaskCreateResponse,
    MineruBatchTaskResultItem,
    MineruBatchTaskResultResponse,
    MineruBatchUploadFile,
    MineruBatchUploadRequest,
    MineruBatchUploadResponse,
    MineruBatchUrlFile,
    MineruBatchUrlRequest,
    MineruTaskResultResponse,
    MineruUrlTaskCreateRequest,
)


@dataclass(slots=True)
class LocalMineruFile:
    path: Path
    data_id: str | None = None
    is_ocr: bool | None = None
    page_ranges: str | None = None


@dataclass(slots=True)
class DownloadedBundle:
    file_name: str
    data_id: str | None
    full_zip_url: str
    bundle_zip_path: Path


class MineruClient:
    def __init__(
        self,
        settings: Settings | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        if not self.settings.mineru_api_token:
            raise ValueError("MINERU_API_KEY or MINERU_API_TOKEN is required")

        self._owns_client = http_client is None
        self.client = http_client or httpx.Client(
            base_url=self.settings.mineru_api_base.rstrip("/"),
            headers={
                "Authorization": f"Bearer {self.settings.mineru_api_token}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(60.0, connect=30.0, read=60.0, write=60.0),
            follow_redirects=True,
        )

    def __enter__(self) -> "MineruClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def create_url_task(
        self,
        source_url: str,
        data_id: str | None = None,
        model_version: str | None = None,
    ) -> str:
        payload = MineruUrlTaskCreateRequest(
            url=source_url,
            data_id=data_id,
            model_version=model_version or self.settings.mineru_model_version,
        )
        response = self.client.post(
            "/extract/task",
            content=payload.model_dump_json(by_alias=True, exclude_none=True),
        )
        response.raise_for_status()
        result = MineruTaskCreateResponse.model_validate(response.json())
        self._ensure_success(result.code, result.msg)
        return result.data.task_id

    def create_url_batch_task(
        self,
        source_urls: list[str],
        model_version: str | None = None,
    ) -> str:
        payload = MineruBatchUrlRequest(
            files=[MineruBatchUrlFile(url=url) for url in source_urls],
            model_version=model_version or self.settings.mineru_model_version,
        )
        response = self.client.post(
            "/extract/task/batch",
            content=payload.model_dump_json(by_alias=True, exclude_none=True),
        )
        response.raise_for_status()
        result = MineruBatchTaskCreateResponse.model_validate(response.json())
        self._ensure_success(result.code, result.msg)
        return result.data.batch_id

    def get_task_result(self, task_id: str) -> MineruTaskResultResponse:
        response = self.client.get(f"/extract/task/{task_id}")
        response.raise_for_status()
        result = MineruTaskResultResponse.model_validate(response.json())
        self._ensure_success(result.code, result.msg)
        return result

    def get_batch_results(self, batch_id: str) -> MineruBatchTaskResultResponse:
        response = self.client.get(f"/extract-results/batch/{batch_id}")
        response.raise_for_status()
        result = MineruBatchTaskResultResponse.model_validate(response.json())
        self._ensure_success(result.code, result.msg)
        return result

    def request_batch_upload_urls(
        self,
        files: list[LocalMineruFile],
        model_version: str | None = None,
    ) -> MineruBatchUploadResponse:
        payload = MineruBatchUploadRequest(
            files=[
                MineruBatchUploadFile(
                    name=file.path.name,
                    data_id=file.data_id,
                    is_ocr=file.is_ocr,
                    page_ranges=file.page_ranges,
                )
                for file in files
            ],
            model_version=model_version or self.settings.mineru_model_version,
        )
        response = self.client.post(
            "/file-urls/batch",
            content=payload.model_dump_json(by_alias=True, exclude_none=True),
        )
        response.raise_for_status()
        result = MineruBatchUploadResponse.model_validate(response.json())
        self._ensure_success(result.code, result.msg)
        return result

    def submit_local_files(
        self,
        files: list[LocalMineruFile],
        model_version: str | None = None,
    ) -> tuple[str, list[LocalMineruFile]]:
        prepared_files = [self._prepare_local_file(file) for file in files]
        batch_response = self.request_batch_upload_urls(prepared_files, model_version)
        upload_urls = [str(item) for item in batch_response.data.file_urls]

        if len(upload_urls) != len(prepared_files):
            raise ValueError("MinerU returned a different number of upload urls")

        for upload_url, local_file in zip(upload_urls, prepared_files, strict=True):
            self.upload_file(upload_url, local_file.path)

        return batch_response.data.batch_id, prepared_files

    def submit_single_local_file(
        self,
        file_path: str | Path,
        data_id: str | None = None,
        model_version: str | None = None,
    ) -> tuple[str, LocalMineruFile]:
        batch_id, files = self.submit_local_files(
            [LocalMineruFile(path=Path(file_path), data_id=data_id)],
            model_version=model_version,
        )
        return batch_id, files[0]

    def upload_file(self, upload_url: str, file_path: str | Path) -> None:
        path = Path(file_path)
        with path.open("rb") as file_obj:
            response = httpx.put(
                upload_url,
                content=file_obj.read(),
                headers={},
                timeout=httpx.Timeout(300.0, connect=60.0, read=300.0, write=300.0),
                follow_redirects=True,
            )
        response.raise_for_status()

    def poll_task(
        self,
        task_id: str,
        interval_seconds: int | None = None,
        timeout_seconds: int | None = None,
    ) -> MineruTaskResultResponse:
        interval = interval_seconds or self.settings.mineru_poll_interval_seconds
        timeout = timeout_seconds or self.settings.mineru_poll_timeout_seconds
        started_at = time.monotonic()

        while True:
            result = self.get_task_result(task_id)
            if result.data.state == "done":
                return result
            if result.data.state == "failed":
                raise RuntimeError(
                    f"MinerU task {task_id} failed: {result.data.err_msg or 'unknown'}"
                )
            if time.monotonic() - started_at > timeout:
                raise TimeoutError(f"MinerU task {task_id} timed out after {timeout}s")
            time.sleep(interval)

    def poll_batch(
        self,
        batch_id: str,
        interval_seconds: int | None = None,
        timeout_seconds: int | None = None,
    ) -> MineruBatchTaskResultResponse:
        interval = interval_seconds or self.settings.mineru_poll_interval_seconds
        timeout = timeout_seconds or self.settings.mineru_poll_timeout_seconds
        started_at = time.monotonic()

        while True:
            result = self.get_batch_results(batch_id)
            states = [item.state for item in result.data.extract_result]
            if states and all(state == "done" for state in states):
                return result
            if any(state == "failed" for state in states):
                failed_items = [
                    f"{item.file_name}: {item.err_msg or 'unknown'}"
                    for item in result.data.extract_result
                    if item.state == "failed"
                ]
                raise RuntimeError(
                    f"MinerU batch {batch_id} failed for files: {', '.join(failed_items)}"
                )
            if time.monotonic() - started_at > timeout:
                raise TimeoutError(f"MinerU batch {batch_id} timed out after {timeout}s")
            time.sleep(interval)

    def download_bundle(self, bundle_url: str, destination: str | Path) -> Path:
        destination_path = Path(destination)
        destination_path.parent.mkdir(parents=True, exist_ok=True)

        with httpx.stream(
            "GET",
            bundle_url,
            timeout=httpx.Timeout(300.0, connect=60.0, read=300.0, write=300.0),
            follow_redirects=True,
        ) as response:
            response.raise_for_status()
            with destination_path.open("wb") as output:
                for chunk in response.iter_bytes():
                    output.write(chunk)
        return destination_path

    def download_batch_bundles(
        self,
        batch_result: MineruBatchTaskResultResponse,
        output_dir: str | Path,
    ) -> list[DownloadedBundle]:
        output_root = Path(output_dir)
        output_root.mkdir(parents=True, exist_ok=True)
        downloads: list[DownloadedBundle] = []

        for item in batch_result.data.extract_result:
            downloads.append(self.download_bundle_for_item(item, output_root))
        return downloads

    def download_bundle_for_item(
        self,
        item: MineruBatchTaskResultItem,
        output_dir: str | Path,
    ) -> DownloadedBundle:
        if item.full_zip_url is None:
            raise ValueError(f"MinerU result for {item.file_name} is missing full_zip_url")

        safe_name = self._safe_stem(item.file_name)
        data_suffix = f"-{item.data_id}" if item.data_id else ""
        parsed = urlparse(str(item.full_zip_url))
        extension = Path(parsed.path).suffix or ".zip"
        destination = Path(output_dir) / f"{safe_name}{data_suffix}{extension}"
        bundle_zip_path = self.download_bundle(str(item.full_zip_url), destination)
        return DownloadedBundle(
            file_name=item.file_name,
            data_id=item.data_id,
            full_zip_url=str(item.full_zip_url),
            bundle_zip_path=bundle_zip_path,
        )

    @staticmethod
    def _ensure_success(code: int, msg: str) -> None:
        if code != 0:
            raise RuntimeError(f"MinerU API returned code={code}: {msg}")

    @staticmethod
    def _safe_stem(file_name: str) -> str:
        invalid = '<>:"/\\|?*'
        cleaned = "".join("_" if char in invalid else char for char in Path(file_name).stem)
        return cleaned or "mineru_bundle"

    @staticmethod
    def _prepare_local_file(local_file: LocalMineruFile) -> LocalMineruFile:
        path = local_file.path.expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(path)
        return LocalMineruFile(
            path=path,
            data_id=local_file.data_id or MineruClient._default_data_id(path),
            is_ocr=local_file.is_ocr,
            page_ranges=local_file.page_ranges,
        )

    @staticmethod
    def _default_data_id(path: Path) -> str:
        digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:10]
        suffix = path.suffix.lower().lstrip(".") or "file"
        return f"local-{path.stem}-{suffix}-{digest}"
