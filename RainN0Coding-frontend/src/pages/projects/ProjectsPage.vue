<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PlusOutlined } from '@ant-design/icons-vue'
import EmptyState from '@/components/shared/EmptyState.vue'
import ErrorState from '@/components/shared/ErrorState.vue'
import PageHeader from '@/components/shared/PageHeader.vue'
import ProjectCard from '@/components/projects/ProjectCard.vue'
import ProjectListToolbar from '@/components/projects/ProjectListToolbar.vue'
import ChatLayout from '@/layouts/ChatLayout.vue'
import {
  SUPPORTED_CODE_GEN_TYPES,
  type AppsQueryState,
  type CodeGenTypeFilter,
  type DeploymentFilter,
  useAppsStore,
} from '@/stores/apps'
import type { EntityId } from '@/types/entity'

const apps = useAppsStore()
const route = useRoute()
const router = useRouter()
const deletingId = ref<EntityId | null>(null)
const actionError = ref('')
const totalPages = computed(() => Math.max(1, Math.ceil(apps.total / apps.pageSize)))
const hasServerFilters = computed(() => Boolean(apps.keyword.trim()) || apps.codeGenType !== 'all')

async function loadProjects(options?: { pageNum?: number; keyword?: string; codeGenType?: CodeGenTypeFilter }) {
  try {
    await apps.fetchMyApps(options)
  } catch {
    // The store keeps the last successful list and exposes a page-local retry state.
  }
}

function queryValue(value: unknown) {
  return typeof value === 'string' ? value : ''
}

function deploymentFilter(value: unknown): DeploymentFilter {
  return value === 'deployed' || value === 'undeployed' ? value : 'all'
}

function codeGenTypeFilter(value: unknown): CodeGenTypeFilter {
  const candidate = queryValue(value)
  return SUPPORTED_CODE_GEN_TYPES.includes(candidate as Exclude<CodeGenTypeFilter, 'all'>)
    ? candidate as Exclude<CodeGenTypeFilter, 'all'>
    : 'all'
}

function pageFromQuery(value: unknown) {
  const page = Number(queryValue(value))
  return Number.isInteger(page) && page > 0 ? page : 1
}

function routeState(): AppsQueryState {
  return {
    pageNum: pageFromQuery(route.query.page),
    keyword: queryValue(route.query.keyword).trim(),
    codeGenType: codeGenTypeFilter(route.query.type ?? route.query.codeGenType),
    status: deploymentFilter(route.query.status),
  }
}

function queryFromState(state: AppsQueryState) {
  return {
    ...(state.pageNum > 1 ? { page: String(state.pageNum) } : {}),
    ...(state.keyword.trim() ? { keyword: state.keyword.trim() } : {}),
    ...(state.codeGenType !== 'all' ? { type: state.codeGenType } : {}),
    ...(state.status !== 'all' ? { status: state.status } : {}),
  }
}

function sameRecognizedQuery(query: ReturnType<typeof queryFromState>) {
  return (
    queryValue(route.query.page) === (query.page ?? '')
    && queryValue(route.query.keyword) === (query.keyword ?? '')
    && queryValue(route.query.type ?? route.query.codeGenType) === (query.type ?? '')
    && queryValue(route.query.status) === (query.status ?? '')
  )
}

function requestForState(state: AppsQueryState) {
  return {
    pageNum: state.pageNum,
    keyword: state.keyword,
    ...(state.codeGenType !== 'all' ? { codeGenType: state.codeGenType } : {}),
  }
}

function currentState(): AppsQueryState {
  return {
    pageNum: apps.pageNum,
    keyword: apps.keyword,
    codeGenType: apps.codeGenType,
    status: apps.status,
  }
}

function retryProjects() {
  void loadProjects(requestForState(currentState()))
}

