import {
  startTransition,
  useDeferredValue,
  useEffect,
  useEffectEvent,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
  type InputHTMLAttributes,
} from 'react'
import ReactMarkdown from 'react-markdown'
import rehypeKatex from 'rehype-katex'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import { Document, Page, pdfjs } from 'react-pdf'
import 'katex/dist/katex.min.css'
import './App.css'
import {
  bulkDeleteKnowledgeBaseDocuments,
  buildStorageFileUrl,
  createKnowledgeBase,
  deleteKnowledgeBase,
  deleteKnowledgeBaseDocument,
  deleteKnowledgeBaseFolder,
  fetchKnowledgeBaseDocuments,
  fetchKnowledgeBaseJobs,
  fetchKnowledgeBases,
  fetchSystemOverview,
  renameKnowledgeBaseFolder,
  streamAskKnowledgeBase,
  updateKnowledgeBase,
  updateKnowledgeBaseDocument,
  uploadKnowledgeBaseFiles,
} from './lib/api'
import type {
  AnswerSource,
  AskResponse,
  DocumentFileSummary,
  KnowledgeBaseSummary,
  PipelineJobSummary,
  SystemOverview,
} from './lib/types'

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString()

type UploadMode = 'files' | 'folder'
type ExplorerFilter = 'all' | 'warning' | 'running'
type WorkspaceTab = 'files' | 'chat' | 'tasks'
type FolderNode = {
  path: string
  label: string
  depth: number
}

type DirectoryInputProps = InputHTMLAttributes<HTMLInputElement> & {
  webkitdirectory?: string
  directory?: string
}

