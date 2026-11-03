<script setup lang="ts">
import { computed } from 'vue'
import type { GenerationEvent } from '@/types/generation'
const props = defineProps<{ events: GenerationEvent[] }>()
const evidence = computed(() => {
  for (const event of [...props.events].reverse()) {
    if (event.type === 'done' && event.result && typeof event.result === 'object') {
      return event.result as { build_status?: string; runtime_result?: { status?: string } }
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
  <section v-if="evidence?.build_status" aria-label="验证结果">
    <p role="status">构建：{{ labels[evidence.build_status] ?? '状态待确认' }}</p>
    <p v-if="evidence.runtime_result?.status">浏览器：{{ labels[evidence.runtime_result.status] ?? '状态待确认' }}</p>
  </section>
</template>
