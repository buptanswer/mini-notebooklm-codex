import type {
  AskStreamDone,
  AskStreamMeta,
  AskRequest,
  AskResponse,
  BulkDeleteResponse,
  DocumentUpdateRequest,
  DocumentFileSummary,
  FolderUpdateResponse,
  KnowledgeBaseCreateRequest,
  KnowledgeBaseUpdateRequest,
  KnowledgeBaseSummary,
  PipelineJobSummary,
  SystemOverview,
  UploadBatchResponse,
} from './types'

async function request<T>(input: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (!(init?.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(input, {
    ...init,
    headers,
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Request failed with status ${response.status}`)
  }

  return (await response.json()) as T
}

export function fetchSystemOverview() {
  return request<SystemOverview>('/api/v1/system/overview')
}

export function fetchKnowledgeBases() {
  return request<KnowledgeBaseSummary[]>('/api/v1/knowledge-bases')
}

export function createKnowledgeBase(payload: KnowledgeBaseCreateRequest) {
  return request<KnowledgeBaseSummary>('/api/v1/knowledge-bases', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateKnowledgeBase(
  knowledgeBaseId: string,
  payload: KnowledgeBaseUpdateRequest,
) {
  return request<KnowledgeBaseSummary>(`/api/v1/knowledge-bases/${knowledgeBaseId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function deleteKnowledgeBase(knowledgeBaseId: string) {
  return request<KnowledgeBaseSummary>(`/api/v1/knowledge-bases/${knowledgeBaseId}`, {
    method: 'DELETE',
  })
}

export function fetchKnowledgeBaseDocuments(knowledgeBaseId: string) {
  return request<DocumentFileSummary[]>(
    `/api/v1/knowledge-bases/${knowledgeBaseId}/documents`,
  )
}

export function fetchKnowledgeBaseJobs(knowledgeBaseId: string) {
  return request<PipelineJobSummary[]>(
    `/api/v1/knowledge-bases/${knowledgeBaseId}/jobs`,
  )
}

export function updateKnowledgeBaseDocument(
  knowledgeBaseId: string,
  documentId: string,
  payload: DocumentUpdateRequest,
) {
  return request<DocumentFileSummary>(
    `/api/v1/knowledge-bases/${knowledgeBaseId}/documents/${documentId}`,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  )
}

export function deleteKnowledgeBaseDocument(
  knowledgeBaseId: string,
  documentId: string,
) {
  return request<DocumentFileSummary>(
    `/api/v1/knowledge-bases/${knowledgeBaseId}/documents/${documentId}`,
    {
      method: 'DELETE',
    },
  )
}

export function bulkDeleteKnowledgeBaseDocuments(
  knowledgeBaseId: string,
  documentIds: string[],
) {
  return request<BulkDeleteResponse>(
    `/api/v1/knowledge-bases/${knowledgeBaseId}/documents/bulk-delete`,
    {
      method: 'POST',
      body: JSON.stringify({ document_ids: documentIds }),
    },
  )
}

export function renameKnowledgeBaseFolder(
  knowledgeBaseId: string,
  folderPath: string,
  newFolderPath: string,
) {
  return request<FolderUpdateResponse>(
    `/api/v1/knowledge-bases/${knowledgeBaseId}/folders/rename`,
    {
      method: 'POST',
      body: JSON.stringify({
        folder_path: folderPath,
        new_folder_path: newFolderPath,
      }),
    },
  )
}

export function deleteKnowledgeBaseFolder(
  knowledgeBaseId: string,
  folderPath: string,
) {
  return request<FolderUpdateResponse>(
    `/api/v1/knowledge-bases/${knowledgeBaseId}/folders/delete`,
    {
      method: 'POST',
      body: JSON.stringify({ folder_path: folderPath }),
    },
  )
}

export function askKnowledgeBase(
  knowledgeBaseId: string,
  payload: AskRequest,
) {
  return request<AskResponse>(`/api/v1/knowledge-bases/${knowledgeBaseId}/ask`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function uploadKnowledgeBaseFiles(
  knowledgeBaseId: string,
  entries: Array<{ file: File; relativePath?: string }>,
) {
  const formData = new FormData()
  for (const entry of entries) {
    formData.append('files', entry.file, entry.file.name)
    formData.append('relative_paths', entry.relativePath ?? entry.file.name)
  }

  return request<UploadBatchResponse>(
    `/api/v1/knowledge-bases/${knowledgeBaseId}/upload`,
    {
      method: 'POST',
      body: formData,
    },
  )
}

export async function streamAskKnowledgeBase(
  knowledgeBaseId: string,
  payload: AskRequest,
  handlers: {
    onMeta: (payload: AskStreamMeta) => void
    onDelta: (text: string) => void
    onDone: (payload: AskStreamDone) => void
  },
) {
  const response = await fetch(`/api/v1/knowledge-bases/${knowledgeBaseId}/ask/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })

  if (!response.ok || !response.body) {
    const text = await response.text()
    throw new Error(text || `Request failed with status ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) {
      break
    }

    buffer += decoder.decode(value, { stream: true })
    const frames = buffer.split('\n\n')
    buffer = frames.pop() ?? ''

    for (const frame of frames) {
      const lines = frame.split('\n')
      const event = lines.find((line) => line.startsWith('event:'))?.slice(6).trim()
      const data = lines
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trim())
        .join('\n')
      if (!event || !data) {
        continue
      }
      const parsed = JSON.parse(data)
      if (event === 'meta') {
        handlers.onMeta(parsed as AskStreamMeta)
      } else if (event === 'delta') {
        handlers.onDelta((parsed as { text: string }).text)
      } else if (event === 'done') {
        handlers.onDone(parsed as AskStreamDone)
      } else if (event === 'error') {
        throw new Error((parsed as { message: string }).message)
      }
    }
  }
}

export function buildStorageFileUrl(path: string | null | undefined) {
  if (!path) {
    return null
  }
  const params = new URLSearchParams({ path })
  return `/api/v1/files?${params.toString()}`
}
