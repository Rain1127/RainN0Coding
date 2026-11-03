import apiClient from './client'
import type {
  AppVO, AppAddRequest, AppUpdateRequest,
  AppAdminUpdateRequest, AppQueryRequest,
} from '@/types/app'
import type { PageResult, DeleteRequest } from '@/types/api'
import type { EntityId } from '@/types/entity'
import type { GenerationInstruction, GenerationStepEvent, InstructionTarget } from '@/types/generation'

export const listGenerationSteps = (appId: EntityId, runId: string, after = 0) =>
  apiClient.get<any, { events: GenerationStepEvent[]; step_cursor: number; has_more: boolean }>('/app/chat/gen/steps', {
    params: { appId, runId, after, limit: 100 },
  })

export const listGenerationInstructions = (appId: EntityId, runId: string) =>
  apiClient.get<any, { enabled: boolean; run_status: string; instructions: GenerationInstruction[] }>('/app/chat/gen/instructions', {
    params: { appId, runId },
  })

export const updateGenerationInstruction = (appId: EntityId, runId: string, instructionId: string,
  payload: { action: 'submit'; target: InstructionTarget; content: string } | { action: 'cancel' }) =>
  apiClient.post<any, GenerationInstruction>('/app/chat/gen/instructions', { appId, runId, instructionId, ...payload })

export const createApp = (body: AppAddRequest) =>
  apiClient.post<any, EntityId>('/app/add', body)

export const getAppVO = (id: EntityId) =>
  apiClient.get<any, AppVO>('/app/get/vo', { params: { id } })

export const updateApp = (body: AppUpdateRequest) =>
  apiClient.post<any, boolean>('/app/update', body)

export const deleteApp = (body: DeleteRequest) =>
  apiClient.post<any, boolean>('/app/delete', body)

export const listMyApps = (body: AppQueryRequest) =>
  apiClient.post<any, PageResult<AppVO>>('/app/my/list/page/vo', body)

export const listGoodApps = (body: AppQueryRequest) =>
  apiClient.post<any, PageResult<AppVO>>('/app/good/list/page/vo', body)

export const deployApp = (appId: EntityId) =>
  apiClient.post<any, string>('/app/deploy', { appId })

export const downloadApp = (appId: EntityId) =>
  `/api/app/download/${appId}`

export interface ArtifactVersion { id: string; number: number; description: string }
export const listArtifactVersions = (appId: EntityId) =>
  apiClient.get<any, ArtifactVersion[]>(`/app/${encodeURIComponent(String(appId))}/versions`)
export const rollbackArtifactVersion = (appId: EntityId, versionId: string) =>
  apiClient.post<any, boolean>(`/app/${encodeURIComponent(String(appId))}/versions/${encodeURIComponent(versionId)}/rollback`)

// Admin
export const adminListApps = (body: AppQueryRequest) =>
  apiClient.post<any, PageResult<AppVO>>('/app/admin/list/page/vo', body)

export const adminDeleteApp = (body: DeleteRequest) =>
  apiClient.post<any, boolean>('/app/admin/delete', body)

export const adminUpdateApp = (body: AppAdminUpdateRequest) =>
  apiClient.post<any, boolean>('/app/admin/update', body)

export const adminGetAppVO = (id: EntityId) =>
  apiClient.get<any, AppVO>('/app/admin/get/vo', { params: { id } })
