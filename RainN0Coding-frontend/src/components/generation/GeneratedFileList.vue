<script setup lang="ts">
import type { GeneratedFile, GenerationStatus } from '@/types/generation'

defineProps<{
  files: GeneratedFile[]
  status: GenerationStatus
}>()

function languageLabel(language: string) {
  if (!language.trim()) return '未知语言'
  const labels: Record<string, string> = {
    vue: 'Vue',
    typescript: 'TypeScript',
    javascript: 'JavaScript',
    html: 'HTML',
    css: 'CSS',
    python: 'Python',
    java: 'Java',
  }
  return labels[language.trim().toLowerCase()] ?? language.trim()
}

function sizeLabel(size?: number | string) {
  if (size === undefined || size === '') return '大小未知'
  if (typeof size === 'string') return size
  if (size < 1024) return `${size} B`
  const kilobytes = size / 1024
  return `${Number.isInteger(kilobytes) ? kilobytes : kilobytes.toFixed(1)} KB`
}

function fileStatus(status: GenerationStatus) {
  if (status === 'success') return '已生成'
  if (status === 'failed') return '已保留'
  if (status === 'cancelled') return '取消前已生成'
  return '生成中'
}
</script>

<template>
  <section class="generated-files" aria-labelledby="generated-files-title">
    <div class="generated-files__heading">
      <h2 id="generated-files-title">生成文件</h2>
      <span>{{ files.length }} 个</span>
    </div>

    <ul v-if="files.length" class="generated-files__list" aria-label="生成文件">
      <li v-for="file in files" :key="file.path" class="generated-files__item">
        <code :title="file.path">{{ file.path }}</code>
        <div class="generated-files__metadata">
          <span>{{ languageLabel(file.language) }}</span>
          <span>{{ sizeLabel(file.size) }}</span>
          <span>{{ fileStatus(status) }}</span>
        </div>
      </li>
    </ul>
    <p v-else class="generated-files__empty" data-empty-files>
      文件将在生成后显示。这里仅展示路径和元数据，不展示源码内容。
    </p>
  </section>
</template>

<style scoped>
.generated-files {
  padding: var(--space-5);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
}

.generated-files__heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.generated-files h2 { margin: 0; font-size: 1rem; }
.generated-files__heading span { color: var(--color-text-muted); font-size: 0.78rem; }

.generated-files__list {
  display: grid;
  gap: var(--space-2);
  margin: var(--space-4) 0 0;
  padding: 0;
  list-style: none;
}

.generated-files__item {
  min-width: 0;
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface-subtle);
}

.generated-files code {
  display: block;
  overflow: hidden;
  font-family: var(--font-mono);
  font-size: 0.78rem;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.generated-files__metadata {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-2);
  color: var(--color-text-muted);
  font-size: 0.7rem;
}

.generated-files__metadata span + span::before { content: '·'; margin-right: var(--space-2); }
.generated-files__empty { margin: var(--space-4) 0 0; color: var(--color-text-muted); font-size: 0.82rem; }
</style>
