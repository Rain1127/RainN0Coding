export interface ChatHistory {
  id: number
  message: string
  messageType: 'user' | 'ai'
  appId: number
  userId: number
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