function App() {
  const [overview, setOverview] = useState<SystemOverview | null>(null)
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBaseSummary[]>([])
  const [documents, setDocuments] = useState<DocumentFileSummary[]>([])
  const [jobs, setJobs] = useState<PipelineJobSummary[]>([])
  const [selectedKnowledgeBaseId, setSelectedKnowledgeBaseId] = useState<string | null>(null)
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null)
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null)
  const [activeWorkspace, setActiveWorkspace] = useState<WorkspaceTab>('files')
  const [selectedFolderPath, setSelectedFolderPath] = useState<string>('')
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<string[]>([])
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [createBusy, setCreateBusy] = useState(false)
  const [uploadBusy, setUploadBusy] = useState(false)
  const [loadingShell, setLoadingShell] = useState(true)
  const [loadingContext, setLoadingContext] = useState(false)
  const [renamingKnowledgeBase, setRenamingKnowledgeBase] = useState(false)
  const [deletingKnowledgeBaseBusy, setDeletingKnowledgeBaseBusy] = useState(false)
  const [fileFilter, setFileFilter] = useState('')
  const [explorerFilter, setExplorerFilter] = useState<ExplorerFilter>('all')
  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState(false)
  const [answerResult, setAnswerResult] = useState<AskResponse | null>(null)
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [uploadSummary, setUploadSummary] = useState<string | null>(null)

  const deferredFileFilter = useDeferredValue(fileFilter)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const folderInputRef = useRef<HTMLInputElement | null>(null)

  const selectedKnowledgeBase = knowledgeBases.find(
    (item) => item.id === selectedKnowledgeBaseId,
  ) ?? null
  const selectedDocument = documents.find((item) => item.id === selectedDocumentId) ?? null
  const selectedJob = jobs.find((item) => item.id === selectedJobId) ?? null
  const selectedSource =
    answerResult?.sources.find((item) => item.source_id === selectedSourceId) ?? null

  const syncShell = useEffectEvent(async () => {
    setLoadingShell(true)
    setError(null)
    try {
      const [systemOverview, bases] = await Promise.all([
        fetchSystemOverview(),
        fetchKnowledgeBases(),
      ])
      startTransition(() => {
        setOverview(systemOverview)
        setKnowledgeBases(bases)
        if (!selectedKnowledgeBaseId && bases.length > 0) {
          setSelectedKnowledgeBaseId(bases[0].id)
        }
      })
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : '加载系统信息失败')
    } finally {
      setLoadingShell(false)
    }
  })

  const syncKnowledgeBaseContext = useEffectEvent(async (knowledgeBaseId: string) => {
    setLoadingContext(true)
    try {
      const [docs, taskList] = await Promise.all([
        fetchKnowledgeBaseDocuments(knowledgeBaseId),
        fetchKnowledgeBaseJobs(knowledgeBaseId),
      ])
      startTransition(() => {
        setDocuments(docs)
        setJobs(taskList)
        if (
          selectedFolderPath &&
          !docs.some(
            (item) =>
              item.source_relative_path === selectedFolderPath ||
              item.source_relative_path.startsWith(`${selectedFolderPath}/`),
          )
        ) {
          setSelectedFolderPath('')
        }
        setSelectedDocumentIds((current) =>
          current.filter((documentId) => docs.some((item) => item.id === documentId)),
        )
        if (!docs.find((item) => item.id === selectedDocumentId)) {
          setSelectedDocumentId(docs[0]?.id ?? null)
        }
        if (!taskList.find((item) => item.id === selectedJobId)) {
          setSelectedJobId(taskList[0]?.id ?? null)
        }
      })
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : '加载知识库内容失败')
    } finally {
      setLoadingContext(false)
    }
  })

  useEffect(() => {
    void syncShell()
  }, [])

  useEffect(() => {
    if (!selectedKnowledgeBaseId) {
      setDocuments([])
      setJobs([])
      setSelectedDocumentId(null)
      setSelectedJobId(null)
      setSelectedDocumentIds([])
      setSelectedFolderPath('')
      return
    }
    void syncKnowledgeBaseContext(selectedKnowledgeBaseId)
  }, [selectedKnowledgeBaseId])

  useEffect(() => {
    if (!selectedKnowledgeBaseId) {
      return
    }
    const hasRunningJobs = jobs.some((job) => job.state === 'pending' || job.state === 'running')
    if (!hasRunningJobs) {
      return
    }
    const timer = window.setInterval(() => {
      void syncKnowledgeBaseContext(selectedKnowledgeBaseId)
      void syncShell()
    }, 4000)
    return () => window.clearInterval(timer)
  }, [jobs, selectedKnowledgeBaseId])

  async function handleCreateKnowledgeBase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!name.trim()) {
      return
    }

    setCreateBusy(true)
    setError(null)
    try {
      const created = await createKnowledgeBase({
        name: name.trim(),
        description: description.trim() || undefined,
      })
      setName('')
      setDescription('')
      setSelectedKnowledgeBaseId(created.id)
      await syncShell()
      await syncKnowledgeBaseContext(created.id)
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : '创建知识库失败')
    } finally {
      setCreateBusy(false)
    }
  }

  async function handleUploadSelection(
    mode: UploadMode,
    event: ChangeEvent<HTMLInputElement>,
  ) {
    const selectedFiles = event.target.files
    if (!selectedFiles?.length || !selectedKnowledgeBaseId) {
      return
    }

    setUploadBusy(true)
    setError(null)
    setUploadSummary(null)
    try {
      const entries = Array.from(selectedFiles).map((file) => {
        const relativePath =
          mode === 'folder'
            ? (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name
            : file.name
        return { file, relativePath }
      })
      const response = await uploadKnowledgeBaseFiles(selectedKnowledgeBaseId, entries)
      setUploadSummary(
        `${response.accepted_files} 个文件已进入后台任务队列，正在执行 MinerU 解析、切片与索引入库。`,
      )
      setActiveWorkspace('tasks')
      await syncKnowledgeBaseContext(selectedKnowledgeBaseId)
      await syncShell()
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : '上传失败')
    } finally {
      setUploadBusy(false)
      event.target.value = ''
    }
  }

  async function handleAskQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedKnowledgeBaseId || !question.trim()) {
      return
    }

    setAsking(true)
    setError(null)
    try {
      setAnswerResult(null)
      setSelectedSourceId(null)
      await streamAskKnowledgeBase(selectedKnowledgeBaseId, {
        question: question.trim(),
      }, {
        onMeta: (meta) => {
          setAnswerResult({
            knowledge_base_id: meta.knowledge_base_id,
            question: meta.question,
            answer: '',
            answer_model: meta.answer_model,
            rerank_model: meta.rerank_model,
            embedding_model: meta.embedding_model,
            generated_at: new Date().toISOString(),
            sources: meta.sources,
            retrieval_trace: meta.retrieval_trace,
            usage: {
              retrieval_candidates: meta.retrieval_trace.length,
              reranked_candidates: meta.sources.length,
              prompt_tokens: null,
              completion_tokens: null,
              total_tokens: null,
            },
          })
          setSelectedSourceId(meta.sources[0]?.source_id ?? null)
          setActiveWorkspace('chat')
        },
        onDelta: (text) => {
          startTransition(() => {
            setAnswerResult((current) =>
              current
                ? {
                    ...current,
                    answer: `${current.answer}${text}`,
                  }
                : current,
            )
          })
        },
        onDone: (response) => {
          setAnswerResult(response)
          setSelectedSourceId(response.sources[0]?.source_id ?? null)
        },
      })
    } catch (askError) {
      setError(askError instanceof Error ? askError.message : '问答失败')
    } finally {
      setAsking(false)
    }
  }

  async function handleRenameKnowledgeBase() {
    if (!selectedKnowledgeBase) {
      return
    }
    const nextName = window.prompt('输入新的知识库名称', selectedKnowledgeBase.name)?.trim()
    if (!nextName || nextName === selectedKnowledgeBase.name) {
      return
    }
    setRenamingKnowledgeBase(true)
    setError(null)
    try {
      await updateKnowledgeBase(selectedKnowledgeBase.id, {
        name: nextName,
        description: selectedKnowledgeBase.description ?? undefined,
      })
      await syncShell()
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : '知识库重命名失败')
    } finally {
      setRenamingKnowledgeBase(false)
    }
  }

  async function handleDeleteKnowledgeBase() {
    if (!selectedKnowledgeBase) {
      return
    }
    const confirmed = window.confirm(`确认删除知识库“${selectedKnowledgeBase.name}”吗？`)
    if (!confirmed) {
      return
    }
    setDeletingKnowledgeBaseBusy(true)
    setError(null)
    try {
      await deleteKnowledgeBase(selectedKnowledgeBase.id)
      setSelectedKnowledgeBaseId(null)
      setDocuments([])
      setJobs([])
      setAnswerResult(null)
      setSelectedSourceId(null)
      setSelectedDocumentId(null)
      setSelectedDocumentIds([])
      await syncShell()
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : '知识库删除失败')
    } finally {
      setDeletingKnowledgeBaseBusy(false)
    }
  }

  async function handleRenameDocument(document: DocumentFileSummary) {
    if (!selectedKnowledgeBaseId) {
      return
    }
    const nextName = window.prompt('输入新的文件名', document.source_filename)?.trim()
    if (!nextName || nextName === document.source_filename) {
      return
    }
    try {
      await updateKnowledgeBaseDocument(selectedKnowledgeBaseId, document.id, {
        new_name: nextName,
      })
      await syncKnowledgeBaseContext(selectedKnowledgeBaseId)
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : '文件重命名失败')
    }
  }

  async function handleMoveDocument(document: DocumentFileSummary) {
    if (!selectedKnowledgeBaseId) {
      return
    }
    const currentParent = parentFolderPath(document.source_relative_path)
    const nextParent = window.prompt('输入目标文件夹路径，留空表示根目录', currentParent)?.trim()
    if (nextParent === null) {
      return
    }
    try {
      await updateKnowledgeBaseDocument(selectedKnowledgeBaseId, document.id, {
        new_parent_path: nextParent,
      })
      await syncKnowledgeBaseContext(selectedKnowledgeBaseId)
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : '文件移动失败')
    }
  }

  async function handleDeleteDocument(documentId: string) {
    if (!selectedKnowledgeBaseId) {
      return
    }
    const confirmed = window.confirm('确认删除这个文件吗？')
    if (!confirmed) {
      return
    }
    try {
      await deleteKnowledgeBaseDocument(selectedKnowledgeBaseId, documentId)
      setSelectedDocumentIds((current) => current.filter((item) => item !== documentId))
      await syncKnowledgeBaseContext(selectedKnowledgeBaseId)
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : '文件删除失败')
    }
  }

  async function handleBulkDeleteDocuments() {
    if (!selectedKnowledgeBaseId || !selectedDocumentIds.length) {
      return
    }
    const confirmed = window.confirm(`确认删除选中的 ${selectedDocumentIds.length} 个文件吗？`)
    if (!confirmed) {
      return
    }
    try {
      await bulkDeleteKnowledgeBaseDocuments(selectedKnowledgeBaseId, selectedDocumentIds)
      setSelectedDocumentIds([])
      await syncKnowledgeBaseContext(selectedKnowledgeBaseId)
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : '批量删除失败')
    }
  }

  async function handleRenameFolder(folderPath: string) {
    if (!selectedKnowledgeBaseId || !folderPath) {
      return
    }
    const nextPath = window.prompt('输入新的文件夹路径', folderPath)?.trim()
    if (!nextPath || nextPath === folderPath) {
      return
    }
    try {
      await renameKnowledgeBaseFolder(selectedKnowledgeBaseId, folderPath, nextPath)
      setSelectedFolderPath(nextPath)
      await syncKnowledgeBaseContext(selectedKnowledgeBaseId)
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : '文件夹重命名失败')
    }
  }

  async function handleDeleteFolder(folderPath: string) {
    if (!selectedKnowledgeBaseId || !folderPath) {
      return
    }
    const confirmed = window.confirm(`确认删除文件夹“${folderPath}”及其中所有文件吗？`)
    if (!confirmed) {
      return
    }
    try {
      await deleteKnowledgeBaseFolder(selectedKnowledgeBaseId, folderPath)
      setSelectedFolderPath('')
      setSelectedDocumentIds([])
      await syncKnowledgeBaseContext(selectedKnowledgeBaseId)
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : '文件夹删除失败')
    }
  }

  function toggleDocumentSelection(documentId: string) {
    setSelectedDocumentIds((current) =>
      current.includes(documentId)
        ? current.filter((item) => item !== documentId)
        : [...current, documentId],
    )
  }

  const filteredDocuments = documents.filter((document) => {
    const searchText = deferredFileFilter.trim().toLowerCase()
    const matchesFolder =
      !selectedFolderPath ||
      document.source_relative_path === selectedFolderPath ||
      document.source_relative_path.startsWith(`${selectedFolderPath}/`)
    const matchesText =
      !searchText ||
      document.source_filename.toLowerCase().includes(searchText) ||
      (document.document_title ?? '').toLowerCase().includes(searchText)
    if (!matchesText || !matchesFolder) {
      return false
    }
    if (explorerFilter === 'warning') {
      return document.review_status === 'needs_review'
    }
    if (explorerFilter === 'running') {
      return (
        document.parsing_status !== 'completed' ||
        document.chunking_status !== 'completed' ||
        document.indexing_status !== 'completed'
      )
    }
    return true
  })

  const folderNodes = buildFolderNodes(documents)

  const workspaceMetrics = [
    { label: '文档', value: documents.length, note: '当前空间文件数' },
    {
      label: '需复核',
      value: documents.filter((item) => item.review_status === 'needs_review').length,
      note: 'MinerU 异常与未知字段',
    },
    {
      label: '运行中任务',
      value: jobs.filter((item) => item.state === 'pending' || item.state === 'running').length,
      note: '后台解析与索引',
    },
    {
      label: 'Child Chunk',
      value: documents.reduce((sum, item) => sum + item.child_chunk_count, 0),
      note: '检索向量规模',
    },
  ]

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="sidebar-brand">
          <span className="eyebrow">Mini-NotebookLM</span>
          <h1>知识库工作台</h1>
          <p>
            上传资料、跟踪任务、发起问答，并把答案一路溯源回 PDF 页码、块坐标和原始
            MinerU 输出。
          </p>
        </div>

        <section className="sidebar-section">
          <div className="section-heading">
            <span className="eyebrow">Knowledge Bases</span>
            <strong>知识库空间</strong>
          </div>
          <div className="sidebar-list">
            {knowledgeBases.map((knowledgeBase) => (
              <button
                key={knowledgeBase.id}
                type="button"
                className={`sidebar-card ${
                  knowledgeBase.id === selectedKnowledgeBaseId ? 'active' : ''
                }`}
                onClick={() => {
                  setSelectedKnowledgeBaseId(knowledgeBase.id)
                  setAnswerResult(null)
                  setSelectedSourceId(null)
                }}
              >
                <div>
                  <strong>{knowledgeBase.name}</strong>
                  <span>{knowledgeBase.document_count} 个文件</span>
                </div>
                <small>{knowledgeBase.task_count} 个任务</small>
              </button>
            ))}
            {!knowledgeBases.length && (
              <div className="sidebar-empty">先创建一个知识库，后面所有上传与问答都在这里发生。</div>
            )}
          </div>
        </section>

        <section className="sidebar-section">
          <div className="section-heading">
            <span className="eyebrow">Create</span>
            <strong>新建空间</strong>
          </div>
          <form className="kb-create-form" onSubmit={handleCreateKnowledgeBase}>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="例如：数据库系统复习"
              maxLength={120}
            />
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="记录课程、学期或资料范围"
              maxLength={500}
              rows={3}
            />
            <button type="submit" disabled={createBusy}>
              {createBusy ? '创建中...' : '新建知识库'}
            </button>
          </form>
        </section>

        <section className="sidebar-section sidebar-health">
          <div className="section-heading">
            <span className="eyebrow">Bootstrap</span>
            <strong>系统状态</strong>
          </div>
          <div className="health-grid">
            <span className={`status-dot ${overview?.bootstrap.storage_ready ? 'ok' : 'pending'}`}>
              Storage
            </span>
            <span className={`status-dot ${overview?.bootstrap.database_ready ? 'ok' : 'pending'}`}>
              SQLite
            </span>
            <span className={`status-dot ${overview?.bootstrap.qdrant_ready ? 'ok' : 'warning'}`}>
              Qdrant
            </span>
          </div>
          <button type="button" className="ghost-button" onClick={() => void syncShell()}>
            {loadingShell ? '刷新中' : '刷新全局状态'}
          </button>
        </section>
      </aside>

      <main className="app-main">
        <section className="hero-panel">
          <div className="hero-copy">
            <span className="eyebrow">Stage 5</span>
            <h2>上传、解析、检索、问答、溯源现在已经接成一条完整链路。</h2>
            <p>
              普通用户会先从这里上传单文件或整个资料文件夹。系统在后台调用 MinerU、
              生成 IR、切片入库，并把可疑文档明确标成黄色 warning。
            </p>
          </div>
          <div className="hero-actions">
            <button
              type="button"
              className="primary-button"
              disabled={!selectedKnowledgeBaseId || uploadBusy}
              onClick={() => fileInputRef.current?.click()}
            >
              {uploadBusy ? '上传中...' : '上传文件'}
            </button>
            <button
              type="button"
              className="secondary-button"
              disabled={!selectedKnowledgeBaseId || uploadBusy}
              onClick={() => folderInputRef.current?.click()}
            >
              上传文件夹
            </button>
            <button type="button" className="ghost-button" onClick={() => void syncShell()}>
              {loadingShell || loadingContext ? '同步中...' : '同步状态'}
            </button>
            <button
              type="button"
              className="ghost-button"
              disabled={!selectedKnowledgeBaseId || renamingKnowledgeBase}
              onClick={() => void handleRenameKnowledgeBase()}
            >
              {renamingKnowledgeBase ? '重命名中...' : '重命名知识库'}
            </button>
            <button
              type="button"
              className="danger-button"
              disabled={!selectedKnowledgeBaseId || deletingKnowledgeBaseBusy}
              onClick={() => void handleDeleteKnowledgeBase()}
            >
              {deletingKnowledgeBaseBusy ? '删除中...' : '删除知识库'}
            </button>
          </div>
          <input
            ref={fileInputRef}
            hidden
            type="file"
            multiple
            accept=".pdf,.ppt,.pptx,.doc,.docx,.png,.jpg,.jpeg"
            onChange={(event) => void handleUploadSelection('files', event)}
          />
          <input
            ref={folderInputRef}
            hidden
            type="file"
            multiple
            accept=".pdf,.ppt,.pptx,.doc,.docx,.png,.jpg,.jpeg"
            onChange={(event) => void handleUploadSelection('folder', event)}
            {...({ webkitdirectory: '', directory: '' } as DirectoryInputProps)}
          />
        </section>

        {error && <section className="banner error-banner">{error}</section>}
        {uploadSummary && <section className="banner success-banner">{uploadSummary}</section>}

        <section className="metrics-grid">
          {workspaceMetrics.map((metric) => (
            <article key={metric.label} className="metric-card">
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
              <small>{metric.note}</small>
            </article>
          ))}
        </section>

        <section className="workspace-tabs">
          {([
            ['files', '文件管理'],
            ['chat', '聊天问答'],
            ['tasks', '任务状态'],
          ] as Array<[WorkspaceTab, string]>).map(([value, label]) => (
            <button
              key={value}
              type="button"
              className={`tab-button ${activeWorkspace === value ? 'active' : ''}`}
              onClick={() => setActiveWorkspace(value)}
            >
              {label}
            </button>
          ))}
        </section>

        <section className="workspace-grid">
          <div className="workspace-main">
            {activeWorkspace === 'files' && (
              <section className="panel">
                <div className="panel-header">
                  <div>
                    <span className="eyebrow">Explorer</span>
                    <h3>上传与文件管理</h3>
                    <p className="muted">
                      黄色卡片表示解析出现 warning 或 unknown block，用户应打开
                      `document_ir.json` 和 MinerU 原始输出排查。
                    </p>
                  </div>
                  <div className="panel-actions">
                    <input
                      value={fileFilter}
                      onChange={(event) => setFileFilter(event.target.value)}
                      placeholder="搜索文件名或标题"
                    />
                    <div className="chip-row">
                      <button
                        type="button"
                        className={`chip ${explorerFilter === 'all' ? 'active' : ''}`}
                        onClick={() => setExplorerFilter('all')}
                      >
                        全部
                      </button>
                      <button
                        type="button"
                        className={`chip ${explorerFilter === 'warning' ? 'active' : ''}`}
                        onClick={() => setExplorerFilter('warning')}
                      >
                        仅 warning
                      </button>
                      <button
                        type="button"
                        className={`chip ${explorerFilter === 'running' ? 'active' : ''}`}
                        onClick={() => setExplorerFilter('running')}
                      >
                        运行中
                      </button>
                    </div>
                  </div>
                </div>

                <div className="file-actions-bar">
                  <span>
                    当前文件夹：{selectedFolderPath || '根目录'} · 已选 {selectedDocumentIds.length} 项
                  </span>
                  <div className="chip-row">
                    <button
                      type="button"
                      className="ghost-button"
                      disabled={!selectedDocumentIds.length}
                      onClick={() => void handleBulkDeleteDocuments()}
                    >
                      批量删除
                    </button>
                    <button
                      type="button"
                      className="ghost-button"
                      disabled={!selectedFolderPath}
                      onClick={() => void handleRenameFolder(selectedFolderPath)}
                    >
                      重命名文件夹
                    </button>
                    <button
                      type="button"
                      className="danger-button"
                      disabled={!selectedFolderPath}
                      onClick={() => void handleDeleteFolder(selectedFolderPath)}
                    >
                      删除文件夹
                    </button>
                  </div>
                </div>

                <div className="explorer-layout">
                  <aside className="folder-tree">
                    <button
                      type="button"
                      className={`folder-node ${selectedFolderPath === '' ? 'active' : ''}`}
                      onClick={() => setSelectedFolderPath('')}
                    >
                      全部文件
                    </button>
                    {folderNodes.map((node) => (
                      <button
                        key={node.path}
                        type="button"
                        className={`folder-node ${
                          selectedFolderPath === node.path ? 'active' : ''
                        }`}
                        style={{ paddingLeft: `${0.9 + node.depth * 1.1}rem` }}
                        onClick={() => setSelectedFolderPath(node.path)}
                      >
                        {node.label}
                      </button>
                    ))}
                  </aside>

                  <div className="document-grid">
                    {filteredDocuments.map((document) => (
                      <article
                        key={document.id}
                        className={`document-card ${
                          selectedDocumentId === document.id ? 'active' : ''
                        } ${document.review_status === 'needs_review' ? 'warning' : ''}`}
                      >
                        <div className="document-card-top">
                          <label className="select-toggle">
                            <input
                              type="checkbox"
                              checked={selectedDocumentIds.includes(document.id)}
                              onChange={() => toggleDocumentSelection(document.id)}
                            />
                            <span>选择</span>
                          </label>
                          <span className={`review-badge ${document.review_status}`}>
                            {document.review_status === 'needs_review' ? '需复核' : 'OK'}
                          </span>
                          <span className="file-type">{document.source_format.toUpperCase()}</span>
                        </div>
                        <button
                          type="button"
                          className="document-open"
                          onClick={() => setSelectedDocumentId(document.id)}
                        >
                          <strong>{document.source_filename}</strong>
                          <p>{document.source_relative_path}</p>
                          <p>{document.document_title ?? '等待标题抽取或使用原文件名。'}</p>
                        </button>
                        <dl className="mini-stats">
                          <div>
                            <dt>Parser Warning</dt>
                            <dd>{document.parser_warning_count}</dd>
                          </div>
                          <div>
                            <dt>Unknown Block</dt>
                            <dd>{document.unknown_block_count}</dd>
                          </div>
                          <div>
                            <dt>Child Chunk</dt>
                            <dd>{document.child_chunk_count}</dd>
                          </div>
                        </dl>
                        <div className="status-row">
                          <span className={`stage-pill ${document.parsing_status}`}>
                            Parse {document.parsing_status}
                          </span>
                          <span className={`stage-pill ${document.indexing_status}`}>
                            Index {document.indexing_status}
                          </span>
                        </div>
                        <div className="document-inline-actions">
                          <button type="button" className="ghost-button" onClick={() => void handleRenameDocument(document)}>
                            重命名
                          </button>
                          <button type="button" className="ghost-button" onClick={() => void handleMoveDocument(document)}>
                            移动
                          </button>
                          <button type="button" className="danger-button" onClick={() => void handleDeleteDocument(document.id)}>
                            删除
                          </button>
                        </div>
                      </article>
                    ))}
                    {!filteredDocuments.length && (
                      <div className="empty-card">
                        <strong>还没有可展示的文件</strong>
                        <p>先上传样本或切换筛选条件，文档解析完成后会自动出现在这里。</p>
                      </div>
                    )}
                  </div>
                </div>
              </section>
            )}

            {activeWorkspace === 'chat' && (
              <section className="panel">
                <div className="panel-header stack">
                  <div>
                    <span className="eyebrow">Ask</span>
                    <h3>聊天问答</h3>
                    <p className="muted">
                      混合检索会先做向量召回和关键词检索，再经过 `qwen3-rerank`，
                      最后由 `qwen3.5-plus` 生成答案。
                    </p>
                  </div>
                  <form className="ask-form" onSubmit={handleAskQuestion}>
                    <textarea
                      value={question}
                      onChange={(event) => setQuestion(event.target.value)}
                      placeholder="例如：这个 Word 模板的指导教师是谁？"
                      rows={4}
                    />
                    <div className="ask-actions">
                      <button
                        type="submit"
                        className="primary-button"
                        disabled={!selectedKnowledgeBaseId || asking}
                      >
                        {asking ? '回答生成中...' : '开始问答'}
                      </button>
                      <button
                        type="button"
                        className="ghost-button"
                        onClick={() => setQuestion('智能推荐测试样本PPT用于什么测试？')}
                      >
                        填入示例问题
                      </button>
                    </div>
                  </form>
                </div>

                {!answerResult && (
                  <div className="empty-card">
                    <strong>还没有问答结果</strong>
                    <p>输入问题后，右侧会同步展示引用来源、PDF 高亮和对应图片资产。</p>
                  </div>
                )}

                {answerResult && (
                  <div className="chat-layout">
                    <article className="answer-card">
                      <div className="answer-meta">
                        <span>{answerResult.answer_model}</span>
                        <span>{answerResult.rerank_model}</span>
                        <span>{answerResult.embedding_model}</span>
                      </div>
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm, remarkMath]}
                        rehypePlugins={[rehypeKatex]}
                      >
                        {answerResult.answer}
                      </ReactMarkdown>
                      <div className="usage-strip">
                        <span>召回候选 {answerResult.usage.retrieval_candidates}</span>
                        <span>重排候选 {answerResult.usage.reranked_candidates}</span>
                        <span>总 Token {answerResult.usage.total_tokens ?? '未知'}</span>
                      </div>
                    </article>

                    <section className="panel inset-panel">
                      <div className="panel-header compact">
                        <div>
                          <span className="eyebrow">Sources</span>
                          <h4>引用资料面板</h4>
                        </div>
                      </div>
                      <div className="source-list">
                        {answerResult.sources.map((source, index) => (
                          <button
                            key={source.source_id}
                            type="button"
                            className={`source-card ${
                              selectedSourceId === source.source_id ? 'active' : ''
                            } ${
                              source.review_status === 'needs_review' ? 'warning' : ''
                            }`}
                            onClick={() => setSelectedSourceId(source.source_id)}
                          >
                            <div className="source-card-top">
                              <span>#{index + 1}</span>
                              <span className={`review-badge ${source.review_status}`}>
                                {source.review_status === 'needs_review' ? '需复核' : '可追溯'}
                              </span>
                            </div>
                            <strong>{source.source_filename}</strong>
                            <p>{source.quote}</p>
                            <small>
                              {source.header_path.length
                                ? source.header_path.join(' / ')
                                : '未命中标题路径'}
                            </small>
                          </button>
                        ))}
                      </div>
                    </section>

                    <section className="panel inset-panel">
                      <div className="panel-header compact">
                        <div>
                          <span className="eyebrow">Trace</span>
                          <h4>检索与重排轨迹</h4>
                        </div>
                      </div>
                      <div className="trace-list">
                        {answerResult.retrieval_trace.map((hit, index) => (
                          <article key={`${hit.child_chunk_id}-${index}`} className="trace-card">
                            <div className="trace-card-top">
                              <strong>{hit.source_filename}</strong>
                              <span>{hit.chunk_type}</span>
                            </div>
                            <p>
                              融合 {hit.fusion_score.toFixed(3)} / 重排{' '}
                              {hit.rerank_score?.toFixed(3) ?? '未启用'}
                            </p>
                            <small>
                              {hit.channels.join(' + ')} · p.{hit.page_start + 1}-{hit.page_end + 1}
                            </small>
                          </article>
                        ))}
                      </div>
                    </section>
                  </div>
                )}
              </section>
            )}

            {activeWorkspace === 'tasks' && (
              <section className="panel">
                <div className="panel-header">
                  <div>
                    <span className="eyebrow">Pipeline</span>
                    <h3>任务状态</h3>
                    <p className="muted">
                      这里展示正式上传链路中的后台任务，而不是测试脚本输出。普通用户可以直接看到
                      parse/chunk/index 每一步是否完成。
                    </p>
                  </div>
                </div>
                <div className="task-list">
                  {jobs.map((job) => (
                    <button
                      key={job.id}
                      type="button"
                      className={`task-card ${selectedJobId === job.id ? 'active' : ''}`}
                      onClick={() => setSelectedJobId(job.id)}
                    >
                      <div className="task-card-top">
                        <strong>{job.stage}</strong>
                        <span className={taskBadgeClass(job.state)}>{job.state}</span>
                      </div>
                      <p>{summarizePayload(job.payload_json)}</p>
                      <small>
                        attempts {job.attempts} · {formatDate(job.updated_at)}
                      </small>
                    </button>
                  ))}
                  {!jobs.length && (
                    <div className="empty-card">
                      <strong>后台任务列表为空</strong>
                      <p>上传文件后，MinerU 解析、切片和索引任务会依次出现在这里。</p>
                    </div>
                  )}
                </div>
              </section>
            )}
          </div>

          <aside className="workspace-detail">
            <section className="panel detail-panel">
              <div className="panel-header compact">
                <div>
                  <span className="eyebrow">Detail</span>
                  <h3>
                    {activeWorkspace === 'chat'
                      ? '引用预览与可视化溯源'
                      : activeWorkspace === 'tasks'
                        ? '任务详情'
                        : '文件详情'}
                  </h3>
                </div>
              </div>

              {activeWorkspace === 'chat' && selectedSource && (
                <SourcePreview source={selectedSource} />
              )}

              {activeWorkspace === 'files' && selectedDocument && (
                <DocumentInspector
                  document={selectedDocument}
                  onRename={() => void handleRenameDocument(selectedDocument)}
                  onMove={() => void handleMoveDocument(selectedDocument)}
                  onDelete={() => void handleDeleteDocument(selectedDocument.id)}
                />
              )}

              {activeWorkspace === 'tasks' && selectedJob && <JobInspector job={selectedJob} />}

              {activeWorkspace === 'files' && !selectedDocument && (
                <div className="empty-card">
                  <strong>选择一个文件</strong>
                  <p>右侧会显示原始路径、IR 文件、MinerU 输出和 warning 说明。</p>
                </div>
              )}

              {activeWorkspace === 'chat' && !selectedSource && (
                <div className="empty-card">
                  <strong>选择一个引用来源</strong>
                  <p>右侧会显示 PDF 高亮、引用文本和对应图片资产。</p>
                </div>
              )}

              {activeWorkspace === 'tasks' && !selectedJob && (
                <div className="empty-card">
                  <strong>选择一个后台任务</strong>
                  <p>右侧会展开这个任务的 stage、状态、时间和错误信息。</p>
                </div>
              )}

              <div className="detail-footer">
                <span>当前知识库</span>
                <strong>{selectedKnowledgeBase?.name ?? '未选择'}</strong>
                <code>{selectedKnowledgeBase?.storage_root ?? '暂无存储路径'}</code>
              </div>
            </section>
          </aside>
        </section>
      </main>
    </div>
  )
}

