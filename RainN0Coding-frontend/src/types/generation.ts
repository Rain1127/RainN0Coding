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
  | 'pausing'
  | 'paused'
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

export interface GenerationStepEvent {
  seq: number
  run_id: string
  step_id: string
  type: string
  timestamp: number
  payload: {
    tool?: string
    path?: string
    status?: string
    elapsed_ms?: number | null
    contract_version?: number
    before_hash?: string
    after_hash?: string
    result?: { ok?: boolean; reason?: string; status?: string; match_count?: number }
    [key: string]: unknown
  }
}

export type InstructionTarget = 'next_step' | 'next_run'
export interface GenerationInstruction {
  instruction_id: string
  run_id: string
  target: InstructionTarget
  content: string
  status: 'queued' | 'planning' | 'prepared' | 'included' | 'rejected' | 'cancelled' | 'next_run_ready'
  reason: string | null
  step_id: string | null
  contract_version: number | null
}

export interface GenerationTask {
  taskId: string
  appId: string
  status: 'QUEUED' | 'RUNNING' | 'PAUSING' | 'PAUSED' | 'SUCCEEDED' | 'FAILED' | 'INTERRUPTED'
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
