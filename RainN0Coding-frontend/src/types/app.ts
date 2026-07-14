export type CodeGenType = 'html' | 'multi_file' | 'vue_project' | 'python' | 'java' | 'go' | 'rust' | 'nodejs' | 'generic'

export interface AppVO {
  id: number
  appName: string
  cover: string
  initPrompt: string
  codeGenType: CodeGenType
  deployKey: string
  deployedTime: string
  priority: number
  userId: number
  currentVersion: number
  createTime: string
  updateTime: string
  editTime: string
  userVO?: {
    id: number
    userName: string
  }
}

export interface AppAddRequest {
  initPrompt?: string
}

export interface AppUpdateRequest {
  id: number
  appName: string
}

export interface AppAdminUpdateRequest {
  id: number
  appName?: string
  cover?: string
  priority?: number
}

export interface AppDeployRequest {
  appId: number
}

export interface AppQueryRequest {
  pageNum: number
  pageSize: number
  sortField?: string
  sortOrder?: string
  id?: number
  appName?: string
  codeGenType?: string
  userId?: number
}
