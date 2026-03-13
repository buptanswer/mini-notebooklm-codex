from __future__ import annotations

import shutil
from pathlib import Path, PurePosixPath

from sqlalchemy.orm import Session

from app.db.models import DocumentORM
from app.repositories.documents import DocumentRepository
from app.repositories.knowledge_bases import KnowledgeBaseRepository
from app.services.qdrant_manager import QdrantManager
from app.services.storage import StorageManager


class FileManagerService:
    def __init__(
        self,
        *,
        storage_manager: StorageManager,
        qdrant_manager: QdrantManager | None = None,
    ) -> None:
        self.storage_manager = storage_manager
        self.qdrant_manager = qdrant_manager

    def move_document(
        self,
        session: Session,
        *,
        knowledge_base_id: str,
        document_id: str,
        new_name: str | None,
        new_parent_path: str | None,
    ):
        repository = DocumentRepository(session)
        entity = repository.get_entity(document_id)
        if entity is None or entity.knowledge_base_id != knowledge_base_id:
            raise ValueError(f"document `{document_id}` not found")

        current_relative = entity.source_relative_path or entity.source_filename
        current_parent = PurePosixPath(current_relative).parent
        if str(current_parent) == ".":
            current_parent = PurePosixPath("")

        target_name = (new_name or PurePosixPath(current_relative).name).strip()
        target_parent = self._sanitize_relative_path(new_parent_path or current_parent.as_posix())
        target_relative = self._join_relative_path(target_parent, target_name)
        target_path = self.storage_manager.uploads_root(knowledge_base_id) / target_relative
        self._move_file(Path(entity.source_path), target_path)
        self._prune_empty_directories(Path(entity.source_path).parent, self.storage_manager.uploads_root(knowledge_base_id))
        return repository.update_relative_path(document_id, target_relative.as_posix(), target_path)

    def delete_document(self, session: Session, *, knowledge_base_id: str, document_id: str):
        repository = DocumentRepository(session)
        entity = repository.get_entity(document_id)
        if entity is None or entity.knowledge_base_id != knowledge_base_id:
            raise ValueError(f"document `{document_id}` not found")

        self._delete_document_artifacts(entity)
        return repository.delete(document_id)

    def bulk_delete_documents(
        self,
        session: Session,
        *,
        knowledge_base_id: str,
        document_ids: list[str],
    ) -> list[str]:
        deleted_ids: list[str] = []
        for document_id in document_ids:
            self.delete_document(session, knowledge_base_id=knowledge_base_id, document_id=document_id)
            deleted_ids.append(document_id)
        return deleted_ids

    def rename_folder(
        self,
        session: Session,
        *,
        knowledge_base_id: str,
        folder_path: str,
        new_folder_path: str,
    ) -> list[str]:
        repository = DocumentRepository(session)
        old_prefix = self._sanitize_relative_path(folder_path).as_posix()
        new_prefix = self._sanitize_relative_path(new_folder_path).as_posix()
        entities = repository.list_by_prefix(knowledge_base_id, old_prefix)
        if not entities:
            raise ValueError(f"folder `{folder_path}` not found")

        moved_ids: list[str] = []
        for entity in entities:
            suffix = entity.source_relative_path[len(old_prefix):].lstrip("/\\")
            target_relative = PurePosixPath(new_prefix) / PurePosixPath(suffix)
            target_path = self.storage_manager.uploads_root(knowledge_base_id) / target_relative
            self._move_file(Path(entity.source_path), target_path)
            repository.update_relative_path(entity.id, target_relative.as_posix(), target_path)
            moved_ids.append(entity.id)
        return moved_ids

    def delete_folder(
        self,
        session: Session,
        *,
        knowledge_base_id: str,
        folder_path: str,
    ) -> list[str]:
        repository = DocumentRepository(session)
        prefix = self._sanitize_relative_path(folder_path).as_posix()
        entities = repository.list_by_prefix(knowledge_base_id, prefix)
        if not entities:
            raise ValueError(f"folder `{folder_path}` not found")

        deleted_ids: list[str] = []
        for entity in list(entities):
            self._delete_document_artifacts(entity)
            repository.delete(entity.id)
            deleted_ids.append(entity.id)
        return deleted_ids

    def delete_knowledge_base(self, session: Session, *, knowledge_base_id: str):
        kb_repository = KnowledgeBaseRepository(session)
        kb_entity = kb_repository.get_entity(knowledge_base_id)
        if kb_entity is None:
            raise ValueError(f"knowledge base `{knowledge_base_id}` not found")

        documents = list(kb_entity.documents)
        for document in documents:
            self._delete_document_artifacts(document, delete_source=False)

        summary = kb_repository.delete(knowledge_base_id)
        self.storage_manager.delete_knowledge_base_tree(knowledge_base_id)
        return summary

    def _delete_document_artifacts(self, entity: DocumentORM, *, delete_source: bool = True) -> None:
        if self.qdrant_manager is not None and entity.source_sha1:
            self.qdrant_manager.delete_document_chunks(entity.source_sha1)

        if delete_source and entity.source_path:
            source_path = Path(entity.source_path)
            if source_path.exists():
                source_path.unlink(missing_ok=True)
                stop_dir = next(
                    (parent for parent in source_path.parents if parent.name == "uploads"),
                    source_path.parent,
                )
                self._prune_empty_directories(source_path.parent, stop_dir)

        if entity.bundle_root:
            bundle_root = Path(entity.bundle_root)
            if bundle_root.exists():
                shutil.rmtree(bundle_root, ignore_errors=True)

    def _move_file(self, source_path: Path, target_path: Path) -> None:
        if source_path.resolve() == target_path.resolve():
            return
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if source_path.exists():
            shutil.move(str(source_path), str(target_path))

    def _prune_empty_directories(self, start_dir: Path, stop_dir: Path) -> None:
        current = start_dir
        stop_resolved = stop_dir.resolve()
        while current.exists() and current.resolve() != stop_resolved:
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent

    def _sanitize_relative_path(self, raw_path: str) -> PurePosixPath:
        normalized = raw_path.replace("\\", "/").strip("/")
        if not normalized:
            return PurePosixPath("")
        relative = PurePosixPath(normalized)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"invalid relative path: {raw_path}")
        return relative

    def _join_relative_path(self, parent: PurePosixPath, name: str) -> PurePosixPath:
        cleaned_name = name.strip().replace("\\", "/").strip("/")
        if not cleaned_name or "/" in cleaned_name:
            raise ValueError(f"invalid file name: {name}")
        return parent / cleaned_name if parent.parts else PurePosixPath(cleaned_name)
