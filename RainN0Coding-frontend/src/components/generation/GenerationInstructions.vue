<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { listGenerationInstructions, updateGenerationInstruction } from '@/api/app'
import { newRequestId } from '@/stores/generation'
import type { EntityId } from '@/types/entity'
import type { GenerationInstruction, InstructionTarget } from '@/types/generation'

const props = defineProps<{ appId: EntityId; runId: string; active: boolean; eventCount: number }>()
const emit = defineEmits<{ nextRun: [content: string] }>()
const rows = ref<GenerationInstruction[]>([])
const enabled = ref(false)
const text = ref('')
const target = ref<InstructionTarget>('next_step')
const busy = ref(false)
const error = ref('')
let mounted = true
let loading = false
let timer: ReturnType<typeof setInterval> | undefined
let retry: { instructionId: string; target: InstructionTarget; content: string } | undefined

const labels: Record<GenerationInstruction['status'], string> = {
  queued: '已接收，等待处理', planning: '正在核对纠偏', prepared: '等待模型回执',
  included: '已纳入模型请求', rejected: '已拒绝', cancelled: '已取消', next_run_ready: '可用于下一轮',
}
const reasons: Record<string, string> = {
  run_ended_before_model_receipt: '本轮结束前没有后续模型回执',
  cancelled_by_owner: '已由用户取消',
  scope_would_expand_or_is_empty: '纠偏超出本轮可修改范围',
  scope_conflicts_with_existing_candidate_edits: '候选中已有新范围之外的修改',
  correction_conditions_not_independently_verifiable: '缺少可执行的验收条件',
  correction_incompatible_with_current_task: '纠偏与当前任务存在冲突',
  correction_has_no_verified_effect: '未找到可核对的范围或验收变更',
}

async function refresh() {
  if (loading || !mounted) return
  loading = true
  try {
    const response = await listGenerationInstructions(props.appId, props.runId)
    if (mounted) {
      enabled.value = response.enabled
      rows.value = response.instructions
    }
  } catch {
    // The Java queue can exist briefly before Python registers the run.
  } finally {
    loading = false
  }
}

async function submit() {
  const content = text.value.trim()
  if (!content || busy.value) return
  if (!retry || retry.content !== content || retry.target !== target.value) {
    retry = { instructionId: newRequestId(), target: target.value, content }
  }
  busy.value = true
  error.value = ''
  try {
    await updateGenerationInstruction(props.appId, props.runId, retry.instructionId,
      { action: 'submit', target: retry.target, content: retry.content })
    retry = undefined
    text.value = ''
    await refresh()
  } catch {
    if (mounted) error.value = '暂未收到确认，可以重试这条指令。'
  } finally {
    busy.value = false
  }
}

async function cancel(instructionId: string) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    await updateGenerationInstruction(props.appId, props.runId, instructionId, { action: 'cancel' })
  } catch {
    if (mounted) error.value = '取消未确认，可能已开始处理。'
  } finally {
    busy.value = false
    await refresh()
  }
}

watch(() => [props.active, props.eventCount], () => void refresh())
onMounted(() => {
  void refresh()
  timer = setInterval(() => { if (props.active) void refresh() }, 4000)
})
onBeforeUnmount(() => {
  mounted = false
  clearInterval(timer)
})
</script>

<template>
  <section v-if="enabled" aria-label="生成补充指令">
    <details>
      <summary>补充指令 · {{ rows.length }} 条</summary>
      <form v-if="active" @submit.prevent="submit">
        <label>处理时机
          <select v-model="target" :disabled="busy">
            <option value="next_step">本轮下一步纠偏</option>
            <option value="next_run">留到下一轮新任务</option>
          </select>
        </label>
        <label>补充内容
          <textarea v-model="text" rows="3" maxlength="1200" :disabled="busy" />
        </label>
        <button type="submit" :disabled="busy || !text.trim()">提交指令</button>
      </form>
      <p v-if="error" role="status">{{ error }}</p>
      <ol>
        <li v-for="row in rows" :key="row.instruction_id">
          <p>{{ row.content }}</p>
          <small>{{ row.target === 'next_step' ? '本轮纠偏' : '下一轮' }} · {{ labels[row.status] }}</small>
          <small v-if="row.step_id"> · 步骤 {{ row.step_id }} · 合同 v{{ row.contract_version }}</small>
          <p v-if="row.reason">{{ reasons[row.reason] ?? row.reason }}</p>
          <button v-if="row.status === 'queued' || row.status === 'next_run_ready'" type="button"
            :disabled="busy" @click="cancel(row.instruction_id)">取消指令</button>
          <button v-if="row.status === 'next_run_ready' && !active" type="button"
            @click="emit('nextRun', row.content)">填入下一轮需求</button>
        </li>
      </ol>
    </details>
  </section>
</template>

<style scoped>
form, label { display: grid; gap: .35rem; }
form { margin-block: .5rem; }
p, small { overflow-wrap: anywhere; }
</style>
