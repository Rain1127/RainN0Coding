export type KnownGenerationPhase =
  | 'intent'
  | 'pm'
  | 'architect'
  | 'coder'
  | 'image_collector'
  | 'reviewer'
  | 'builder'
  | 'done'

export type GenerationPhase = KnownGenerationPhase | (string & {})

export type GenerationStatus =
  | 'idle'
  | 'connecting'
  | 'queued'
  | 'running'
  | 'success'
  | 'failed'
  | 'cancelled'

export interface GenerationEvent {
  id?: string
  type?: string
  sse_event?: string
  error?: boolean
  code?: number | string
  phase?: GenerationPhase
  status?: string
  message?: string
  text?: string
  detail?: string
  content?: string
  source?: string
  file_path?: string
  path?: string
  name?: string
  language?: string
  size?: number | string
  [key: string]: unknown
}

export interface GenerationTask {
  taskId: string
  appId: string
  status: 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'INTERRUPTED'
  errorMessage: string | null
  lastEventId: string
  retryAllowed: boolean
}

export interface GeneratedFile {
  path: string
  language: string
  size?: number | string
}

export interface GenerationState {
  status: GenerationStatus
  phase: GenerationPhase | null
  events: GenerationEvent[]
  files: GeneratedFile[]
  error: string | null
}
