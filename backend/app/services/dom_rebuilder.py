from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.ir import DocumentIR, IRBlock, IRSection


@dataclass(slots=True)
class SectionNode:
    section: IRSection
    parent_section_id: str | None
    child_section_ids: list[str] = field(default_factory=list)
    direct_block_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DocumentDOM:
    document_ir: DocumentIR
    sections: dict[str, SectionNode]
    blocks: dict[str, IRBlock]
    root_section_ids: list[str]

    def ordered_sections(self) -> list[SectionNode]:
        return sorted(
            self.sections.values(),
            key=lambda item: (item.section.order_start, item.section.level, item.section.section_id),
        )

    def direct_main_blocks(self, section_id: str) -> list[IRBlock]:
        node = self.sections[section_id]
        blocks = [self.blocks[block_id] for block_id in node.direct_block_ids]
        return [block for block in blocks if block.role == "main"]


class DOMRebuilder:
    def rebuild(self, document_ir: DocumentIR) -> DocumentDOM:
        blocks = {block.block_id: block for block in document_ir.blocks}
        sections: dict[str, SectionNode] = {}

        for section in document_ir.sections:
            sections[section.section_id] = SectionNode(
                section=section,
                parent_section_id=section.parent_section_id,
                child_section_ids=list(section.child_section_ids),
                direct_block_ids=list(section.block_ids),
            )

        root_section_ids = [
            node.section.section_id
            for node in sections.values()
            if node.parent_section_id is None
        ]

        return DocumentDOM(
            document_ir=document_ir,
            sections=sections,
            blocks=blocks,
            root_section_ids=root_section_ids,
        )
