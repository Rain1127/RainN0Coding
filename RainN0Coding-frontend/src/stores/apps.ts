import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { deleteApp, listMyApps } from '@/api/app'
import type { AppVO, CodeGenType } from '@/types/app'
import { normalizePageResult } from '@/utils/pageResult'
import type { EntityId } from '@/types/entity'

export type DeploymentFilter = 'all' | 'deployed' | 'undeployed'
export type CodeGenTypeFilter = 'all' | CodeGenType

export const SUPPORTED_CODE_GEN_TYPES: CodeGenType[] = [
  'html',
  'multi_file',
  'vue_project',
  'python',
  'java',
  'go',
  'rust',
  'nodejs',
  'generic',
]

export interface AppsQueryState {
  pageNum: number
  keyword: string
  codeGenType: CodeGenTypeFilter
  status: DeploymentFilter
}

interface FetchAppsOptions extends Partial<AppsQueryState> {
  pageSize?: number
}

const DEFAULT_PAGE_SIZE = 12
const RECENT_PAGE_SIZE = 5

function matchesDeploymentFilter(app: AppVO, status: DeploymentFilter) {
  if (status === 'all') return true
  const deployed = Boolean(app.deployKey?.trim())
  return status === 'deployed' ? deployed : !deployed
}

export const useAppsStore = defineStore('apps', () => {
  const appList = ref<AppVO[]>([])
  const recentApps = ref<AppVO[]>([])
  const total = ref(0)
  const pageNum = ref(1)
  const pageSize = ref(DEFAULT_PAGE_SIZE)
  const keyword = ref('')
  const codeGenType = ref<CodeGenTypeFilter>('all')
  const status = ref<DeploymentFilter>('all')
  const loading = ref(false)
  const recentLoading = ref(false)
  const error = ref('')
  const recentError = ref('')
  const searchKeyword = ref('')
  let listRequestSequence = 0
  let recentRequestSequence = 0

  const visibleApps = computed(() => (
    appList.value.filter(app => matchesDeploymentFilter(app, status.value))
  ))

  const filteredApps = computed(() => {
    const query = searchKeyword.value.trim().toLowerCase()
    if (!query) return recentApps.value
    return recentApps.value.filter(app => (app.appName || '').toLowerCase().includes(query))
  })

  const groupedApps = computed(() => {
    const now = Date.now()
    const today: AppVO[] = []
    const week: AppVO[] = []
    const older: AppVO[] = []

    for (const app of filteredApps.value) {
      const source = app.editTime || app.updateTime || app.createTime
      const timestamp = source ? new Date(source).getTime() : 0
      const age = now - timestamp
      if (age < 24 * 60 * 60 * 1000) today.push(app)
      else if (age < 7 * 24 * 60 * 60 * 1000) week.push(app)
      else older.push(app)
    }

    return [
      { label: '今天', items: today },
      { label: '7 天内', items: week },
      { label: '更早', items: older },
    ].filter(group => group.items.length > 0)
  })

  function applyQueryState(next: Partial<AppsQueryState>) {
    if (next.pageNum !== undefined) pageNum.value = next.pageNum
    if (next.keyword !== undefined) keyword.value = next.keyword
    if (next.codeGenType !== undefined) codeGenType.value = next.codeGenType
    if (next.status !== undefined) status.value = next.status
  }

  async function fetchMyApps(options: FetchAppsOptions = {}) {
    const requestSequence = ++listRequestSequence
    applyQueryState(options)
    if (options.pageSize !== undefined) pageSize.value = options.pageSize

    const requestPage = pageNum.value
    const requestSize = pageSize.value
    const requestKeyword = keyword.value.trim()
    const requestCodeGenType = codeGenType.value
    loading.value = true
    error.value = ''

    try {
      const result = await listMyApps({
        pageNum: requestPage,
        pageSize: requestSize,
        sortField: 'editTime',
        sortOrder: 'descend',
        ...(requestKeyword ? { appName: requestKeyword } : {}),
        ...(requestCodeGenType !== 'all' ? { codeGenType: requestCodeGenType } : {}),
      })
      if (requestSequence !== listRequestSequence) return
      const page = normalizePageResult(result, requestPage, requestSize)
      appList.value = page.records
      total.value = page.total
      pageNum.value = page.current
      pageSize.value = page.size
    } catch (cause) {
      if (requestSequence === listRequestSequence) {
        error.value = '项目加载失败，请稍后重试。'
      }
      throw cause
    } finally {
      if (requestSequence === listRequestSequence) {
        loading.value = false
      }
    }
  }

  async function fetchRecentApps() {
    const requestSequence = ++recentRequestSequence
    recentLoading.value = true
    recentError.value = ''
    try {
      const result = await listMyApps({
        pageNum: 1,
        pageSize: RECENT_PAGE_SIZE,
        sortField: 'editTime',
        sortOrder: 'descend',
      })
      if (requestSequence !== recentRequestSequence) return
      recentApps.value = result.records
    } catch (cause) {
      if (requestSequence === recentRequestSequence) {
        recentError.value = '最近项目暂时无法加载。'
      }
      throw cause
    } finally {
      if (requestSequence === recentRequestSequence) {
        recentLoading.value = false
      }
    }
  }

  async function deleteProject(appId: EntityId) {
    await deleteApp({ id: appId })
    appList.value = appList.value.filter(app => app.id !== appId)
    recentApps.value = recentApps.value.filter(app => app.id !== appId)
    total.value = Math.max(0, total.value - 1)
  }

  function setSearchKeyword(value: string) {
    searchKeyword.value = value
  }

  function removeApp(appId: EntityId) {
    appList.value = appList.value.filter(app => app.id !== appId)
    recentApps.value = recentApps.value.filter(app => app.id !== appId)
  }

  function addApp(app: AppVO) {
    recentApps.value = [app, ...recentApps.value.filter(item => item.id !== app.id)].slice(0, RECENT_PAGE_SIZE)
  }

  return {
    appList,
    recentApps,
    total,
    pageNum,
    pageSize,
    keyword,
    codeGenType,
    status,
    loading,
    recentLoading,
    error,
    recentError,
    searchKeyword,
    visibleApps,
    filteredApps,
    groupedApps,
    applyQueryState,
    fetchMyApps,
    fetchRecentApps,
    deleteProject,
    setSearchKeyword,
    removeApp,
    addApp,
  }
})
