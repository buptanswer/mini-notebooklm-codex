# Mini-NotebookLM

`Mini-NotebookLM` 现在已经完成 stage1 到 stage5 的核心链路，包括新版架构、MinerU 标准化、结构化切片、混合检索问答，以及前端工作台与可视化溯源。stage6 音视频增强项当前明确延期，后续按需要再接入。

这一阶段交付了三件核心事情：

- 前后端分离工程骨架：`frontend/` 使用 Vite + React + TypeScript，`backend/` 使用 FastAPI。
- 分层数据底座：文件系统目录、SQLite 元数据库、Qdrant 向量库初始化能力已经就位。
- Schema First 数据契约：已经建立 MinerU 原始层、Canonical IR 层、Parent/Child Chunk 层的 Pydantic 模型。

## 目录结构

```text
frontend/                  React 工作台
backend/                   FastAPI 服务
  app/api/                 API 路由
  app/core/                配置与启动
  app/db/                  SQLite 表结构与初始化
  app/repositories/        元数据仓储
  app/schemas/             Raw MinerU / IR / Chunk / API 模型
  app/services/            存储与 Qdrant 服务
storage/                   本地数据底座
  sqlite/                  SQLite 数据文件
  qdrant/                  本地 Qdrant 数据
  knowledge_bases/         各知识库物理目录
doc/                       需求与技术文档
test_inputs/               后续解析联调用测试资料
```

## 当前实际范围

- 已实现主链路：文档/图片上传、MinerU 解析、IR 标准化、Parent/Child Chunking、Qdrant + SQLite 入库、混合检索、重排序、问答、前端溯源
- 暂未实现：飞书妙记/通义听悟、音视频转写入库、视频关键帧
- 当前前端实际技术栈：`React + Vite + TypeScript + 自定义 CSS`
- 需求/设计文档与当前代码实现的详细对照见：
  - [当前实现与需求设计对照说明](C:/Users/14044/Desktop/PyProj/mini-notebooklm/doc/当前实现与需求设计对照说明.md)

## Stage1 已实现

- FastAPI 应用启动时自动初始化：
  - `storage/` 根目录
  - `storage/sqlite/mini_notebooklm.db`
  - SQLite FTS5 虚表与触发器
  - Qdrant `child_chunks` collection
- SQLite 已定义核心表：
  - `knowledge_bases`
  - `documents`
  - `document_assets`
  - `pipeline_jobs`
  - `parent_chunks`
  - `child_chunks`
- FastAPI 已提供基础接口：
  - `GET /api/v1/health`
  - `GET /api/v1/system/overview`
  - `GET /api/v1/knowledge-bases`
  - `POST /api/v1/knowledge-bases`
- 前端已提供 stage1 工作台：
  - 架构总览
  - 数据底座状态展示
  - 知识库列表
  - 新建知识库入口
  - 开发路线图

## 后端启动

在仓库根目录执行：

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e .\backend[dev]
.venv\Scripts\uvicorn app.main:app --app-dir backend --reload
```

可选：将 `backend/.env.example` 复制为根目录 `.env` 后再调整配置。

默认配置下：

- SQLite 使用本地文件模式
- Qdrant 使用本地嵌入式模式
- 向量维度默认按文档建议预留为 `1024`

## 前端启动

```powershell
cd frontend
npm install
npm run dev
```

前端开发服务器默认运行在 `http://127.0.0.1:5173`，并通过 Vite 代理访问后端 `http://127.0.0.1:8000`。

## Stage2 已实现

- 已实现 MinerU 在线 API 客户端：
  - 本地单文件上传
  - 本地批量上传
  - URL 单任务 / 批任务创建
  - 任务轮询
  - `full_zip_url` 下载
- 已实现 MinerU bundle 解析：
  - 解压并识别 `content_list_v2.json`
  - 解析 `layout.json`
  - 识别 `*_origin.pdf`、`images/`、兼容 `*_content_list.json` 与 `*_model.json`
