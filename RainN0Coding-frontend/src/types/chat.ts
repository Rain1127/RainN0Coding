import type { EntityId } from './entity'

export interface ChatHistory {
  id: EntityId
  message: string
  messageType: 'user' | 'ai'
  appId: EntityId
  userId: EntityId
  createTime: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'ai'
  content: string
  timestamp: number
  isStreaming?: boolean
}

export interface ChatHistoryPageRequest {
  pageSize?: number
  lastCreateTime?: string
}
