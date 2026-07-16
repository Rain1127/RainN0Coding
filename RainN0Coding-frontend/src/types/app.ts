import type { EntityId } from './entity'

export type CodeGenType = 'html' | 'multi_file' | 'vue_project' | 'python' | 'java' | 'go' | 'rust' | 'nodejs' | 'generic'

export interface AppVO {
  id: EntityId
  appName: string
  cover: string
  initPrompt: string
  codeGenType: CodeGenType
  deployKey: string
  deployedTime: string
  priority: number
  userId: EntityId
  currentVersion: number
  createTime: string
  updateTime: string
  editTime: string
  userVO?: {
    id: EntityId
    userName: string
  }
}

export interface AppAddRequest {
  initPrompt?: string
}

export interface AppUpdateRequest {
  id: EntityId
  appName: string
}

export interface AppAdminUpdateRequest {
  id: EntityId
  appName?: string
  cover?: string
  priority?: number
}

export interface AppDeployRequest {
  appId: EntityId
}

export interface AppQueryRequest {
  pageNum: number
  pageSize: number
  sortField?: string
  sortOrder?: string
  id?: EntityId
  appName?: string
  codeGenType?: string
  userId?: EntityId
}