function DocumentInspector({
  document,
  onRename,
  onMove,
  onDelete,
}: {
  document: DocumentFileSummary
  onRename: () => void
  onMove: () => void
  onDelete: () => void
}) {
  const originPdfUrl = buildStorageFileUrl(document.origin_pdf_path)
  const irUrl = buildStorageFileUrl(document.ir_path)
  const enrichedIrUrl = buildStorageFileUrl(document.enriched_ir_path)
  const contentListUrl = buildStorageFileUrl(joinStoragePath(document.bundle_root, 'content_list_v2.json'))
  const layoutUrl = buildStorageFileUrl(joinStoragePath(document.bundle_root, 'layout.json'))

  return (
    <div className="detail-stack">
      {document.review_status === 'needs_review' && (
        <div className="warning-callout">
          <strong>该文档需要人工复核</strong>
          <p>{document.review_summary ?? '解析阶段出现 warning 或 unknown block。'}</p>
        </div>
      )}

      <article className="detail-card">
        <div className="detail-header">
          <strong>{document.source_filename}</strong>
          <span className={`review-badge ${document.review_status}`}>
            {document.review_status === 'needs_review' ? '需复核' : '状态正常'}
          </span>
        </div>
        <dl className="detail-list">
          <div>
            <dt>标题</dt>
            <dd>{document.document_title ?? '未抽取'}</dd>
          </div>
          <div>
            <dt>解析状态</dt>
            <dd>{document.parsing_status}</dd>
          </div>
          <div>
            <dt>索引状态</dt>
            <dd>{document.indexing_status}</dd>
          </div>
          <div>
            <dt>Parser Warning</dt>
            <dd>{document.parser_warning_count}</dd>
          </div>
          <div>
            <dt>Unknown Block</dt>
            <dd>{document.unknown_block_count}</dd>
          </div>
          <div>
            <dt>Parent / Child</dt>
            <dd>
              {document.parent_chunk_count} / {document.child_chunk_count}
            </dd>
          </div>
        </dl>
        <div className="document-inline-actions">
          <button type="button" className="ghost-button" onClick={onRename}>
            重命名
          </button>
          <button type="button" className="ghost-button" onClick={onMove}>
            移动
          </button>
          <button type="button" className="danger-button" onClick={onDelete}>
            删除
          </button>
        </div>
      </article>

      <LinkPanel
        title="检查输出"
        links={[
          ['document_ir.json', irUrl],
          ['document_ir_enriched.json', enrichedIrUrl],
          ['content_list_v2.json', contentListUrl],
          ['layout.json', layoutUrl],
          ['origin.pdf', originPdfUrl],
        ]}
      />
    </div>
  )
}

