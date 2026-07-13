import apiClient from './client'
import type { IntentTreeResponse } from '@/types/intent'

export const getIntentTree = () =>
  apiClient.get<any, IntentTreeResponse>('/intent-config/tree')

export const saveIntentTree = (treeJson: string) =>
  apiClient.post<any, boolean>('/intent-config/save', { treeJson })

export const resetIntentTree = () =>
  apiClient.post<any, boolean>('/intent-config/reset')
