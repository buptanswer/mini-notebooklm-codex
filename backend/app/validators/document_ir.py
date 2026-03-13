from app.schemas.ir import DocumentIR


def validate_document_ir(document_ir: DocumentIR) -> None:
    section_ids = {section.section_id for section in document_ir.sections}
    page_ids = {page.page_id for page in document_ir.pages}

    for section in document_ir.sections:
        if (
            section.parent_section_id is not None
            and section.parent_section_id not in section_ids
        ):
            raise ValueError(
                f"section {section.section_id} has missing parent "
                f"{section.parent_section_id}"
            )

    for block in document_ir.blocks:
        if block.section_id not in section_ids:
            raise ValueError(
                f"block {block.block_id} references missing section {block.section_id}"
            )
        if block.anchor is not None and block.anchor.page_id not in page_ids:
            raise ValueError(
                f"block {block.block_id} references missing page {block.anchor.page_id}"
            )