function JobInspector({ job }: { job: PipelineJobSummary }) {
  const payload = summarizePayload(job.payload_json)

  return (
    <div className="detail-stack">
      <article className="detail-card">
        <div className="detail-header">
          <strong>{job.stage}</strong>
          <span className={taskBadgeClass(job.state)}>{job.state}</span>
        </div>
        <dl className="detail-list">
          <div>
            <dt>任务 ID</dt>
            <dd>{job.id}</dd>
          </div>
          <div>
            <dt>Document ID</dt>
            <dd>{job.document_id ?? '未绑定'}</dd>
          </div>
          <div>
            <dt>Attempts</dt>
            <dd>{job.attempts}</dd>
          </div>
          <div>
            <dt>开始时间</dt>
            <dd>{job.started_at ? formatDate(job.started_at) : '尚未开始'}</dd>
          </div>
          <div>
            <dt>结束时间</dt>
            <dd>{job.finished_at ? formatDate(job.finished_at) : '未结束'}</dd>
          </div>
        </dl>
      </article>

      <article className="detail-card">
        <strong>任务摘要</strong>
        <p className="detail-copy">{payload}</p>
        {job.error_message && (
          <div className="error-inline">
            <strong>错误信息</strong>
            <p>{job.error_message}</p>
          </div>
        )}
      </article>
    </div>
  )
}

