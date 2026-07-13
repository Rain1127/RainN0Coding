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
  | 'running'
  | 'success'
  | 'failed'
  | 'cancelled'

export interface GenerationEvent {
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
