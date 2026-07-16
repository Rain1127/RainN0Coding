import apiClient from './client'
import type { ChatHistory } from '@/types/chat'
import type { PageResult } from '@/types/api'
import type { EntityId } from '@/types/entity'

export const getChatHistory = (appId: EntityId, pageSize = 50, lastCreateTime?: string) =>
  apiClient.get<any, PageResult<ChatHistory>>(`/chatHistory/app/${appId}`, {
    params: { pageSize, lastCreateTime },
  })