function SourcePreview({ source }: { source: AnswerSource }) {
  const pdfUrl = buildStorageFileUrl(source.origin_pdf_path)
  const irUrl = buildStorageFileUrl(source.ir_path)
  const contentListUrl = buildStorageFileUrl(joinStoragePath(source.bundle_root, 'content_list_v2.json'))
  const layoutUrl = buildStorageFileUrl(joinStoragePath(source.bundle_root, 'layout.json'))
  const pageWidth = source.page_width ?? 595
  const previewWidth = 430
  const scale = previewWidth / pageWidth
  const highlightBlocks = source.anchor_blocks.filter(
    (block) => block.page_idx === source.page_start && block.bbox_page,
  )

  return (
    <div className="detail-stack">
      {source.review_status === 'needs_review' && (
        <div className="warning-callout">
          <strong>来源文档已标记为需复核</strong>
          <p>
            该回答仍可查看引用与高亮，但建议进一步检查 `document_ir.json` 与 MinerU 原始输出。
          </p>
        </div>
      )}

      <article className="detail-card">
        <div className="detail-header">
          <strong>{source.source_filename}</strong>
          <span className={`review-badge ${source.review_status}`}>
            {source.review_status === 'needs_review' ? '需复核' : '引用可追溯'}
          </span>
        </div>
        <p className="detail-copy">{source.quote}</p>
        <small>
          页码 {source.page_start + 1}-{source.page_end + 1}
          {source.header_path.length ? ` · ${source.header_path.join(' / ')}` : ''}
        </small>
      </article>

      {pdfUrl && (
        <article className="pdf-preview-card">
          <div className="preview-caption">PDF 高亮溯源</div>
          <div className="pdf-stage" style={{ width: `${previewWidth}px` }}>
            <Document file={pdfUrl} loading={<div className="pdf-fallback">PDF 加载中...</div>}>
              <Page
                pageNumber={source.page_start + 1}
                width={previewWidth}
                renderAnnotationLayer={false}
                renderTextLayer={false}
                loading={<div className="pdf-fallback">PDF 页面加载中...</div>}
              />
            </Document>
            <div className="pdf-overlay">
              {highlightBlocks.map((block) => {
                const [x0, y0, x1, y1] = block.bbox_page ?? [0, 0, 0, 0]
                return (
                  <div
                    key={block.block_id}
                    className="highlight-box"
                    style={{
                      left: `${x0 * scale}px`,
                      top: `${y0 * scale}px`,
                      width: `${(x1 - x0) * scale}px`,
                      height: `${(y1 - y0) * scale}px`,
                    }}
                    title={`${block.block_type} · block ${block.block_id}`}
                  />
                )
              })}
            </div>
          </div>
        </article>
      )}

      <article className="detail-card">
        <strong>父块上下文</strong>
        <p className="detail-copy">{source.parent_context}</p>
      </article>

      <LinkPanel
        title="原始输出与中间结果"
        links={[
          ['document_ir.json', irUrl],
          ['content_list_v2.json', contentListUrl],
          ['layout.json', layoutUrl],
          ['origin.pdf', pdfUrl],
        ]}
      />

      {!!source.assets.length && (
        <article className="detail-card">
          <strong>关联资产</strong>
          <div className="asset-grid">
            {source.assets.map((asset) => {
              const assetUrl = buildStorageFileUrl(asset.absolute_path)
              return (
                <a
                  key={asset.asset_id}
                  className="asset-card"
                  href={assetUrl ?? '#'}
                  target="_blank"
                  rel="noreferrer"
                >
                  <span>{asset.asset_type}</span>
                  <strong>{asset.relative_path}</strong>
                </a>
              )
            })}
          </div>
        </article>
      )}
    </div>
  )
}

