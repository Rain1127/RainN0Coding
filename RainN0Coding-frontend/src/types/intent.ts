export interface IntentNode {
  key: string
  title: string
  type?: string
  source?: string
  enabled?: boolean
  description?: string
  examples?: string[]
  parentKey?: string | null
  sortOrder?: number
  collection?: string
  children?: IntentNode[]
}

export interface IntentTreeResponse {
  customized: boolean
  treeJson: string
}