async function syncQuery(next: Partial<AppsQueryState>) {
  const state: AppsQueryState = {
    pageNum: apps.pageNum,
    keyword: apps.keyword,
    codeGenType: apps.codeGenType,
    status: apps.status,
    ...next,
  }
  apps.applyQueryState(state)
  const query = queryFromState(state)
  if (sameRecognizedQuery(query)) {
    await loadProjects(requestForState(state))
    return
  }
  try {
    await router.replace({ query })
  } catch {
    actionError.value = '筛选条件同步失败，请重试。'
  }
}

function search(keyword: string) {
  void syncQuery({ pageNum: 1, keyword })
}

function filterStatus(status: DeploymentFilter) {
  void syncQuery({ pageNum: 1, status })
}

function filterCodeGenType(codeGenType: CodeGenTypeFilter) {
  void syncQuery({ pageNum: 1, codeGenType })
}

function clearStatus() {
  void syncQuery({ pageNum: 1, status: 'all' })
}

function changePage(page: number) {
  if (page < 1 || page > totalPages.value || page === apps.pageNum || apps.loading) return
  void syncQuery({ pageNum: page })
}

async function deleteProject(appId: EntityId) {
  if (deletingId.value !== null) return
  deletingId.value = appId
  actionError.value = ''
  try {
    await apps.deleteProject(appId)
    const nextPage = apps.appList.length === 0 && apps.pageNum > 1
      ? apps.pageNum - 1
      : apps.pageNum
    await syncQuery({ pageNum: nextPage })
    void apps.fetchRecentApps().catch(() => undefined)
  } catch {
    actionError.value = '项目删除失败，请稍后重试。'
  } finally {
    deletingId.value = null
  }
}

watch(
  () => [route.query.page, route.query.keyword, route.query.type, route.query.codeGenType, route.query.status],
  () => {
    const state = routeState()
    apps.applyQueryState(state)
    void loadProjects(requestForState(state))
  },
  { immediate: true },
)
</script>

<template>
  <ChatLayout>
    <div class="projects-page content-container">
      <PageHeader
        eyebrow="项目管理"
        title="我的项目"
        description="按名称和代码类型查找全部项目，并在当前页快速查看部署状态。"
      >
        <template #actions>
          <router-link to="/" class="projects-page__create">
            <PlusOutlined aria-hidden="true" />
            创建新项目
          </router-link>
        </template>
      </PageHeader>

      <ProjectListToolbar
        :keyword="apps.keyword"
        :code-gen-type="apps.codeGenType"
        :status="apps.status"
        :loading="apps.loading"
        @search="search"
        @type-change="filterCodeGenType"
        @status-change="filterStatus"
      />

      <p v-if="actionError" class="projects-page__action-error" role="alert">{{ actionError }}</p>

      <div
        v-if="apps.error && apps.appList.length > 0"
        class="projects-page__cached-error"
        role="alert"
      >
        <span>{{ apps.error }} 当前显示上次成功加载的结果。</span>
        <button type="button" data-action="retry-projects" @click="retryProjects">重新加载</button>
      </div>

      <div v-if="apps.loading" class="project-grid project-grid--skeleton" aria-busy="true">
        <div v-for="index in 6" :key="index" class="project-card-skeleton" />
      </div>

      <ErrorState
        v-else-if="apps.error && apps.appList.length === 0"
        title="项目加载失败"
        :description="apps.error"
        retryable
        @retry="retryProjects"
      />

      <EmptyState
        v-else-if="apps.total === 0 && hasServerFilters"
        title="没有找到匹配项目"
        description="没有符合当前名称或代码类型筛选的项目，请调整筛选条件。"
      >
        <button type="button" class="projects-page__secondary" @click="syncQuery({ pageNum: 1, keyword: '', codeGenType: 'all' })">清除服务端筛选</button>
      </EmptyState>

      <EmptyState
        v-else-if="apps.total === 0"
        title="还没有项目"
        description="从一个清晰的需求开始，创建你的第一个 AI 生成项目。"
      >
        <router-link to="/" class="projects-page__create">创建第一个项目</router-link>
      </EmptyState>

      <EmptyState
        v-else-if="apps.visibleApps.length === 0"
        :title="apps.status === 'deployed' ? '当前页没有已部署项目' : '当前页没有未部署项目'"
        description="部署状态筛选只作用于当前服务端分页；你可以切换状态或继续翻页。"
      >
        <button
          type="button"
          class="projects-page__secondary"
          data-action="clear-status"
          @click="clearStatus"
        >
          查看当前页全部状态
        </button>
      </EmptyState>

      <div v-else class="project-grid">
        <ProjectCard
          v-for="project in apps.visibleApps"
          :key="project.id"
          :project="project"
          :deleting="deletingId === project.id"
          @delete="deleteProject"
        />
      </div>

      <nav
        v-if="!apps.loading && (!apps.error || apps.appList.length > 0) && apps.total > apps.pageSize"
        class="project-pagination"
        aria-label="项目分页"
      >
        <button
          type="button"
          data-action="previous-page"
          :disabled="apps.pageNum <= 1"
          @click="changePage(apps.pageNum - 1)"
        >
          上一页
        </button>
        <span aria-live="polite">第 {{ apps.pageNum }} / {{ totalPages }} 页，共 {{ apps.total }} 个项目</span>
        <button
          type="button"
          data-action="next-page"
          :disabled="apps.pageNum >= totalPages"
          @click="changePage(apps.pageNum + 1)"
        >
          下一页
        </button>
      </nav>
    </div>
  </ChatLayout>