function LinkPanel({
  title,
  links,
}: {
  title: string
  links: Array<[string, string | null]>
}) {
  const visibleLinks = links.filter(([, url]) => !!url)
  if (!visibleLinks.length) {
    return null
  }

  return (
    <article className="detail-card">
      <strong>{title}</strong>
      <div className="link-list">
        {visibleLinks.map(([label, url]) => (
          <a key={label} href={url ?? '#'} target="_blank" rel="noreferrer">
            {label}
          </a>
        ))}
      </div>
    </article>
  )
}

function formatDate(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString('zh-CN', { hour12: false })
}

function taskBadgeClass(state: string) {
  if (state === 'completed') {
    return 'task-badge completed'
  }
  if (state === 'failed') {
    return 'task-badge failed'
  }
  if (state === 'running') {
    return 'task-badge running'
  }
  return 'task-badge pending'
}

function summarizePayload(payloadJson: string | null) {
  if (!payloadJson) {
    return '等待任务执行，尚未写入 payload。'
  }

  try {
    const payload = JSON.parse(payloadJson) as Record<string, unknown>
    const parts = Object.entries(payload)
      .slice(0, 4)
      .map(([key, value]) => `${key}: ${String(value)}`)
    return parts.join(' · ')
  } catch {
    return payloadJson
  }
}

function joinStoragePath(root: string | null | undefined, fileName: string) {
  if (!root) {
    return null
  }
  return `${root.replace(/[\\/]+$/, '')}/${fileName}`
}

function buildFolderNodes(documents: DocumentFileSummary[]): FolderNode[] {
  const seen = new Set<string>()
  for (const document of documents) {
    const parts = document.source_relative_path.split('/').filter(Boolean)
    for (let index = 0; index < parts.length - 1; index += 1) {
      seen.add(parts.slice(0, index + 1).join('/'))
    }
  }
  return Array.from(seen)
    .sort((left, right) => left.localeCompare(right, 'zh-CN'))
    .map((path) => ({
      path,
      label: path.split('/').at(-1) ?? path,
      depth: path.split('/').length - 1,
    }))
}

function parentFolderPath(relativePath: string) {
  const parts = relativePath.split('/').filter(Boolean)
  if (parts.length <= 1) {
    return ''
  }
  return parts.slice(0, -1).join('/')
}

export default App
