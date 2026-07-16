export interface BaseResponse<T = unknown> {
  code: number
  data: T
  message: string
}

export interface PageResult<T> {
  records: T[]
  total?: number
  size?: number
  current?: number
  pages?: number
  pageNumber?: number
  pageSize?: number
  totalRow?: number
  totalPage?: number
}

export interface PageRequest {
  pageNum: number
  pageSize: number
  sortField?: string
  sortOrder?: string
}

export interface DeleteRequest {
  id: EntityId
}
import type { EntityId } from './entity'
