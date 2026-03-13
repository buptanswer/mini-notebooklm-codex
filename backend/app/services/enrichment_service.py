from __future__ import annotations

import base64
import mimetypes
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings, get_settings
from app.schemas.chat_api import ChatMessage, ChatMessageContentPart
from app.schemas.ir import (
    DocumentIR,
    IRBlock,
    IRBlockEnrichment,
    IRBlockEnrichmentNeighbor,
)
from app.services.chat_client import DashScopeChatClient
from app.writers import write_json


@dataclass(slots=True)
class EnrichmentArtifacts:
    document_ir: DocumentIR
    enriched_ir_path: Path
    image_enriched_count: int
    table_enriched_count: int


class DocumentEnrichmentService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def enrich_document(
        self,
        *,
        document_ir_path: str | Path,
        bundle_root: str | Path,
        output_path: str | Path | None = None,
    ) -> EnrichmentArtifacts:
        ir_path = Path(document_ir_path)
        document_ir = DocumentIR.model_validate_json(ir_path.read_text(encoding="utf-8"))
        blocks = [block.model_copy(deep=True) for block in document_ir.blocks]

        image_total = sum(1 for block in blocks if block.type == "image")
        table_total = sum(1 for block in blocks if block.type == "table")
        image_enriched_count = 0
        table_enriched_count = 0
        degraded_modes = list(document_ir.quality.degraded_modes)

        for index, block in enumerate(blocks):
            enrichment = self._build_base_enrichment(blocks, index)
            try:
                if block.type == "image":
                    description = self._describe_image(block, bundle_root, enrichment)
                    if description:
                        enrichment.image_vlm_description = description
                        image_enriched_count += 1
                    enrichment.embedding_text = self._compose_image_embedding_text(block, enrichment)
                elif block.type == "table":
                    summary = self._summarize_table(block, bundle_root, enrichment)
                    if summary:
                        enrichment.table_summary = summary
                        table_enriched_count += 1
                    enrichment.table_html_available = any(
                        segment.type == "table_html" and (segment.content or "").strip()
                        for segment in block.segments
                    )
                    enrichment.embedding_text = self._compose_table_embedding_text(block, enrichment)
                elif block.type == "equation":
                    enrichment.equation_context_text = self._neighbor_text(enrichment.neighbor_context)
                    enrichment.embedding_text = self._compose_equation_embedding_text(block, enrichment)
                else:
                    continue
            except Exception:
                degraded_modes.append(f"enrichment_fallback:{block.block_id}")
                if block.type == "image":
                    enrichment.embedding_text = self._compose_image_embedding_text(block, enrichment)
                elif block.type == "table":
                    enrichment.table_html_available = any(
                        segment.type == "table_html" and (segment.content or "").strip()
                        for segment in block.segments
                    )
                    enrichment.embedding_text = self._compose_table_embedding_text(block, enrichment)
                elif block.type == "equation":
                    enrichment.equation_context_text = self._neighbor_text(enrichment.neighbor_context)
                    enrichment.embedding_text = self._compose_equation_embedding_text(block, enrichment)
            block.enrichment = enrichment

        enriched = document_ir.model_copy(update={"blocks": blocks}, deep=True)
        enriched.quality.degraded_modes = degraded_modes
        enriched.quality.image_vlm_coverage = self._ratio(image_enriched_count, image_total)
        enriched.quality.table_summary_coverage = self._ratio(table_enriched_count, table_total)

        target_path = Path(output_path) if output_path else Path(bundle_root) / "document_ir_enriched.json"
        write_json(target_path, enriched.model_dump(mode="json"))
        return EnrichmentArtifacts(
            document_ir=enriched,
            enriched_ir_path=target_path,
            image_enriched_count=image_enriched_count,
            table_enriched_count=table_enriched_count,
        )

    def _build_base_enrichment(self, blocks: list[IRBlock], index: int) -> IRBlockEnrichment:
        block = blocks[index]
        prev_paragraphs: list[str] = []
        next_paragraphs: list[str] = []
        probe = index - 1
        while probe >= 0 and len(prev_paragraphs) < 2:
            candidate = blocks[probe]
            if candidate.section_id != block.section_id:
                break
            if candidate.type == "paragraph" and candidate.text:
                prev_paragraphs.insert(0, candidate.text.strip())
            probe -= 1

        probe = index + 1
        while probe < len(blocks) and len(next_paragraphs) < 2:
            candidate = blocks[probe]
            if candidate.section_id != block.section_id:
                break
            if candidate.type == "paragraph" and candidate.text:
                next_paragraphs.append(candidate.text.strip())
            probe += 1

        return IRBlockEnrichment(
            image_caption_text=self._segment_text(block, "caption") if block.type == "image" else None,
            table_caption_text=self._segment_text(block, "caption") if block.type == "table" else None,
            neighbor_context=IRBlockEnrichmentNeighbor(
                prev_paragraphs=prev_paragraphs,
                next_paragraphs=next_paragraphs,
            ),
        )

    def _describe_image(
        self,
        block: IRBlock,
        bundle_root: str | Path,
        enrichment: IRBlockEnrichment,
    ) -> str | None:
        asset_url = self._asset_to_data_url(block, bundle_root)
        context_text = self._neighbor_text(enrichment.neighbor_context)
        caption = enrichment.image_caption_text or block.text or ""
        if asset_url is None:
            return self._compact_text(" ".join(part for part in [caption, context_text] if part))

        messages = [
            ChatMessage(
                role="user",
                content=[
                    ChatMessageContentPart(
                        type="text",
                        text=(
                            "请面向课程知识库检索，简洁总结这张图片的核心信息。"
                            "输出 2 句以内自然语言，不要空话。"
                            f"\n标题路径：{' > '.join(block.header_path)}"
                            f"\n图片说明：{caption or '无'}"
                            f"\n上下文：{context_text or '无'}"
                        ),
                    ),
                    ChatMessageContentPart(type="image_url", image_url={"url": asset_url}),
                ],
            )
        ]
        with DashScopeChatClient(self.settings) as client:
            result = client.chat(messages, model=self.settings.enrichment_model)
        return self._compact_text(result.content)

    def _summarize_table(
        self,
        block: IRBlock,
        bundle_root: str | Path,
        enrichment: IRBlockEnrichment,
    ) -> str | None:
        caption = enrichment.table_caption_text or ""
        table_text = " ".join(
            segment.content.strip()
            for segment in block.segments
            if segment.content and segment.type in {"table_html", "footnote", "caption"}
        )
        context_text = self._neighbor_text(enrichment.neighbor_context)
        asset_url = self._asset_to_data_url(block, bundle_root)
        parts = [
            ChatMessageContentPart(
                type="text",
                text=(
                    "请把这张表格总结成适合知识库检索的短摘要。"
                    "优先提炼主题、关键列和关键结论，输出 2 到 4 句自然语言。"
                    f"\n标题路径：{' > '.join(block.header_path)}"
                    f"\n表格标题：{caption or '无'}"
                    f"\n表格文本：{table_text or '无'}"
                    f"\n上下文：{context_text or '无'}"
                ),
            )
        ]
        if asset_url is not None:
            parts.append(ChatMessageContentPart(type="image_url", image_url={"url": asset_url}))

        with DashScopeChatClient(self.settings) as client:
            result = client.chat(
                [ChatMessage(role="user", content=parts)],
                model=self.settings.enrichment_model,
            )
        return self._compact_text(result.content)

    def _compose_image_embedding_text(self, block: IRBlock, enrichment: IRBlockEnrichment) -> str:
        return self._compact_text(
            "\n".join(
                part
                for part in [
                    " > ".join(block.header_path),
                    enrichment.image_caption_text or "",
                    enrichment.image_vlm_description or "",
                    self._neighbor_text(enrichment.neighbor_context),
                ]
                if part
            )
        )

    def _compose_table_embedding_text(self, block: IRBlock, enrichment: IRBlockEnrichment) -> str:
        table_text = " ".join(
            segment.content.strip()
            for segment in block.segments
            if segment.content and segment.type in {"table_html", "footnote"}
        )
        return self._compact_text(
            "\n".join(
                part
                for part in [
                    " > ".join(block.header_path),
                    enrichment.table_caption_text or "",
                    enrichment.table_summary or "",
                    table_text,
                    self._neighbor_text(enrichment.neighbor_context),
                ]
                if part
            )
        )

    def _compose_equation_embedding_text(self, block: IRBlock, enrichment: IRBlockEnrichment) -> str:
        return self._compact_text(
            "\n".join(
                part
                for part in [
                    " > ".join(block.header_path),
                    block.text or "",
                    enrichment.equation_context_text or "",
                ]
                if part
            )
        )

    def _segment_text(self, block: IRBlock, segment_type: str) -> str | None:
        texts = [
            (segment.content or "").strip()
            for segment in block.segments
            if segment.type == segment_type and (segment.content or "").strip()
        ]
        if not texts:
            return None
        return self._compact_text(" ".join(texts))

    def _neighbor_text(self, neighbor: IRBlockEnrichmentNeighbor | None) -> str:
        if neighbor is None:
            return ""
        return self._compact_text(" ".join([*neighbor.prev_paragraphs, *neighbor.next_paragraphs]))

    def _asset_to_data_url(self, block: IRBlock, bundle_root: str | Path) -> str | None:
        if not block.assets:
            return None
        asset = block.assets[0]
        path = (Path(bundle_root) / asset.path).resolve()
        if not path.exists() or not path.is_file() or path.stat().st_size > 7 * 1024 * 1024:
            return None
        mime_type, _ = mimetypes.guess_type(path.name)
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime_type or 'image/jpeg'};base64,{encoded}"

    def _compact_text(self, value: str) -> str:
        return " ".join(value.split()).strip()

    def _ratio(self, numerator: int, denominator: int) -> float | None:
        if denominator <= 0:
            return None
        return round(numerator / denominator, 4)
