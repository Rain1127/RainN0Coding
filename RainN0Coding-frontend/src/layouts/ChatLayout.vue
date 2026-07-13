<template>
  <div class="flex h-full">
    <!-- Sidebar -->
    <div class="w-[260px] bg-gpt-sidebar flex flex-col shrink-0">
      <div class="p-3">
        <div class="flex items-center gap-2 px-2 py-3">
          <div class="w-8 h-8 bg-gpt-accent rounded-lg flex items-center justify-center">
            <span class="text-white font-bold text-sm">AI</span>
          </div>
          <div>
            <div class="text-gpt-text-sidebar text-sm font-medium">AI 代码生成</div>
            <div class="text-gpt-text-muted text-xs">Powered by AI</div>
          </div>
        </div>
        <button class="w-full mt-2 flex items-center gap-2 px-3 py-2.5 rounded-lg border border-white/15 text-gpt-text-sidebar text-sm hover:bg-gpt-sidebar-hover transition-colors" @click="handleNewChat">
          <PlusOutlined class="text-gpt-accent" />
          <span>新建对话</span>
        </button>
      </div>
      <div class="px-3 pb-3">
        <a-input v-model:value="appsStore.searchKeyword" placeholder="搜索对话" size="small" class="search-input" @update:model-value="appsStore.setSearchKeyword($event)">
          <template #prefix><SearchOutlined class="text-gpt-text-muted" /></template>
          <template #suffix><span class="text-gpt-text-muted text-xs">Ctrl K</span></template>
        </a-input>
      </div>
      <div class="flex-1 overflow-y-auto px-2">
        <div v-for="group in appsStore.groupedApps" :key="group.label" class="mb-4">
          <div class="text-xs text-gpt-text-muted px-2 py-1.5 font-medium">{{ group.label }}</div>
          <div v-for="app in group.items" :key="app.id"
            class="flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm cursor-pointer transition-colors hover:bg-gpt-sidebar-hover"
            :class="currentAppId === app.id ? 'bg-gpt-sidebar-active text-gpt-text-sidebar' : 'text-gpt-text-sidebar'"
            @click="$router.push(`/chat/${app.id}`)">
            <span class="truncate flex-1">{{ app.appName || '新对话' }}</span>
          </div>
        </div>
        <div v-if="appsStore.filteredApps.length === 0 && !appsStore.loading" class="text-sm text-gpt-text-muted text-center py-8">
          暂无对话记录
        </div>
      </div>
      <div class="p-3 border-t border-white/10">
        <div class="flex items-center gap-2 px-2 py-2">
          <a-avatar :size="28" class="shrink-0">{{ auth.userName?.charAt(0) }}</a-avatar>
          <span class="text-sm text-gpt-text-sidebar truncate flex-1">{{ auth.userName }}</span>
          <a-dropdown>
            <MoreOutlined class="text-gpt-text-muted cursor-pointer" />
            <template #overlay>
              <a-menu>
                <a-menu-item v-if="auth.isAdmin" @click="$router.push('/admin/apps')">
                  <SettingOutlined /> 管理后台
                </a-menu-item>
                <a-menu-item @click="handleLogout">
                  <LogoutOutlined /> 退出登录
                </a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </div>
      </div>
    </div>
    <!-- Main -->
    <div class="flex-1 flex flex-col min-w-0">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PlusOutlined, SearchOutlined, MoreOutlined, SettingOutlined, LogoutOutlined } from '@ant-design/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useAppsStore } from '@/stores/apps'
import { createApp } from '@/api/app'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const appsStore = useAppsStore()

const currentAppId = computed(() => {
  const id = route.params.appId
  return id ? Number(id) : null
})

onMounted(() => {
  appsStore.fetchMyApps()
})

async function handleNewChat() {
  try {
    const appId = await createApp({ initPrompt: '' })
    appsStore.fetchMyApps()
    router.push(`/chat/${appId}`)
  } catch { /* error handled by interceptor */ }
}

async function handleLogout() {
  await auth.logout()
  router.push('/login')
}
</script>

<style scoped>
.search-input :deep(.ant-input) {
  background: #2a2a2a;
  border-color: transparent;
  color: #ececec;
}
.search-input :deep(.ant-input)::placeholder {
  color: #8e8ea0;
}
</style>
