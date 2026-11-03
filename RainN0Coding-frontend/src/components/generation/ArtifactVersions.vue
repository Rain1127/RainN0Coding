<script setup lang="ts">
import { ref, watch } from 'vue'
import type { EntityId } from '@/types/entity'
import { listArtifactVersions, rollbackArtifactVersion, type ArtifactVersion } from '@/api/app'
const props = defineProps<{ appId: EntityId; disabled: boolean }>()
const emit = defineEmits<{ restored: [] }>()
const versions = ref<ArtifactVersion[]>([])
const error = ref('')
const pending = ref(false)
let sequence = 0
async function load() {
  const current = ++sequence
  error.value = ''
  try {
    const result = await listArtifactVersions(props.appId)
    if (current === sequence) versions.value = result
  } catch { if (current === sequence) error.value = '版本记录暂不可用' }
}
async function rollback(version: ArtifactVersion) {
  const currentApp = props.appId
  pending.value = true
  error.value = ''
  try {
    await rollbackArtifactVersion(currentApp, String(version.id))
    if (currentApp === props.appId) { emit('restored'); await load() }
  } catch { error.value = '回滚失败，请刷新版本记录后重试' }
  finally { pending.value = false }
}
watch(() => [props.appId, props.disabled], () => { versions.value = []; if (!props.disabled) void load() }, { immediate: true })
</script>
<template>
  <section aria-label="产物版本">
    <h3>产物版本</h3>
    <p v-if="error" role="alert">{{ error }}</p>
    <button type="button" :disabled="disabled || pending" @click="load">刷新版本</button>
    <ul>
      <li v-for="version in versions" :key="version.id">
        v{{ version.number }} · {{ version.description }}
        <button type="button" :disabled="disabled || pending" @click="rollback(version)">回滚到此版本</button>
      </li>
    </ul>
  </section>
</template>
