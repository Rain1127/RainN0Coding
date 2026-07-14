<script setup lang="ts">
import { ref, watch } from 'vue'
import { SearchOutlined } from '@ant-design/icons-vue'
import {
  SUPPORTED_CODE_GEN_TYPES,
  type CodeGenTypeFilter,
  type DeploymentFilter,
} from '@/stores/apps'
import type { CodeGenType } from '@/types/app'

const props = defineProps<{
  keyword: string
  status: DeploymentFilter
  codeGenType: CodeGenTypeFilter
  loading?: boolean
}>()

const emit = defineEmits<{
  search: [keyword: string]
  'status-change': [status: DeploymentFilter]
  'type-change': [codeGenType: CodeGenTypeFilter]
}>()

const draftKeyword = ref(props.keyword)

watch(() => props.keyword, value => {
  draftKeyword.value = value
})

function submitSearch() {
  emit('search', draftKeyword.value.trim())
}

function handleStatusChange(event: Event) {
  emit('status-change', (event.target as HTMLSelectElement).value as DeploymentFilter)
}

function handleTypeChange(event: Event) {
  emit('type-change', (event.target as HTMLSelectElement).value as CodeGenTypeFilter)
}

const typeLabels: Record<CodeGenType, string> = {
  html: 'HTML 页面',
  multi_file: '多文件项目',
  vue_project: 'Vue 项目',
  python: 'Python 项目',
  java: 'Java 项目',
  go: 'Go 项目',
  rust: 'Rust 项目',
  nodejs: 'Node.js 项目',
  generic: '通用项目',
}
</script>

<template>
  <div class="project-toolbar">
    <form class="project-toolbar__search" role="search" @submit.prevent="submitSearch">
      <label for="project-search">搜索项目名称</label>
      <div class="project-toolbar__search-row">
        <input
          id="project-search"
          v-model="draftKeyword"
          name="project-search"
          type="search"
          autocomplete="off"
          placeholder="例如：数据看板…"
          :disabled="loading"
        />
        <button type="submit" :disabled="loading">
          <SearchOutlined aria-hidden="true" />
          搜索
        </button>
      </div>
    </form>
    <div class="project-toolbar__filter">
      <label for="project-code-type">代码类型</label>
      <select
        id="project-code-type"
        :value="codeGenType"
        :disabled="loading"
        @change="handleTypeChange"
      >
        <option value="all">全部类型</option>
        <option v-for="type in SUPPORTED_CODE_GEN_TYPES" :key="type" :value="type">
          {{ typeLabels[type] }}
        </option>
      </select>
    </div>
    <div class="project-toolbar__filter">
      <label for="project-deployment-status">部署状态（当前页）</label>
      <select
        id="project-deployment-status"
        :value="status"
        :disabled="loading"
        @change="handleStatusChange"
      >
        <option value="all">全部状态</option>
        <option value="deployed">已部署</option>
        <option value="undeployed">未部署</option>
      </select>
    </div>
  </div>
</template>

<style scoped>
.project-toolbar {
  display: grid;
  grid-template-columns: minmax(280px, 1fr) minmax(180px, 220px) minmax(180px, 220px);
  gap: var(--space-4);
  align-items: end;
  margin-bottom: var(--space-6);
  padding: var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
}

.project-toolbar label {
  display: block;
  margin-bottom: var(--space-2);
  color: var(--color-text);
  font-size: 0.85rem;
  font-weight: 800;
}

.project-toolbar__search-row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: var(--space-2);
}

.project-toolbar input,
.project-toolbar select,
.project-toolbar button {
  min-height: 44px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: 0 var(--space-3);
  color: var(--color-text);
  background: var(--color-surface);
}

.project-toolbar select {
  width: 100%;
}

.project-toolbar button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  border-color: var(--color-primary);
  color: #ffffff;
  background: var(--color-primary);
  font-weight: 800;
}

.project-toolbar button:not(:disabled):hover {
  background: var(--color-primary-hover);
}

@media (max-width: 767px) {
  .project-toolbar {
    grid-template-columns: 1fr;
  }
}

@media (min-width: 768px) and (max-width: 1100px) {
  .project-toolbar {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .project-toolbar__search {
    grid-column: 1 / -1;
  }
}

@media (max-width: 420px) {
  .project-toolbar__search-row {
    grid-template-columns: 1fr;
  }
}
</style>
