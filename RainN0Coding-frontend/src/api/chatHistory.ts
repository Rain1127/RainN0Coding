import apiClient from './client'
import type { ChatHistory } from '@/types/chat'
import type { PageResult } from '@/types/api'

export const getChatHistory = (appId: number, pageSize = 50, lastCreateTime?: string) =>
  apiClient.get<any, PageResult<ChatHistory>>(`/chatHistory/app/${appId}`, {
    params: { pageSize, lastCreateTime },
  })
