import apiClient from './client'
import type {
  AppVO, AppAddRequest, AppUpdateRequest,
  AppAdminUpdateRequest, AppQueryRequest,
} from '@/types/app'
import type { PageResult, DeleteRequest } from '@/types/api'
import type { EntityId } from '@/types/entity'

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

// Admin
export const adminListApps = (body: AppQueryRequest) =>
  apiClient.post<any, PageResult<AppVO>>('/app/admin/list/page/vo', body)

export const adminDeleteApp = (body: DeleteRequest) =>
  apiClient.post<any, boolean>('/app/admin/delete', body)

export const adminUpdateApp = (body: AppAdminUpdateRequest) =>
  apiClient.post<any, boolean>('/app/admin/update', body)

export const adminGetAppVO = (id: EntityId) =>
  apiClient.get<any, AppVO>('/app/admin/get/vo', { params: { id } })
