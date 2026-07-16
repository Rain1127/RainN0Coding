<script setup lang="ts">
import { computed, nextTick, ref, useId } from 'vue'
import { DeleteOutlined, FolderOpenOutlined } from '@ant-design/icons-vue'
import type { AppVO, CodeGenType } from '@/types/app'
import type { EntityId } from '@/types/entity'

const props = withDefaults(defineProps<{
  project: AppVO
  deleting?: boolean
}>(), {
  deleting: false,
})

const emit = defineEmits<{
  delete: [appId: EntityId]
}>()

const confirmOpen = ref(false)
const confirmTitleId = useId()
const deleteTrigger = ref<HTMLButtonElement | null>(null)
const cancelButton = ref<HTMLButtonElement | null>(null)
const confirmButton = ref<HTMLButtonElement | null>(null)

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

const projectName = computed(() => props.project.appName?.trim() || '未命名项目')
const deploymentLabel = computed(() => props.project.deployKey?.trim() ? '已部署' : '未部署')
const updatedLabel = computed(() => {
  const source = props.project.editTime || props.project.updateTime || props.project.createTime
  const date = source ? new Date(source) : null
  if (!date || Number.isNaN(date.getTime())) return '更新时间未知'
  return `更新于 ${new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date)}`
})

async function openConfirmation() {
  confirmOpen.value = true
  await nextTick()
  cancelButton.value?.focus()
}

async function closeConfirmation() {
  confirmOpen.value = false
  await nextTick()
  deleteTrigger.value?.focus()
}

function confirmDelete() {
  emit('delete', props.project.id)
  void closeConfirmation()
}

function handleConfirmationKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    void closeConfirmation()
    return
  }
  if (event.key !== 'Tab') return
  if (event.shiftKey && event.target === cancelButton.value) {
    event.preventDefault()
    confirmButton.value?.focus()
  } else if (!event.shiftKey && event.target === confirmButton.value) {
    event.preventDefault()
    cancelButton.value?.focus()
  }
}
</script>

<template>
  <article class="project-card">
    <div class="project-card__topline">
      <span class="project-card__type">{{ typeLabels[project.codeGenType] }}</span>
      <span
        class="project-card__status"
        :class="{ 'project-card__status--deployed': Boolean(project.deployKey?.trim()) }"
      >
        {{ deploymentLabel }}
      </span>
    </div>
    <h2 class="project-card__title">{{ projectName }}</h2>
    <p class="project-card__prompt">
      {{ project.initPrompt?.trim() || '这个项目还没有需求摘要。' }}
    </p>
    <p class="project-card__updated">{{ updatedLabel }}</p>

    <div class="project-card__actions">
      <router-link :to="`/chat/${project.id}`" class="project-card__open">
        <FolderOpenOutlined aria-hidden="true" />
        打开项目
      </router-link>
      <button
        ref="deleteTrigger"
        type="button"
        class="project-card__delete"
        data-action="request-delete"
        :disabled="deleting"
        :aria-label="`删除项目：${projectName}`"
        @click="openConfirmation"
      >
        <DeleteOutlined aria-hidden="true" />
        删除
      </button>
    </div>

    <div
      v-if="confirmOpen"
      class="project-card__confirmation"
      role="alertdialog"
      aria-modal="true"
      :aria-labelledby="confirmTitleId"
      @keydown="handleConfirmationKeydown"
    >
      <p :id="confirmTitleId">删除“{{ projectName }}”？此操作无法撤销。</p>
      <div class="project-card__confirmation-actions">
        <button
          ref="cancelButton"
          type="button"
          data-action="cancel-delete"
          :disabled="deleting"
          @click="closeConfirmation"
        >
          取消
        </button>
        <button
          ref="confirmButton"
          type="button"
          class="project-card__confirm-delete"
          data-action="confirm-delete"
          :disabled="deleting"
          @click="confirmDelete"
        >
          {{ deleting ? '正在删除…' : '确认删除' }}
        </button>
      </div>
    </div>
  </article>
</template>

<style scoped>
.project-card {
  position: relative;
  display: flex;
  min-width: 0;
  min-height: 272px;
  flex-direction: column;
  padding: var(--space-5);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  box-shadow: var(--shadow-card);
}

.project-card__topline,
.project-card__actions,
.project-card__confirmation-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.project-card__type,
.project-card__status,
.project-card__updated {
  color: var(--color-text-muted);
  font-size: 0.8rem;
}

.project-card__type {
  font-family: var(--font-mono);
}

.project-card__status {
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-full);
  background: var(--color-surface-subtle);
  font-weight: 800;
}

.project-card__status--deployed {
  color: var(--color-success);
  background: var(--color-success-soft);
}

.project-card__title {
  margin: var(--space-4) 0 var(--space-2);
  overflow-wrap: anywhere;
  color: var(--color-text);
  font-size: 1.15rem;
  line-height: 1.3;
}

.project-card__prompt {
  display: -webkit-box;
  margin: 0;
  overflow: hidden;
  color: var(--color-text-muted);
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}

.project-card__updated {
  margin: auto 0 var(--space-4);
  padding-top: var(--space-5);
}

.project-card__open,
.project-card__delete,
.project-card__confirmation button {
  display: inline-flex;
  min-height: 44px;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  border-radius: var(--radius-sm);
  padding: 0 var(--space-3);
  font-weight: 800;
  text-decoration: none;
}

.project-card__open {
  color: #ffffff;
  background: var(--color-primary);
}

.project-card__open:hover {
  background: var(--color-primary-hover);
}

.project-card__delete,
.project-card__confirmation button {
  border: 1px solid var(--color-border);
  color: var(--color-text);
  background: var(--color-surface);
}

.project-card__delete:hover {
  border-color: var(--color-danger);
  color: var(--color-danger);
}

.project-card__confirmation {
  position: absolute;
  z-index: 2;
  inset: var(--space-4);
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: var(--space-5);
  border: 1px solid var(--color-danger);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  box-shadow: var(--shadow-card);
  overscroll-behavior: contain;
}

.project-card__confirmation p {
  margin: 0 0 var(--space-5);
  font-weight: 700;
}

.project-card__confirmation .project-card__confirm-delete {
  border-color: var(--color-danger);
  color: #ffffff;
  background: var(--color-danger);
}

@media (max-width: 420px) {
  .project-card__actions {
    align-items: stretch;
    flex-direction: column;
  }

  .project-card__open,
  .project-card__delete {
    width: 100%;
  }
}
</style>
