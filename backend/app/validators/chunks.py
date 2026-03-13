from app.schemas.chunk import ChildChunk, ParentChunk
from app.schemas.ir import DocumentIR


def validate_chunks(
    document_ir: DocumentIR,
    parent_chunks: list[ParentChunk],
    child_chunks: list[ChildChunk],
) -> None:
    block_ids = {block.block_id: block for block in document_ir.blocks}
    section_ids = {section.section_id for section in document_ir.sections}
    parent_ids = {parent.parent_chunk_id for parent in parent_chunks}

    if len(parent_ids) != len(parent_chunks):
        raise ValueError("parent_chunk_id must be unique")
    if len({child.child_chunk_id for child in child_chunks}) != len(child_chunks):
        raise ValueError("child_chunk_id must be unique")

    for parent in parent_chunks:
        if parent.section_id not in section_ids:
            raise ValueError(f"parent chunk {parent.parent_chunk_id} has invalid section")
        for block_id in parent.block_ids:
            block = block_ids.get(block_id)
            if block is None:
                raise ValueError(f"parent chunk {parent.parent_chunk_id} references missing block {block_id}")
            if block.role != "main":
                raise ValueError(f"parent chunk {parent.parent_chunk_id} cannot include auxiliary block {block_id}")

    for child in child_chunks:
        if child.parent_chunk_id not in parent_ids:
            raise ValueError(f"child chunk {child.child_chunk_id} references missing parent")
        if child.section_id not in section_ids:
            raise ValueError(f"child chunk {child.child_chunk_id} has invalid section")
        for block_id in child.source_block_ids:
            block = block_ids.get(block_id)
            if block is None:
                raise ValueError(f"child chunk {child.child_chunk_id} references missing block {block_id}")
            if block.role != "main":
                raise ValueError(f"child chunk {child.child_chunk_id} cannot include auxiliary block {block_id}")
