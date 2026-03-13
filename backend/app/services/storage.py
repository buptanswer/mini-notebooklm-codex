from pathlib import Path
import shutil

from app.core.config import Settings


class StorageManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def ensure_roots(self) -> None:
        for path in (
            self.settings.storage_root,
            self.settings.sqlite_path.parent,
            self.settings.qdrant_path,
            self.knowledge_base_root,
        ):
            path.mkdir(parents=True, exist_ok=True)

    @property
    def knowledge_base_root(self) -> Path:
        return self.settings.storage_root / "knowledge_bases"

    def knowledge_base_path(self, knowledge_base_id: str) -> Path:
        return self.knowledge_base_root / knowledge_base_id

    def ensure_knowledge_base_tree(self, knowledge_base_id: str) -> Path:
        kb_root = self.knowledge_base_path(knowledge_base_id)
        for subdir in (
            kb_root / "uploads",
            kb_root / "mineru_bundles",
            kb_root / "origin_pdf",
            kb_root / "assets",
            kb_root / "ir",
            kb_root / "chunks",
            kb_root / "cache",
        ):
            subdir.mkdir(parents=True, exist_ok=True)
        return kb_root

    def uploads_root(self, knowledge_base_id: str) -> Path:
        return self.ensure_knowledge_base_tree(knowledge_base_id) / "uploads"

    def delete_knowledge_base_tree(self, knowledge_base_id: str) -> None:
        kb_root = self.knowledge_base_path(knowledge_base_id)
        if kb_root.exists():
            shutil.rmtree(kb_root)

    def delete_path_if_exists(self, path: str | Path) -> None:
        target = Path(path)
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        elif target.exists():
            target.unlink(missing_ok=True)
