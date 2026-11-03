<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { listGenerationSteps } from '@/api/app'
import type { EntityId } from '@/types/entity'
import type { GenerationEvent, GenerationStepEvent } from '@/types/generation'
const props = defineProps<{ appId: EntityId; runId: string; events: GenerationEvent[] }>()
const persisted = ref<GenerationStepEvent[]>([])
const cursor = ref(0)
const more = ref(false)
const pending = ref(false)
const error = ref('')
let sequence = 0
const steps = computed(() => {
  const bySequence = new Map<number, GenerationStepEvent>()
  for (const step of persisted.value) if (step.run_id === props.runId) bySequence.set(step.seq, step)
  for (const event of props.events) {
    if (event.type !== 'step_event') continue
    const step = event.step_event as GenerationStepEvent | undefined
    if (step && step.run_id === props.runId && Number.isSafeInteger(step.seq)) bySequence.set(step.seq, step)
  }
  return [...bySequence.values()].sort((a, b) => a.seq - b.seq)
})
const labels: Record<string, string> = {
  model_request: '准备模型请求', model_submitted: '模型调用已开始', model_result: '模型已返回',
  tool_intent: '准备执行工具', tool_result: '工具已返回', tool_rejected: '工具被拒绝',
  recovery_conflict: '恢复遇到文件冲突', model_interrupted: '请求结果待核对', contract_fixed: '验收合同已固定',
  instruction_included: '补充指令已纳入请求', instruction_rejected: '补充指令被拒绝',
}
async function load() {
  if (pending.value) return
  const current = sequence
  pending.value = true
  error.value = ''
  try {
    const page = await listGenerationSteps(props.appId, props.runId, cursor.value)
    if (current !== sequence) return
    persisted.value.push(...page.events)
    cursor.value = page.step_cursor
    more.value = page.has_more
  } catch { if (current === sequence) error.value = '步骤记录暂不可用，可稍后刷新' }
  finally { if (current === sequence) pending.value = false }
}
watch(() => [props.appId, props.runId], () => {
  sequence++
  persisted.value = []
  cursor.value = 0
  more.value = false
  pending.value = false
  void load()
}, { immediate: true })
onBeforeUnmount(() => sequence++)
</script>
<template>
  <section aria-label="执行步骤">
    <details>
      <summary>执行轨迹 · {{ steps.length }} 条</summary>
      <button type="button" :disabled="pending" @click="load">{{ more ? '加载更多步骤' : '补齐步骤记录' }}</button>
      <p v-if="error" role="status">{{ error }}</p>
      <ol>
        <li v-for="step in steps" :key="step.seq">
          <details>
            <summary>{{ labels[step.type] ?? step.type }} {{ step.payload.tool }} {{ step.payload.path }}</summary>
            <p>状态：{{ step.payload.result?.ok === false ? '失败' : step.payload.status }}
              <span v-if="step.payload.elapsed_ms != null"> · {{ step.payload.elapsed_ms }} ms</span></p>
            <p v-if="step.payload.result?.reason">{{ step.payload.result.reason }}</p>
            <pre>{{ JSON.stringify(step.payload, null, 2) }}</pre>
          </details>
        </li>
      </ol>
    </details>
  </section>
</template>
