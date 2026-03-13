from __future__ import annotations

import base64
import mimetypes
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.schemas.chat_api import ChatMessage, ChatMessageContentPart
from app.schemas.qa import (
    AnswerSource,
    AnswerUsage,
    AskRequest,
    AskResponse,
    RetrievalTraceHit,
    SourceAnchorBlock,
    SourceAsset,
)
from app.schemas.rerank_api import TextRerankResult
from app.services.chat_client import ChatResult, ChatStreamChunk, DashScopeChatClient
from app.services.rerank_client import DashScopeRerankClient
from app.services.retrieval_service import HybridRetrievalService, RetrievedCandidate


@dataclass(slots=True)
class QAContextSource:
    source: AnswerSource
    candidate: RetrievedCandidate


@dataclass(slots=True)
class PreparedAnswer:
    question: str
    sources: list[QAContextSource]
    fused_candidates: list[RetrievedCandidate]
    reranked_candidates: list[RetrievedCandidate]
    messages: list[ChatMessage]
    rerank_tokens: int | None


class QAService:
    def __init__(
        self,
        settings: Settings | None = None,
        retrieval_service: HybridRetrievalService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.retrieval_service = retrieval_service or HybridRetrievalService(self.settings)
        self._ir_cache: dict[str, dict[str, dict]] = {}

    def ask(
        self,
        session: Session,
        knowledge_base_id: str,
        payload: AskRequest,
    ) -> AskResponse:
        prepared = self.prepare_answer(session, knowledge_base_id, payload)
        with DashScopeChatClient(self.settings) as client:
            chat_result = client.chat(prepared.messages)

        return AskResponse(
            knowledge_base_id=knowledge_base_id,
            question=payload.question,
            answer=chat_result.content,
            answer_model=chat_result.model,
            rerank_model=self.settings.rerank_model,
            embedding_model=self.settings.embedding_model,
            generated_at=datetime.now(),
            sources=[item.source for item in prepared.sources],
            retrieval_trace=self._build_trace(prepared.fused_candidates),
            usage=AnswerUsage(
                retrieval_candidates=len(prepared.fused_candidates),
                reranked_candidates=len(prepared.reranked_candidates),
                prompt_tokens=chat_result.prompt_tokens,
                completion_tokens=chat_result.completion_tokens,
                total_tokens=(chat_result.total_tokens or 0) + (prepared.rerank_tokens or 0),
            ),
        )

    def prepare_answer(
        self,
        session: Session,
        knowledge_base_id: str,
        payload: AskRequest,
    ) -> PreparedAnswer:
        fused_candidates = self.retrieval_service.search(
            session=session,
            knowledge_base_id=knowledge_base_id,
            question=payload.question,
            vector_top_k=payload.vector_top_k,
            keyword_top_k=payload.keyword_top_k,
            fused_top_k=payload.fused_top_k,
        )
        if not fused_candidates:
            raise ValueError("no retrieval candidates found for the current knowledge base")

        rerank_top_n = payload.rerank_top_n or self.settings.rerank_top_n
        reranked_candidates, rerank_tokens = self._rerank_candidates(
            payload.question,
            fused_candidates,
            rerank_top_n=rerank_top_n,
        )
        max_sources = payload.max_sources or self.settings.qa_max_sources
        selected_candidates = reranked_candidates[:max_sources]
        sources = [
            self._build_source(candidate, index + 1)
            for index, candidate in enumerate(selected_candidates)
        ]
        max_assets = payload.max_assets or self.settings.qa_max_assets
        messages = self._build_messages(payload.question, sources, max_assets=max_assets)
        return PreparedAnswer(
            question=payload.question,
            sources=sources,
            fused_candidates=fused_candidates,
            reranked_candidates=reranked_candidates,
            messages=messages,
            rerank_tokens=rerank_tokens,
        )

    def stream_answer(self, prepared: PreparedAnswer) -> Iterator[ChatStreamChunk]:
        with DashScopeChatClient(self.settings) as client:
            yield from client.stream_chat(prepared.messages)

    def _rerank_candidates(
        self,
        question: str,
        fused_candidates: list[RetrievedCandidate],
        *,
        rerank_top_n: int,
    ) -> tuple[list[RetrievedCandidate], int | None]:
        documents = [
            item.rerank_text(self.settings.qa_max_parent_chars)
            for item in fused_candidates
        ]
        instruct = (
            "Given a student question, rank the passages that best answer it in a local course knowledge base."
        )
        with DashScopeRerankClient(self.settings) as client:
            rerank_result = client.rerank(
                query=question,
                documents=documents,
                top_n=min(rerank_top_n, len(documents)),
                instruct=instruct,
            )

        ordered: list[RetrievedCandidate] = []
        seen: set[str] = set()
        for item in rerank_result.items:
            if item.index < 0 or item.index >= len(fused_candidates):
                continue
            candidate = fused_candidates[item.index]
            candidate.rerank_score = item.relevance_score
            ordered.append(candidate)
            seen.add(candidate.child_chunk_id)

        for candidate in fused_candidates:
            if candidate.child_chunk_id in seen:
                continue
            ordered.append(candidate)

        ordered.sort(
            key=lambda item: (
                item.rerank_score if item.rerank_score is not None else -1.0,
                item.fusion_score,
            ),
            reverse=True,
        )
        return ordered, rerank_result.total_tokens

    def _build_source(self, candidate: RetrievedCandidate, order_index: int) -> QAContextSource:
        chunk = candidate.chunk
        anchor_blocks = self._resolve_anchor_blocks(
            ir_path=chunk.ir_path,
            source_block_ids=chunk.source_block_ids,
        )
        page_width, page_height = self._resolve_page_size(
            ir_path=chunk.ir_path,
            page_idx=chunk.page_start,
        )
        assets = self._resolve_assets(
            bundle_root=chunk.bundle_root,
            raw_assets=chunk.assets,
        )
        source = AnswerSource(
            source_id=f"S{order_index}",
            child_chunk_id=chunk.child_chunk_id,
            parent_chunk_id=chunk.parent_chunk_id,
            document_id=chunk.document_id,
            source_sha1=chunk.source_sha1,
            source_filename=chunk.source_filename,
            document_title=chunk.document_title,
            header_path=chunk.header_path,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            page_width=page_width,
            page_height=page_height,
            source_block_ids=chunk.source_block_ids,
            quote=chunk.retrieval_text,
            parent_context=self._trim_parent_context(chunk.parent_text),
            origin_pdf_path=chunk.origin_pdf_path,
            ir_path=chunk.ir_path,
            bundle_root=chunk.bundle_root,
            review_status=chunk.review_status,  # type: ignore[arg-type]
            assets=assets,
            anchor_blocks=anchor_blocks,
        )
        return QAContextSource(source=source, candidate=candidate)

    def _build_trace(self, candidates: list[RetrievedCandidate]) -> list[RetrievalTraceHit]:
        return [
            RetrievalTraceHit(
                child_chunk_id=item.chunk.child_chunk_id,
                source_filename=item.chunk.source_filename,
                chunk_type=item.chunk.chunk_type,
                channels=sorted(item.channels),
                vector_rank=item.vector_rank,
                keyword_rank=item.keyword_rank,
                vector_score=item.vector_score,
                keyword_score=item.keyword_score,
                fusion_score=item.fusion_score,
                rerank_score=item.rerank_score,
                page_start=item.chunk.page_start,
                page_end=item.chunk.page_end,
            )
            for item in candidates
        ]

    def _build_messages(
        self,
        question: str,
        sources: list[QAContextSource],
        *,
        max_assets: int,
    ) -> list[ChatMessage]:
        system_prompt = (
            "你是一个面向大学生的本地知识库问答助手。"
            "只能根据给定来源回答，不要编造。"
            "请优先用中文回答，首句先直接给出结论。"
            "随后再用简短自然的说明补充依据，并在关键结论后用 [S1] 这种格式标注来源。"
            "如果能确定具体文件名或页码，可以自然写出。"
            "如果证据不足，请明确说信息不足。"
        )
        context_blocks: list[str] = []
        for item in sources:
            source = item.source
            context_blocks.append(
                "\n".join(
                    [
                        f"[{source.source_id}] 文件: {source.source_filename}",
                        f"标题路径: {' > '.join(source.header_path)}",
                        f"页码: {source.page_start + 1}-{source.page_end + 1}",
                        f"命中片段: {source.quote}",
                        f"父级上下文: {source.parent_context}",
                    ]
                )
            )

        user_parts: list[ChatMessageContentPart] = [
            ChatMessageContentPart(
                type="text",
                text=(
                    "请基于下面检索到的知识库来源回答问题。\n\n"
                    f"问题：{question}\n\n"
                    "文字来源：\n"
                    f"{'\n\n'.join(context_blocks)}"
                ),
            )
        ]

        added_assets = 0
        for item in sources:
            if added_assets >= max_assets:
                break
            for asset in item.source.assets:
                if added_assets >= max_assets:
                    break
                data_url = self._asset_to_data_url(asset.absolute_path)
                if data_url is None:
                    continue
                user_parts.append(
                    ChatMessageContentPart(
                        type="text",
                        text=(
                            f"[{item.source.source_id}] 视觉证据，文件 {item.source.source_filename}，"
                            f"页码 {item.source.page_start + 1}-{item.source.page_end + 1}，"
                            f"资源路径 {asset.relative_path}"
                        ),
                    )
                )
                user_parts.append(
                    ChatMessageContentPart(
                        type="image_url",
                        image_url={"url": data_url},
                    )
                )
                added_assets += 1

        user_parts.append(
            ChatMessageContentPart(
                type="text",
                text=(
                    "请输出最终答案。"
                    "格式要求：1. 先用一句话直接回答；"
                    "2. 再补充 1 到 3 句依据说明；"
                    "3. 关键句后标注来源编号。"
                ),
            )
        )

        return [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_parts),
        ]

    def _resolve_anchor_blocks(
        self,
        *,
        ir_path: str | None,
        source_block_ids: list[str],
    ) -> list[SourceAnchorBlock]:
        if not ir_path or not source_block_ids:
            return []

        block_map = self._load_ir_block_map(ir_path)
        anchors: list[SourceAnchorBlock] = []
        for block_id in source_block_ids:
            block = block_map.get(block_id)
            if block is None:
                continue
            anchors.append(
                SourceAnchorBlock(
                    block_id=block_id,
                    block_type=str(block.get("type", "unknown")),
                    page_idx=int(block.get("page_idx", 0)),
                    bbox_page=block.get("bbox_page"),
                )
            )
        return anchors

    def _resolve_assets(
        self,
        *,
        bundle_root: str | None,
        raw_assets: list[dict],
    ) -> list[SourceAsset]:
        if not bundle_root:
            return []

        root = Path(bundle_root)
        assets: list[SourceAsset] = []
        for item in raw_assets:
            relative_path = str(item.get("path", ""))
            absolute_path = (root / relative_path).resolve()
            assets.append(
                SourceAsset(
                    asset_id=str(item.get("asset_id", "")),
                    asset_type=str(item.get("asset_type", "image")),
                    relative_path=relative_path,
                    absolute_path=str(absolute_path),
                )
            )
        return assets

    def _load_ir_block_map(self, ir_path: str) -> dict[str, dict]:
        if ir_path not in self._ir_cache:
            path = Path(ir_path)
            payload = path.read_text(encoding="utf-8")
            import json

            data = json.loads(payload)
            self._ir_cache[ir_path] = {
                block["block_id"]: block for block in data.get("blocks", [])
            }
        return self._ir_cache[ir_path]

    def _resolve_page_size(
        self,
        *,
        ir_path: str | None,
        page_idx: int,
    ) -> tuple[float | None, float | None]:
        if not ir_path:
            return None, None
        path = Path(ir_path)
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
        for page in payload.get("pages", []):
            if int(page.get("page_idx", -1)) != page_idx:
                continue
            page_size = page.get("page_size", {})
            return (
                float(page_size.get("width", 0.0)) or None,
                float(page_size.get("height", 0.0)) or None,
            )
        return None, None

    def _trim_parent_context(self, text: str) -> str:
        cleaned = text.strip()
        if len(cleaned) <= self.settings.qa_max_parent_chars:
            return cleaned
        return f"{cleaned[: self.settings.qa_max_parent_chars].rstrip()}..."

    def _asset_to_data_url(self, absolute_path: str) -> str | None:
        path = Path(absolute_path)
        if not path.exists() or not path.is_file():
            return None
        if path.stat().st_size > 7 * 1024 * 1024:
            return None

        mime_type, _ = mimetypes.guess_type(path.name)
        if mime_type is None:
            mime_type = "image/jpeg"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"
