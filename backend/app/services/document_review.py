from dataclasses import dataclass

from app.schemas.ir import DocumentIR


@dataclass(slots=True)
class DocumentReviewResult:
    review_status: str
    parser_warning_count: int
    unknown_block_count: int
    review_summary: str | None


def inspect_document_ir(document_ir: DocumentIR) -> DocumentReviewResult:
    parser_warning_count = len(document_ir.quality.parser_warnings)
    unknown_block_count = sum(1 for block in document_ir.blocks if block.type == "unknown")

    if parser_warning_count or unknown_block_count:
        summary_parts: list[str] = []
        if parser_warning_count:
            summary_parts.append(f"{parser_warning_count} 条 parser warning")
        if unknown_block_count:
            summary_parts.append(f"{unknown_block_count} 个 unknown block")
        summary = "，".join(summary_parts) + "。请检查 document_ir.json 和 MinerU 原始输出。"
        return DocumentReviewResult(
            review_status="needs_review",
            parser_warning_count=parser_warning_count,
            unknown_block_count=unknown_block_count,
            review_summary=summary,
        )

    return DocumentReviewResult(
        review_status="ok",
        parser_warning_count=0,
        unknown_block_count=0,
        review_summary=None,
    )
