# Mini-NotebookLM Backend

The backend now covers the full stage1-stage5 core workflow:

- FastAPI application skeleton
- SQLite metadata store with FTS5 bootstrap
- Qdrant bootstrap with local-first configuration
- Strict Pydantic models for MinerU raw payloads, canonical IR, and chunk contracts
- MinerU API client for local upload, batch upload, polling, and bundle download
- Bundle parser that converts `content_list_v2.json + layout.json + origin.pdf` into `document_ir.json`
- Enrichment stage that produces `document_ir_enriched.json` with `qwen3.5-flash`
- Strict review mode that records parser warnings / unknown blocks and marks documents as `needs_review`
- Stage3 chunking/indexing pipeline that generates Parent/Child chunks and writes them into SQLite + Qdrant
- Stage4 hybrid retrieval + rerank + multimodal QA pipeline
- Stage5 upload/task APIs, file-management APIs, and SSE streaming QA for the frontend knowledge-base workspace

The audio/video enhancement line from stage6 is intentionally deferred for now. The current implementation/design differences are summarized in [当前实现与需求设计对照说明](C:/Users/14044/Desktop/PyProj/mini-notebooklm/doc/当前实现与需求设计对照说明.md).

Run the API from the repository root:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e .\backend[dev]
.venv\Scripts\uvicorn app.main:app --app-dir backend --reload
```

The API listens on `http://127.0.0.1:8000` by default.

Run the stage2 smoke test from the repository root:

```powershell
.venv\Scripts\python backend\scripts\stage2_mineru_smoke.py
```

Run the stage3 indexing smoke test from the repository root:

```powershell
.venv\Scripts\python backend\scripts\stage3_index_smoke.py --fake-embeddings
```

Run the stage4 QA smoke test from the repository root:

```powershell
.venv\Scripts\python backend\scripts\stage4_qa_smoke.py
```

Run the clean stage5 end-to-end validation from the repository root:

```powershell
.venv\Scripts\python backend\scripts\stage5_full_e2e.py
```