</template>

<style scoped>
.projects-page {
  width: 100%;
  max-width: var(--content-max-width);
  margin: 0 auto;
  padding: var(--space-8) var(--space-6) var(--space-12);
}

.projects-page__create,
.projects-page__secondary,
.project-pagination button {
  display: inline-flex;
  min-height: 44px;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  border-radius: var(--radius-sm);
  padding: 0 var(--space-4);
  font-weight: 800;
  text-decoration: none;
}

.projects-page__create {
  border: 1px solid var(--color-primary);
  color: #ffffff;
  background: var(--color-primary);
}

.projects-page__create:hover {
  background: var(--color-primary-hover);
}

.projects-page__secondary,
.project-pagination button {
  border: 1px solid var(--color-border);
  color: var(--color-text);
  background: var(--color-surface);
}

.projects-page__secondary:hover,
.project-pagination button:not(:disabled):hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.projects-page__action-error {
  margin: 0 0 var(--space-4);
  padding: var(--space-3) var(--space-4);
  border: 1px solid #fecaca;
  border-radius: var(--radius-sm);
  color: var(--color-danger);
  background: var(--color-danger-soft);
}

.projects-page__cached-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  margin: 0 0 var(--space-4);
  padding: var(--space-3) var(--space-4);
  border: 1px solid #fecaca;
  border-radius: var(--radius-sm);
  color: var(--color-danger);
  background: var(--color-danger-soft);
}

.projects-page__cached-error button {
  min-height: 44px;
  flex: 0 0 auto;
  border: 1px solid currentColor;
  border-radius: var(--radius-sm);
  padding: 0 var(--space-4);
  color: inherit;
  font-weight: 800;
  background: transparent;
}

.project-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-4);
}

.project-card-skeleton {
  min-height: 272px;
  border-radius: var(--radius-lg);
  background: var(--color-surface-subtle);
}

.project-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  margin-top: var(--space-8);
  color: var(--color-text-muted);
}

@media (max-width: 1023px) {
  .project-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 767px) {
  .projects-page {
    padding: 0 0 var(--space-8);
  }

  .project-grid {
    grid-template-columns: 1fr;
  }

  .project-pagination {
    align-items: stretch;
    flex-direction: column;
    text-align: center;
  }

  .projects-page__cached-error {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
