<script setup lang="ts">
import { computed } from 'vue'
import type { GenerationPhase, GenerationStatus } from '@/types/generation'

const props = defineProps<{
  phase: GenerationPhase | null
  status: GenerationStatus
}>()

const agents = [
  { id: 'intent', label: 'Intent', description: '识别意图' },
  { id: 'pm', label: 'PM', description: '整理需求' },
  { id: 'architect', label: 'Architect', description: '设计架构' },
  { id: 'image_collector', label: 'Image Collector', description: '整理图像资源' },
  { id: 'coder', label: 'Coder', description: '编写代码' },
  { id: 'reviewer', label: 'Reviewer', description: '检查质量' },
  { id: 'builder', label: 'Builder', description: '构建项目' },
] as const

const phaseAliases: Record<string, typeof agents[number]['id'] | 'done'> = {
  intent: 'intent',
  intent_agent: 'intent',
  pm: 'pm',
  pm_agent: 'pm',
  arch: 'architect',
  architect: 'architect',
  architect_agent: 'architect',
  image_collector: 'image_collector',
  image_collector_agent: 'image_collector',
  code: 'coder',
  code_retry: 'coder',
  coder: 'coder',
  coder_agent: 'coder',
  review: 'reviewer',
  reviewer: 'reviewer',
  reviewer_agent: 'reviewer',
  build: 'builder',
  builder: 'builder',
  builder_agent: 'builder',
  completed: 'done',
  done: 'done',
}

const normalizedPhase = computed(() => props.phase ? phaseAliases[props.phase] : null)
const currentIndex = computed(() => agents.findIndex((agent) => agent.id === normalizedPhase.value))
const knownPhase = computed(() => props.phase === null || normalizedPhase.value !== undefined)

function stepStatus(index: number) {
  if (props.status === 'success') return 'complete'
  if (currentIndex.value < 0) return 'pending'
  if (index < currentIndex.value) return 'complete'
  if (index === currentIndex.value) return props.status === 'failed' ? 'failed' : 'current'
  return 'pending'
}

function statusText(index: number) {
  if (props.phase === 'done' && props.status === 'failed') return '未完成'
  const status = stepStatus(index)
  if (status === 'complete') return '已完成'
  if (status === 'current') return '进行中'
  if (status === 'failed') return '执行失败'
  return '待处理'
}
</script>

<template>
  <section class="agent-progress" aria-labelledby="agent-progress-title">
    <div class="agent-progress__heading">
      <div>
        <p class="agent-progress__eyebrow">Agent workflow</p>
        <h2 id="agent-progress-title">生成进度</h2>
      </div>
      <span class="agent-progress__run-status" role="status" aria-live="polite" aria-atomic="true">{{ status === 'connecting' ? '正在连接…' : status === 'cancelled' ? '已取消' : status === 'failed' ? '需要处理' : status === 'success' ? '已完成' : status === 'running' ? '生成中…' : '等待开始' }}</span>
    </div>

    <ol class="agent-progress__list">
      <li
        v-for="(agent, index) in agents"
        :key="agent.id"
        :data-agent="agent.id"
        :data-step-status="stepStatus(index)"
        :aria-current="stepStatus(index) === 'current' ? 'step' : undefined"
        class="agent-progress__step"
      >
        <span class="agent-progress__marker" aria-hidden="true">{{ stepStatus(index) === 'complete' ? 'OK' : index + 1 }}</span>
        <span class="agent-progress__copy">
          <strong>{{ agent.label }}</strong>
          <span>{{ agent.description }}</span>
        </span>
        <span class="agent-progress__status">{{ statusText(index) }}</span>
      </li>
    </ol>

    <p v-if="!knownPhase" class="agent-progress__unknown" data-unknown-phase role="status">
      正在处理扩展阶段… <code>{{ phase }}</code>
    </p>
  </section>
</template>

<style scoped>
.agent-progress {
  padding: var(--space-5);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
}

.agent-progress__heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
}

.agent-progress__eyebrow {
  margin: 0 0 var(--space-1);
  color: var(--color-primary);
  font-family: var(--font-mono);
  font-size: 0.7rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.agent-progress h2 { margin: 0; font-size: 1rem; }

.agent-progress__run-status {
  padding: 3px 8px;
  border-radius: var(--radius-full);
  color: var(--color-text-muted);
  background: var(--color-surface-subtle);
  font-size: 0.75rem;
  font-weight: 700;
}

.agent-progress__list {
  display: grid;
  gap: var(--space-2);
  margin: var(--space-4) 0 0;
  padding: 0;
  list-style: none;
}

.agent-progress__step {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--space-2);
  min-height: 48px;
  padding: var(--space-2);
  border-radius: var(--radius-sm);
}

.agent-progress__step[data-step-status="current"] { background: var(--color-primary-soft); }
.agent-progress__step[data-step-status="failed"] { background: var(--color-danger-soft); }

.agent-progress__marker {
  display: grid;
  width: 26px;
  height: 26px;
  place-items: center;
  border: 1px solid var(--color-border);
  border-radius: 50%;
  color: var(--color-text-muted);
  font-size: 0.72rem;
  font-weight: 800;
}

[data-step-status="complete"] .agent-progress__marker {
  border-color: var(--color-success);
  color: #fff;
  background: var(--color-success);
}

[data-step-status="current"] .agent-progress__marker {
  border-color: var(--color-primary);
  color: #fff;
  background: var(--color-primary);
}

.agent-progress__copy { display: grid; min-width: 0; }
.agent-progress__copy strong { overflow: hidden; font-size: 0.82rem; text-overflow: ellipsis; }
.agent-progress__copy span,
.agent-progress__status { color: var(--color-text-muted); font-size: 0.72rem; }
.agent-progress__status { font-weight: 700; }

.agent-progress__unknown {
  margin: var(--space-3) 0 0;
  color: var(--color-warning);
  font-size: 0.78rem;
}

.agent-progress__unknown code { font-family: var(--font-mono); }
</style>
