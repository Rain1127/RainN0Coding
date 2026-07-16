import apiClient from './client'
import type { UserVO, UserAddRequest, UserUpdateRequest, UserQueryRequest } from '@/types/user'
import type { PageResult, DeleteRequest } from '@/types/api'
import type { EntityId } from '@/types/entity'

export const listUsers = (body: UserQueryRequest) =>
  apiClient.post<any, PageResult<UserVO>>('/user/list/page/vo', body)

export const addUser = (body: UserAddRequest) =>
  apiClient.post<any, EntityId>('/user/add', body)

export const deleteUser = (body: DeleteRequest) =>
  apiClient.post<any, boolean>('/user/delete', body)

export const updateUser = (body: UserUpdateRequest) =>
  apiClient.post<any, boolean>('/user/update', body)

export const getUserVO = (id: EntityId) =>
  apiClient.get<any, UserVO>('/user/get/vo', { params: { id } })
