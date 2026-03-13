export type BootstrapStatus = {
  storage_ready: boolean
  database_ready: boolean
  qdrant_ready: boolean
  warnings: string[]
}

export type StorageStatus = {
  storage_root: string
  sqlite_path: string
  qdrant_mode: 'local' | 'remote'
  qdrant_location: string
  qdrant_collection: string
  qdrant_vector_size: number
}

export type SystemCounts = {
  knowledge_bases: number
  documents: number
  tasks: number
  child_chunks: number
}

export type ArchitectureModule = {
  key: string
  name: string
  summary: string
  status: 'ready' | 'warning' | 'planned'
}

export type RoadmapStage = {
  key: string
  name: string
  status: 'completed' | 'next' | 'planned'
  summary: string
}

export type SystemOverview = {
  app_name: string
  api_prefix: string
  debug: boolean
  bootstrap: BootstrapStatus
  storage: StorageStatus
  counts: SystemCounts
  architecture: ArchitectureModule[]
  roadmap: RoadmapStage[]
}

export type KnowledgeBaseSummary = {
  id: string
  name: string
  slug: string
  description: string | null
  status: string
  storage_root: string
  document_count: number
  task_count: number
  created_at: string
  updated_at: string
}

export type KnowledgeBaseCreateRequest = {
  name: string
  description?: string
}

export type KnowledgeBaseUpdateRequest = {
  name: string
  description?: string
}

export type DocumentFileSummary = {
  id: string
  knowledge_base_id: string
  source_filename: string
  source_format: string
  source_path: string
  source_relative_path: string
  source_sha1: string | null
  document_title: string | null
  bundle_root: string | null
  origin_pdf_path: string | null
  ir_path: string | null
  enriched_ir_path: string | null
  parsing_status: string
  chunking_status: string
  indexing_status: string
  review_status: 'pending' | 'ok' | 'needs_review'
  parser_warning_count: number
  unknown_block_count: number
  parent_chunk_count: number
  child_chunk_count: number
  review_summary: string | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export type PipelineJobSummary = {
  id: string
  knowledge_base_id: string | null
  document_id: string | null
  stage: string
  state: string
  attempts: number
  error_message: string | null
  payload_json: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
  updated_at: string
}

export type UploadBatchResponse = {
  knowledge_base_id: string
  accepted_files: number
  jobs: PipelineJobSummary[]
}

export type DocumentUpdateRequest = {
  new_name?: string
  new_parent_path?: string
}

export type BulkDeleteResponse = {
  deleted_ids: string[]
  deleted_count: number
}

export type FolderUpdateResponse = {
  updated_ids?: string[]
  updated_count?: number
  deleted_ids?: string[]
  deleted_count?: number
}

export type SourceAnchorBlock = {
  block_id: string
  block_type: string
  page_idx: number
  bbox_page: [number, number, number, number] | null
}

export type SourceAsset = {
  asset_id: string
  asset_type: string
  relative_path: string
  absolute_path: string
}

export type AnswerSource = {
  source_id: string
  child_chunk_id: string
  parent_chunk_id: string
  document_id: string
  source_sha1: string | null
  source_filename: string
  document_title: string | null
  header_path: string[]
  page_start: number
  page_end: number
  page_width: number | null
  page_height: number | null
  source_block_ids: string[]
  quote: string
  parent_context: string
  origin_pdf_path: string | null
  ir_path: string | null
  bundle_root: string | null
  review_status: 'pending' | 'ok' | 'needs_review'
  assets: SourceAsset[]
  anchor_blocks: SourceAnchorBlock[]
}

export type RetrievalTraceHit = {
  child_chunk_id: string
  source_filename: string
  chunk_type: string
  channels: string[]
  vector_rank: number | null
  keyword_rank: number | null
  vector_score: number | null
  keyword_score: number | null
  fusion_score: number
  rerank_score: number | null
  page_start: number
  page_end: number
}

export type AnswerUsage = {
  retrieval_candidates: number
  reranked_candidates: number
  prompt_tokens: number | null
  completion_tokens: number | null
  total_tokens: number | null
}

export type AskRequest = {
  question: string
  vector_top_k?: number
  keyword_top_k?: number
  fused_top_k?: number
  rerank_top_n?: number
  max_sources?: number
  max_assets?: number
}

export type AskResponse = {
  knowledge_base_id: string
  question: string
  answer: string
  answer_model: string
  rerank_model: string
  embedding_model: string
  generated_at: string
  sources: AnswerSource[]
  retrieval_trace: RetrievalTraceHit[]
  usage: AnswerUsage
}

export type AskStreamMeta = {
  knowledge_base_id: string
  question: string
  answer_model: string
  rerank_model: string
  embedding_model: string
  sources: AnswerSource[]
  retrieval_trace: RetrievalTraceHit[]
}

export type AskStreamDone = AskResponse
