import type { EntityId } from '@/types/entity'
import type { GenerationTask } from '@/types/generation'

export class GenerationRequestError extends Error {
  constructor(message: string, readonly retryable = false, readonly httpStatus?: number) { super(message) }
}

export function generationTaskUrl(suffix = '') {
  return `${import.meta.env.VITE_API_BASE ?? '/api'}/app/generation/tasks${suffix}`
}

async function request<T>(suffix: string, signal: AbortSignal, body?: object): Promise<T> {
  const response = await fetch(generationTaskUrl(suffix), {
    method: body ? 'POST' : 'GET',
    credentials: 'include', signal,
    headers: { Accept: 'application/json', ...(body ? { 'Content-Type': 'application/json' } : {}) },
    ...(body ? { body: JSON.stringify(body) } : {}),
  })
  if (!response.ok) {
    throw new GenerationRequestError(`任务请求失败（HTTP ${response.status}）`, response.status >= 500 || response.status === 429, response.status)
  }
  const result = await response.json() as { code: number; data: T; message?: string }
  if (result.code !== 0) throw new GenerationRequestError(result.message || '任务请求失败')
  return result.data
}

export const createGenerationTask = (appId: EntityId, message: string, idempotencyKey: string, signal: AbortSignal) =>
  request<GenerationTask>('', signal, { appId: String(appId), message, idempotencyKey })

export const getLatestGenerationTask = (appId: EntityId, signal: AbortSignal) =>
  request<GenerationTask | null>(`/latest?appId=${encodeURIComponent(String(appId))}`, signal)

export const getGenerationTask = (taskId: string, signal: AbortSignal) =>
  request<GenerationTask>(`/${encodeURIComponent(taskId)}`, signal)

export const controlGenerationTask = (taskId: string, action: 'pause' | 'resume', signal: AbortSignal) =>
  request<GenerationTask>(`/${encodeURIComponent(taskId)}/${action}`, signal, {})
