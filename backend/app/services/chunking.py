from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.schemas.chunk import (
    ChildChunk,
    ChildChunkMetadata,
    ChunkAssetRef,
    ParentChunk,
    ParentChunkMetadata,
)
from app.schemas.ir import DocumentIR, IRBlock
from app.services.dom_rebuilder import DOMRebuilder

AUXILIARY_BLOCK_TYPES = {
    "page_header",
    "page_footer",
    "page_number",
    "page_footnote",
}

ATOMIC_BLOCK_TYPES = {"list", "code", "image", "table", "equation"}


@dataclass(slots=True)
class ChunkingResult:
    parents: list[ParentChunk]
    children: list[ChildChunk]


class StructureAwareChunker:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.dom_rebuilder = DOMRebuilder()

    def chunk_document(self, document_ir: DocumentIR) -> ChunkingResult:
        dom = self.dom_rebuilder.rebuild(document_ir)

        parents: list[ParentChunk] = []
        children: list[ChildChunk] = []

        for section_node in dom.ordered_sections():
            section = section_node.section
            if section.synthetic and not section.block_ids:
                continue

            direct_blocks = [
                block
                for block in dom.direct_main_blocks(section.section_id)
                if block.type not in AUXILIARY_BLOCK_TYPES and block.type != "unknown"
            ]
            if not direct_blocks:
                continue

            parent_chunk = self._build_parent_chunk(document_ir, section, direct_blocks)
            parents.append(parent_chunk)
            children.extend(self._build_child_chunks(parent_chunk, direct_blocks))

        return ChunkingResult(parents=parents, children=children)

    def _build_parent_chunk(
        self,
        document_ir: DocumentIR,
        section,
        direct_blocks: list[IRBlock],
    ) -> ParentChunk:
        header_path = section.header_path or [section.title or document_ir.document.title or "无标题文档"]
        page_numbers = self._page_numbers_for_blocks(document_ir, direct_blocks)
        page_headers = self._page_auxiliary_texts(document_ir, direct_blocks, "page_headers")
        page_footers = self._page_auxiliary_texts(document_ir, direct_blocks, "page_footers")
        orphan_footnote_ids: list[str] = []
        text_parts = [
            self._block_text_for_parent(block)
            for block in direct_blocks
            if self._block_text_for_parent(block)
        ]
        page_span = [min(block.page_idx for block in direct_blocks), max(block.page_idx for block in direct_blocks)]

        return ParentChunk(
            parent_chunk_id=f"pc_{document_ir.source.doc_id[:8]}_{section.section_id}",
            doc_id=document_ir.source.doc_id,
            section_id=section.section_id,
            header_path=header_path,
            title=section.title,
            page_span=page_span,
            block_ids=[block.block_id for block in direct_blocks],
            text_for_generation="\n\n".join(text_parts).strip(),
            assets=self._collect_assets(direct_blocks),
            metadata=ParentChunkMetadata(
                page_headers=page_headers,
                page_footers=page_footers,
                page_numbers=page_numbers,
                orphan_footnote_ids=orphan_footnote_ids,
            ),
        )

    def _build_child_chunks(
        self,
        parent_chunk: ParentChunk,
        direct_blocks: list[IRBlock],
    ) -> list[ChildChunk]:
        children: list[ChildChunk] = []
        header_text = " > ".join(parent_chunk.header_path)
        child_index = 1

        for block in direct_blocks:
            if block.type == "title":
                continue
            if block.type == "paragraph":
                fragments = self._split_paragraph(block.text or "")
                for fragment in fragments:
                    if not fragment.strip():
                        continue
                    children.append(
                        ChildChunk(
                            child_chunk_id=f"{parent_chunk.parent_chunk_id}_c{child_index:03d}",
                            parent_chunk_id=parent_chunk.parent_chunk_id,
                            doc_id=parent_chunk.doc_id,
                            section_id=parent_chunk.section_id,
                            header_path=parent_chunk.header_path,
                            chunk_type="paragraph",
                            page_span=[block.page_idx, block.page_idx],
                            source_block_ids=[block.block_id],
                            embedding_text=self._compose_embedding_text(header_text, fragment),
                            retrieval_text=fragment,
                            assets=self._collect_assets([block]),
                            metadata=ChildChunkMetadata(
                                page_numbers=[str(block.page_idx + 1)],
                                is_atomic=False,
                            ),
                        )
                    )
                    child_index += 1
                continue

            if block.type in ATOMIC_BLOCK_TYPES:
                chunk_type = "paragraph" if block.type == "title" else block.type
                body_text = self._block_text_for_child(block)
                if not body_text:
                    continue

                if block.type == "code":
                    fragments = self._split_code_block(body_text)
                    if len(fragments) > 1:
                        for fragment_index, fragment in enumerate(fragments, start=1):
                            children.append(
                                ChildChunk(
                                    child_chunk_id=f"{parent_chunk.parent_chunk_id}_c{child_index:03d}",
                                    parent_chunk_id=parent_chunk.parent_chunk_id,
                                    doc_id=parent_chunk.doc_id,
                                    section_id=parent_chunk.section_id,
                                    header_path=parent_chunk.header_path,
                                    chunk_type="code",
                                    page_span=[block.page_idx, block.page_idx],
                                    source_block_ids=[block.block_id],
                                    embedding_text=self._compose_embedding_text(header_text, fragment),
                                    retrieval_text=fragment,
                                    assets=self._collect_assets([block]),
                                    metadata=ChildChunkMetadata(
                                        page_numbers=[str(block.page_idx + 1)],
                                        code_language=block.metadata.code_language,
                                        is_atomic=True,
                                        is_atomic_fragment=True,
                                        fragment_index=fragment_index,
                                        fragment_total=len(fragments),
                                    ),
                                )
                            )
                            child_index += 1
                        continue

                children.append(
                    ChildChunk(
                        child_chunk_id=f"{parent_chunk.parent_chunk_id}_c{child_index:03d}",
                        parent_chunk_id=parent_chunk.parent_chunk_id,
                        doc_id=parent_chunk.doc_id,
                        section_id=parent_chunk.section_id,
                        header_path=parent_chunk.header_path,
                        chunk_type=chunk_type,
                        page_span=[block.page_idx, block.page_idx],
                        source_block_ids=[block.block_id],
                        embedding_text=self._compose_embedding_text(header_text, body_text),
                        retrieval_text=body_text,
                        assets=self._collect_assets([block]),
                        metadata=ChildChunkMetadata(
                            page_numbers=[str(block.page_idx + 1)],
                            code_language=block.metadata.code_language,
                            is_atomic=True,
                            enrichment_status=(
                                "ready"
                                if block.enrichment and block.enrichment.embedding_text
                                else "none"
                            ),
                        ),
                    )
                )
                child_index += 1

        return children

    def _split_paragraph(self, text: str) -> list[str]:
        cleaned = re.sub(r"\s+", " ", text).strip()
        if len(cleaned) <= self.settings.child_chunk_target_chars:
            return [cleaned] if cleaned else []

        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[。！？!?\.；;])\s+", cleaned)
            if sentence.strip()
        ]
        if not sentences:
            return [cleaned]

        target = self.settings.child_chunk_target_chars
        overlap = self.settings.child_chunk_overlap_chars
        chunks: list[str] = []
        current = ""

        for sentence in sentences:
            candidate = f"{current} {sentence}".strip() if current else sentence
            if len(candidate) <= target:
                current = candidate
                continue
            if current:
                chunks.append(current)
            current = sentence

        if current:
            chunks.append(current)

        if overlap <= 0 or len(chunks) <= 1:
            return chunks

        overlapped: list[str] = []
        for index, chunk in enumerate(chunks):
            if index == 0:
                overlapped.append(chunk)
                continue
            prefix = chunks[index - 1][-overlap:]
            overlapped.append(f"{prefix} {chunk}".strip())
        return overlapped

    def _split_code_block(self, text: str) -> list[str]:
        if len(text) <= self.settings.child_chunk_target_chars * 2:
            return [text]

        lines = text.splitlines()
        fragments: list[str] = []
        buffer: list[str] = []
        max_chars = self.settings.child_chunk_target_chars * 2

        for line in lines:
            candidate = "\n".join([*buffer, line]).strip()
            if buffer and len(candidate) > max_chars:
                fragments.append("\n".join(buffer).strip())
                buffer = [line]
            else:
                buffer.append(line)

        if buffer:
            fragments.append("\n".join(buffer).strip())
        return [fragment for fragment in fragments if fragment]

    def _block_text_for_parent(self, block: IRBlock) -> str:
        return self._block_text_for_child(block)

    def _block_text_for_child(self, block: IRBlock) -> str:
        if block.enrichment and block.enrichment.embedding_text:
            return block.enrichment.embedding_text.strip()
        text = (block.text or "").strip()
        if text:
            return text
        if block.assets:
            asset_hint = " ".join(asset.path for asset in block.assets)
            return f"{block.type}: {asset_hint}".strip()
        return ""

    def _compose_embedding_text(self, header_text: str, body: str) -> str:
        return f"{header_text}\n{body}".strip()

    def _collect_assets(self, blocks: list[IRBlock]) -> list[ChunkAssetRef]:
        seen: set[str] = set()
        assets: list[ChunkAssetRef] = []
        for block in blocks:
            for asset in block.assets:
                if asset.asset_id in seen:
                    continue
                seen.add(asset.asset_id)
                assets.append(
                    ChunkAssetRef(
                        asset_id=asset.asset_id,
                        asset_type=asset.asset_type,
                        path=asset.path,
                    )
                )
        return assets

    def _page_numbers_for_blocks(self, document_ir: DocumentIR, blocks: list[IRBlock]) -> list[str]:
        pages = {block.page_idx for block in blocks}
        numbers: list[str] = []
        for page in document_ir.pages:
            if page.page_idx not in pages:
                continue
            for item in page.auxiliary.page_numbers:
                if item.text not in numbers:
                    numbers.append(item.text)
        return numbers or [str(page_idx + 1) for page_idx in sorted(pages)]

    def _page_auxiliary_texts(self, document_ir: DocumentIR, blocks: list[IRBlock], field_name: str) -> list[str]:
        pages = {block.page_idx for block in blocks}
        texts: list[str] = []
        for page in document_ir.pages:
            if page.page_idx not in pages:
                continue
            items = getattr(page.auxiliary, field_name)
            for item in items:
                if item.text not in texts:
                    texts.append(item.text)
        return texts