- 已实现 Canonical IR 生成：
  - 产出 `document_ir.json`
  - 建立页面级 `bbox_page`
  - 建立 `origin_pdf_path + page_id` 溯源锚点
  - 生成 section tree / `header_path`
  - 保留图片、表格、公式等多模态资产引用
- 已实现严格模式审计：
  - 递归检测 MinerU 原始输出中的未知字段
  - 检测未知 block type / fallback content shape
  - 将异常信息写入 `document_ir.json -> quality.parser_warnings`
  - 将文档标记为 `review_status=needs_review`

## Stage5 已实现

- 知识库工作台前端：
  - 知识库空间切换与创建
  - 知识库重命名与删除
  - 单文件上传与整文件夹上传
  - 目录树浏览、文件/文件夹重命名、文件移动、删除、批量删除
  - 任务状态工作区
  - 聊天问答工作区
  - 文件管理与来源详情面板
- 可视化溯源：
  - 来源引用卡片
  - `origin.pdf` 页预览
  - 按 `bbox_page` 高亮命中块
  - 原始资产与 `document_ir.json / content_list_v2.json / layout.json` 打开入口
- 问答体验：
  - `POST /api/v1/knowledge-bases/{knowledge_base_id}/ask`
  - `POST /api/v1/knowledge-bases/{knowledge_base_id}/ask/stream`
  - SSE 流式回答展示
- 多模态富化：
  - `qwen3.5-flash` 图片描述与表格摘要
  - `document_ir_enriched.json`
  - Enriched IR 驱动后续 chunking / embedding
- 严格模式用户可见化：
  - `review_status=needs_review` 在文件卡片与来源面板显示黄色 warning
  - 展示 `parser_warning_count`、`unknown_block_count`、`review_summary`
  - 提示用户检查 `document_ir.json` 和 MinerU 原始输出

## Stage2 联调命令

确保系统环境变量里已经配置 `MINERU_API_KEY`，然后在仓库根目录执行：

```powershell
.venv\Scripts\python backend\scripts\stage2_mineru_smoke.py
```

脚本会自动使用 `test_inputs/` 里的：

- 单文件上传：`pdf / pptx / docx / 单张 jpg`
- 批量上传：混合文档批次
- 批量上传：整组图片文件夹

联调产物会落在：

```text
storage/stage2_runs/<timestamp>/
```

其中每个 bundle 解压目录下都会生成：

- 原始 MinerU 输出文件
- `document_ir.json`
- 汇总清单 `summary.json`

## Stage3 已实现

- 基于 `document_ir.json` 的 DOM/section 重建
- 结构感知 Parent/Child chunking
- `text-embedding-v4` 接入代码
- Child chunk 写入 Qdrant
- Parent/Child metadata 写入 SQLite
- 输出 `parent_chunks.jsonl` 与 `child_chunks.jsonl`

## Stage3 联调命令

真实 embedding：

```powershell
.venv\Scripts\python backend\scripts\stage3_index_smoke.py
```

如果当前机器上还没有可用的 DashScope API Key，可先用确定性假向量验证整条入库链路：

```powershell
.venv\Scripts\python backend\scripts\stage3_index_smoke.py --fake-embeddings
```

## Stage4 已实现

- 向量召回：Qdrant Child Chunk 检索
- 关键词检索：SQLite FTS5 + LIKE 兜底
- 召回融合：RRF 融合向量与关键词候选
- `qwen3-rerank` 重排序
- `qwen3.5-plus` 最终问答
- `POST /api/v1/knowledge-bases/{knowledge_base_id}/ask` 问答接口

## Stage4 联调命令

先确保 stage3 索引已经完成，然后执行：

```powershell
.venv\Scripts\python backend\scripts\stage4_qa_smoke.py
```

最新问答联调结果会落在：

```text
storage/stage4_runs/<timestamp>/summary.json
```

## Stage5 全流程验收命令

从零清空旧数据库、Qdrant、本地缓存和历史 smoke 产物后，基于 `test_inputs/` 正式上传整套样本并逐阶段校验：

```powershell
.venv\Scripts\python backend\scripts\stage5_full_e2e.py
```

验收摘要会落在：

```text
storage/stage5_runs/<timestamp>/summary.json
```
