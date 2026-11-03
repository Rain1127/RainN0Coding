<script setup lang="ts">
import { computed } from 'vue'
import type { GenerationEvent } from '@/types/generation'
const props = defineProps<{ events: GenerationEvent[] }>()
interface RuntimeEvidence {
  status?: string
  contract_id?: string
  contract_version?: number
  contract_hash?: string
  features?: { id: string; name: string; status: string; log?: string; screenshot?: string;
    steps?: { action: string; expected?: unknown; actual?: string }[] }[]
}
const evidence = computed<{ build_status?: string; runtime_result?: RuntimeEvidence } | null>(() => {
  for (const event of [...props.events].reverse()) {
    if (event.type === 'done' && event.result && typeof event.result === 'object') {
      return event.result as { build_status?: string; runtime_result?: RuntimeEvidence }
    }
    if (event.type === 'runtime_validation' && event.result) {
      return { runtime_result: event.result as RuntimeEvidence }
    }
    if (event.type === 'phase_complete' && event.phase === 'build' && event.output) {
      return { build_status: (event.output as { status?: string }).status }
    }
  }
  return null
})
const labels: Record<string, string> = {
  succeeded: '验证通过', failed: '验证失败', unverified: '未验证', not_required: '无需此项验证',
}
</script>
<template>
  <section v-if="evidence" aria-label="验证结果">
    <p v-if="evidence.build_status" role="status">构建：{{ labels[evidence.build_status] ?? '状态待确认' }}</p>
    <p v-if="evidence.runtime_result?.status">浏览器：{{ labels[evidence.runtime_result.status] ?? '状态待确认' }}</p>
    <details v-if="evidence.runtime_result?.contract_id">
      <summary>需求验收合同 v{{ evidence.runtime_result.contract_version }}</summary>
      <p>{{ evidence.runtime_result.contract_id }}</p>
      <ul>
        <li v-for="feature in evidence.runtime_result.features" :key="feature.id">
          {{ feature.name }}：{{ labels[feature.status] ?? '状态待确认' }}
          <details><summary>验证证据</summary>
            <p>{{ feature.log }}</p>
            <ol><li v-for="(step, index) in feature.steps" :key="index">
              {{ step.action }} · 预期：{{ step.expected }} · 实际：{{ step.actual }}
            </li></ol>
          </details>
        </li>
      </ul>
    </details>
  </section>
</template>
