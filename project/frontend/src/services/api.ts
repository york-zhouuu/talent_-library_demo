import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 300000 // 5 minutes for large uploads
})

// 共享范围
export type ShareScope = 'private' | 'team' | 'org' | 'custom'
export type SharePermission = 'view' | 'edit' | 'admin'

export interface PoolShare {
  user_id: string
  permission: SharePermission
}

export interface TalentPool {
  id: number
  name: string
  description: string | null
  owner_id: string
  share_scope: ShareScope
  team_id: string | null
  candidate_count: number
  shared_with: PoolShare[]
  created_at: string
  updated_at: string
}

export interface Candidate {
  id: number
  name: string
  phone: string | null
  email: string | null
  city: string | null
  current_company: string | null
  current_title: string | null
  years_of_experience: number | null
  expected_salary: number | null
  skills: string | null
  summary: string | null
  tags: { id: number; name: string }[]
}

export interface UploadProgress {
  total: number
  completed: number
  failed: number
  current: string
  currentStatus: 'uploading' | 'parsing' | 'done' | 'error'
  results: { filename: string; success: boolean; error?: string; candidate_id?: number }[]
}

// Talent Pools
export const getPools = async () => {
  const res = await api.get<{ items: TalentPool[] }>('/talent-pools')
  return res.data.items
}

export const getPool = async (id: number) => {
  const res = await api.get<TalentPool>(`/talent-pools/${id}`)
  return res.data
}

export const createPool = async (data: {
  name: string
  description?: string
  owner_id: string
  share_scope?: ShareScope
  team_id?: string
}) => {
  const res = await api.post<TalentPool>('/talent-pools', data)
  return res.data
}

export const updatePool = async (id: number, data: {
  name?: string
  description?: string
  share_scope?: ShareScope
  team_id?: string
}) => {
  const res = await api.put<TalentPool>(`/talent-pools/${id}`, data)
  return res.data
}

export const deletePool = async (id: number) => {
  await api.delete(`/talent-pools/${id}`)
}

// Pool Sharing
export const addPoolShare = async (poolId: number, userId: string, permission: SharePermission = 'view') => {
  await api.post(`/talent-pools/${poolId}/shares`, { user_id: userId, permission })
}

export const removePoolShare = async (poolId: number, userId: string) => {
  await api.delete(`/talent-pools/${poolId}/shares/${userId}`)
}

export const getPoolShares = async (poolId: number) => {
  const res = await api.get<{ shares: PoolShare[] }>(`/talent-pools/${poolId}/shares`)
  return res.data.shares
}

export const getPoolCandidates = async (poolId: number, page = 1, pageSize = 20) => {
  const res = await api.get<{ items: Candidate[]; total: number }>(`/talent-pools/${poolId}/candidates`, {
    params: { page, page_size: pageSize }
  })
  return res.data
}

export const addCandidateToPool = async (poolId: number, candidateId: number) => {
  await api.post(`/talent-pools/${poolId}/candidates/${candidateId}`)
}

export const removeCandidateFromPool = async (poolId: number, candidateId: number) => {
  await api.delete(`/talent-pools/${poolId}/candidates/${candidateId}`)
}

// Candidates
export const getCandidates = async (page = 1, pageSize = 20) => {
  const res = await api.get<{ items: Candidate[]; total: number }>('/candidates', {
    params: { page, page_size: pageSize }
  })
  return res.data
}

export const getCandidate = async (id: number) => {
  const res = await api.get<Candidate>(`/candidates/${id}`)
  return res.data
}

export const deleteCandidate = async (id: number) => {
  await api.delete(`/candidates/${id}`)
}

// Upload
export const uploadResume = async (file: File, onProgress?: (p: number) => void) => {
  const formData = new FormData()
  formData.append('file', file)
  const res = await api.post('/candidates/import', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e) => {
      if (onProgress && e.total) {
        onProgress(Math.round((e.loaded * 100) / e.total))
      }
    }
  })
  return res.data
}

