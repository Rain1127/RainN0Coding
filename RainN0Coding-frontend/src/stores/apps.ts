import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { AppVO } from '@/types/app'
import { listMyApps } from '@/api/app'

export const useAppsStore = defineStore('apps', () => {
  const appList = ref<AppVO[]>([])
  const total = ref(0)
  const loading = ref(false)
  const searchKeyword = ref('')

  const filteredApps = computed(() => {
    if (!searchKeyword.value) return appList.value
    const kw = searchKeyword.value.toLowerCase()
    return appList.value.filter(a => a.appName.toLowerCase().includes(kw))
  })

  const groupedApps = computed(() => {
    const now = Date.now()
    const today: AppVO[] = []
    const week: AppVO[] = []
    const older: AppVO[] = []

    for (const app of filteredApps.value) {
      const ts = app.editTime ? new Date(app.editTime).getTime() : new Date(app.createTime).getTime()
      const diff = now - ts
      if (diff < 24 * 60 * 60 * 1000) {
        today.push(app)
      } else if (diff < 7 * 24 * 60 * 60 * 1000) {
        week.push(app)
      } else {
        older.push(app)
      }
    }

    const groups: { label: string; items: AppVO[] }[] = []
    if (today.length) groups.push({ label: '今天', items: today })
    if (week.length) groups.push({ label: '7天内', items: week })
    if (older.length) groups.push({ label: '更早', items: older })
    return groups
  })

  async function fetchMyApps(pageNum = 1, pageSize = 100) {
    loading.value = true
    try {
      const res = await listMyApps({
        pageNum,
        pageSize,
        sortField: 'editTime',
        sortOrder: 'descend',
      })
      appList.value = res.records
      total.value = res.total
    } finally {
      loading.value = false
    }
  }

  function setSearchKeyword(kw: string) {
    searchKeyword.value = kw
  }

  function removeApp(appId: number) {
    appList.value = appList.value.filter(a => a.id !== appId)
  }

  function addApp(app: AppVO) {
    appList.value.unshift(app)
  }

  return {
    appList,
    total,
    loading,
    searchKeyword,
    filteredApps,
    groupedApps,
    fetchMyApps,
    setSearchKeyword,
    removeApp,
    addApp,
  }
})
