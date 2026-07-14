<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  AppstoreOutlined,
  CloseOutlined,
  DownOutlined,
  HomeOutlined,
  LogoutOutlined,
  MenuOutlined,
  PlusOutlined,
  SearchOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'
import BrandMark from '@/components/shared/BrandMark.vue'
import { useModalDrawer } from '@/composables/useModalDrawer'
import { useAppsStore } from '@/stores/apps'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const appsStore = useAppsStore()

const mobileNavOpen = ref(false)
const mobileTrigger = ref<HTMLButtonElement | null>(null)
const mobileDialog = ref<HTMLElement | null>(null)
const desktopSidebar = ref<HTMLElement | null>(null)
const mainColumn = ref<HTMLElement | null>(null)

const currentAppId = computed(() => {
  const appId = route.params.appId
  return appId ? Number(appId) : null
})

const {
  closeDrawer: closeMobileNavigation,
  handleDrawerKeydown: handleWindowKeydown,
  openDrawer: openMobileNavigation,
} = useModalDrawer({
  open: mobileNavOpen,
  trigger: mobileTrigger,
  dialog: mobileDialog,
  background: () => [desktopSidebar.value, mainColumn.value],
})

async function handleLogout() {
  await auth.logout()
  await router.push('/login')
}

onMounted(() => {
  window.addEventListener('keydown', handleWindowKeydown)
  void appsStore.fetchRecentApps().catch(() => undefined)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleWindowKeydown)
})

watch(() => route.fullPath, closeMobileNavigation)
</script>

<template>
  <div class="app-shell">
    <a class="skip-link" href="#main-content">跳到主要内容</a>

    <aside ref="desktopSidebar" class="desktop-sidebar" aria-label="工作台侧栏">
      <div class="sidebar-top">
        <router-link to="/" aria-label="返回生成首页">
          <BrandMark tone="dark" />
        </router-link>
        <router-link to="/" class="shell-primary-button shell-primary-button--sidebar">
          <PlusOutlined aria-hidden="true" />
          新建项目
        </router-link>
      </div>

      <div class="sidebar-search">
        <label for="desktop-project-search" class="sr-only">搜索最近项目</label>
        <a-input
          id="desktop-project-search"
          v-model:value="appsStore.searchKeyword"
          placeholder="搜索最近项目…"
          allow-clear
        >
          <template #prefix><SearchOutlined aria-hidden="true" /></template>
        </a-input>
      </div>

      <nav class="shell-nav" aria-label="主导航">
        <router-link to="/" class="shell-nav__link">
          <HomeOutlined aria-hidden="true" />
          <span>生成首页</span>
        </router-link>
        <router-link to="/projects" class="shell-nav__link">
          <AppstoreOutlined aria-hidden="true" />
          <span>我的项目</span>
        </router-link>
        <p class="shell-nav__label">最近项目</p>
        <router-link
          v-for="app in appsStore.filteredApps"
          :key="app.id"
          :to="`/chat/${app.id}`"
          class="shell-nav__link"
          :class="{ 'router-link-active': currentAppId === app.id }"
        >
          <span class="shell-user-name">{{ app.appName || '未命名项目' }}</span>
        </router-link>
        <p v-if="appsStore.recentError" class="shell-nav__label">最近项目暂不可用</p>
        <p v-else-if="appsStore.filteredApps.length === 0 && !appsStore.recentLoading" class="shell-nav__label">
          暂无最近项目
        </p>
      </nav>

      <div class="sidebar-footer">
        <a-dropdown placement="topLeft" :trigger="['click']">
          <button type="button" class="shell-user-trigger" aria-label="打开用户菜单">
            <a-avatar :size="32">{{ auth.userName?.charAt(0) || 'U' }}</a-avatar>
            <span class="shell-user-name">{{ auth.userName || '当前用户' }}</span>
            <DownOutlined aria-hidden="true" />
          </button>
          <template #overlay>
            <a-menu>
              <a-menu-item v-if="auth.isAdmin" @click="router.push('/admin/apps')">
                <SettingOutlined aria-hidden="true" />
                管理后台
              </a-menu-item>
              <a-menu-item @click="handleLogout">
                <LogoutOutlined aria-hidden="true" />
                退出登录
              </a-menu-item>
            </a-menu>
          </template>
        </a-dropdown>
      </div>
    </aside>

    <div ref="mainColumn" class="shell-main-column">
      <header class="mobile-header">
        <button
          ref="mobileTrigger"
          type="button"
          class="icon-button"
          aria-label="打开主导航"
          aria-controls="chat-mobile-navigation"
          :aria-expanded="mobileNavOpen"
          @click="openMobileNavigation"
        >
          <MenuOutlined aria-hidden="true" />
        </button>
        <router-link to="/" class="mobile-brand-link" aria-label="返回生成首页">
          <BrandMark compact />
        </router-link>
        <a-avatar :size="36" :aria-label="`当前用户：${auth.userName || '用户'}`">
          {{ auth.userName?.charAt(0) || 'U' }}
        </a-avatar>
      </header>

      <main id="main-content" class="page-content" tabindex="-1">
        <slot />
      </main>
    </div>

    <div v-if="mobileNavOpen" class="mobile-drawer-layer">
      <button
        type="button"
        class="mobile-drawer__backdrop"
        aria-label="关闭主导航"
        @click="closeMobileNavigation"
      />
      <aside
        ref="mobileDialog"
        id="chat-mobile-navigation"
        class="mobile-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="移动端主导航"
      >
        <div class="mobile-drawer__header">
          <BrandMark tone="dark" />
          <button type="button" class="icon-button" aria-label="关闭主导航" @click="closeMobileNavigation">
            <CloseOutlined aria-hidden="true" />
          </button>
        </div>
        <nav class="shell-nav" aria-label="主导航">
          <router-link to="/" class="shell-nav__link">
            <HomeOutlined aria-hidden="true" />
            <span>生成首页</span>
          </router-link>
          <router-link to="/projects" class="shell-nav__link">
            <AppstoreOutlined aria-hidden="true" />
            <span>我的项目</span>
          </router-link>
          <p class="shell-nav__label">最近项目</p>
          <router-link
            v-for="app in appsStore.filteredApps"
            :key="app.id"
            :to="`/chat/${app.id}`"
            class="shell-nav__link"
          >
            <span class="shell-user-name">{{ app.appName || '未命名项目' }}</span>
          </router-link>
        </nav>
        <div class="sidebar-footer">
          <button type="button" class="shell-user-trigger" @click="handleLogout">
            <LogoutOutlined aria-hidden="true" />
            <span>退出登录</span>
          </button>
        </div>
      </aside>
    </div>
  </div>
</template>