export const uploadResumeBatch = async (
  files: File[],
  onProgress?: (progress: UploadProgress) => void
) => {
  const results: { success: boolean; filename: string; candidate_id?: number; error?: string }[] = []

  // 逐个文件上传，实时更新进度
  for (let i = 0; i < files.length; i++) {
    const file = files[i]

    // 更新状态：正在上传
    if (onProgress) {
      onProgress({
        total: files.length,
        completed: results.filter(r => r.success).length,
        failed: results.filter(r => !r.success).length,
        current: file.name,
        currentStatus: 'uploading',
        results: [...results]
      })
    }

    try {
      // 更新状态：正在解析
      if (onProgress) {
        onProgress({
          total: files.length,
          completed: results.filter(r => r.success).length,
          failed: results.filter(r => !r.success).length,
          current: file.name,
          currentStatus: 'parsing',
          results: [...results]
        })
      }

      const formData = new FormData()
      formData.append('file', file)

      const res = await api.post<{ candidate_id: number; parsed: Record<string, unknown> }>('/candidates/import', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 120000 // 2 minutes per file for AI parsing
      })

      results.push({
        success: true,
        filename: file.name,
        candidate_id: res.data.candidate_id
      })

      // 更新状态：完成
      if (onProgress) {
        onProgress({
          total: files.length,
          completed: results.filter(r => r.success).length,
          failed: results.filter(r => !r.success).length,
          current: file.name,
          currentStatus: 'done',
          results: [...results]
        })
      }
    } catch (e: unknown) {
      const error = e as { response?: { data?: { detail?: string } }; message?: string }
      const errorMsg = error.response?.data?.detail || error.message || 'Upload failed'
      results.push({
        success: false,
        filename: file.name,
        error: errorMsg
      })

      // 更新状态：失败
      if (onProgress) {
        onProgress({
          total: files.length,
          completed: results.filter(r => r.success).length,
          failed: results.filter(r => !r.success).length,
          current: file.name,
          currentStatus: 'error',
          results: [...results]
        })
      }
    }
  }

  return results
}

// Search
export interface SearchResult {
  id: number
  name: string
  current_title: string | null
  current_company: string | null
  city: string | null
  years_of_experience: number | null
  expected_salary: number | null
  skills: string | null
  match_reasons: { field: string; reason: string }[]
  fit_summary?: string  // 一句话匹配总结
}

export interface SearchResponse {
  session_id: string
  candidates: SearchResult[]
  total: number
  parsed_conditions?: Record<string, unknown>
}

// SSE Streaming Types
export type SearchStage = 'parsing' | 'expanding' | 'searching' | 'ranking' | 'explaining'

export interface StreamingStatusEvent {
  type: 'status'
  stage: SearchStage
  message: string
  progress?: number
}

export interface StreamingPartialResult {
  type: 'partial_result'
  candidates: SearchResult[]
  is_ranked: boolean
  more_coming: boolean
}

export interface StreamingFinalResult {
  type: 'final_result'
  candidates: SearchResult[]
  search_process: { terms: string[]; found: number }[]
  reasoning: string
  total: number
}

export type StreamingEvent = StreamingStatusEvent | StreamingPartialResult | StreamingFinalResult

export const searchCandidates = async (query: string, limit = 10, poolId?: number) => {
  const res = await api.post('/search/quick', { query, limit, pool_id: poolId })
  return res.data
}

export const intelligentSearch = async (query: string, limit = 20) => {
  const res = await api.post('/search/intelligent', { query, limit })
  return res.data
}

export const deepSearch = async (sessionId: string, query: string, limit = 10) => {
  const res = await api.post('/search/deep', { session_id: sessionId, query, limit })
  return res.data
}

// SSE Streaming Search
export const streamingSearch = async (
  query: string,
  limit: number,
  onEvent: (event: StreamingEvent) => void,
  onError?: (error: Error) => void
): Promise<void> => {
  try {
    const response = await fetch('/api/v1/search/natural/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, limit })
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const reader = response.body?.getReader()
    if (!reader) {
      throw new Error('No response body')
    }

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            onEvent(data as StreamingEvent)
          } catch {
            // Ignore parsing errors for incomplete JSON
          }
        }
      }
    }
  } catch (error) {
    if (onError) {
      onError(error as Error)
    } else {
      throw error
    }
  }
}

// Stats
export const getStats = async () => {
  const [candidates, pools] = await Promise.all([
    api.get<{ total: number }>('/candidates', { params: { page: 1, page_size: 1 } }),
    api.get<{ items: TalentPool[] }>('/talent-pools')
  ])

  const publicPools = pools.data.items.filter(p => p.is_public)
  const privatePools = pools.data.items.filter(p => !p.is_public)

  return {
    totalCandidates: candidates.data.total,
    totalPools: pools.data.items.length,
    publicPools: publicPools.length,
    privatePools: privatePools.length,
    publicCandidates: publicPools.reduce((sum, p) => sum + p.candidate_count, 0),
    privateCandidates: privatePools.reduce((sum, p) => sum + p.candidate_count, 0)
  }
}

export default api
