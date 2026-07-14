<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ApartmentOutlined,
  AppstoreOutlined,
  CloseOutlined,
  DownOutlined,
  HomeOutlined,
  LogoutOutlined,
  MenuOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import BrandMark from '@/components/shared/BrandMark.vue'
import { useModalDrawer } from '@/composables/useModalDrawer'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const mobileNavOpen = ref(false)
const mobileTrigger = ref<HTMLButtonElement | null>(null)
const mobileDialog = ref<HTMLElement | null>(null)
const desktopSidebar = ref<HTMLElement | null>(null)
const mainColumn = ref<HTMLElement | null>(null)

const navItems = [
  { path: '/admin/apps', label: '应用管理', icon: AppstoreOutlined },
  { path: '/admin/users', label: '用户管理', icon: UserOutlined },
  { path: '/admin/intent-tree', label: '意图树配置', icon: ApartmentOutlined },
]

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

onMounted(() => window.addEventListener('keydown', handleWindowKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', handleWindowKeydown))
watch(() => route.fullPath, closeMobileNavigation)
</script>

<template>
  <div class="app-shell">
    <a class="skip-link" href="#main-content">跳到主要内容</a>

    <aside ref="desktopSidebar" class="desktop-sidebar desktop-sidebar--admin" aria-label="管理后台侧栏">
      <div class="sidebar-top">
        <router-link to="/admin/apps" aria-label="返回管理后台首页">
          <BrandMark tone="dark" />
        </router-link>
      </div>
      <nav class="shell-nav" aria-label="管理导航">
        <p class="shell-nav__label">管理后台</p>
        <router-link
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="shell-nav__link"
        >
          <component :is="item.icon" aria-hidden="true" />
          <span>{{ item.label }}</span>
        </router-link>
      </nav>
      <div class="sidebar-footer">
        <a-dropdown placement="topLeft" :trigger="['click']">
          <button type="button" class="shell-user-trigger" aria-label="打开管理员菜单">
            <a-avatar :size="32">{{ auth.userName?.charAt(0) || 'A' }}</a-avatar>
            <span class="shell-user-name">{{ auth.userName || '管理员' }}</span>
            <DownOutlined aria-hidden="true" />
          </button>
          <template #overlay>
            <a-menu>
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
      <header class="shell-toolbar">
        <button
          ref="mobileTrigger"
          type="button"
          class="icon-button mobile-only"
          aria-label="打开管理导航"
          aria-controls="admin-mobile-navigation"
          :aria-expanded="mobileNavOpen"
          @click="openMobileNavigation"
        >
          <MenuOutlined aria-hidden="true" />
        </button>
        <router-link to="/" class="shell-toolbar__link">
          <HomeOutlined aria-hidden="true" />
          返回工作台
        </router-link>
        <a-avatar :size="36" :aria-label="`当前管理员：${auth.userName || '管理员'}`">
          {{ auth.userName?.charAt(0) || 'A' }}
        </a-avatar>
      </header>
      <main id="main-content" class="page-content" tabindex="-1">
        <div class="content-container admin-content">
          <slot />
        </div>
      </main>
    </div>

    <div v-if="mobileNavOpen" class="mobile-drawer-layer">
      <button
        type="button"
        class="mobile-drawer__backdrop"
        aria-label="关闭管理导航"
        @click="closeMobileNavigation"
      />
      <aside
        ref="mobileDialog"
        id="admin-mobile-navigation"
        class="mobile-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="移动端管理导航"
      >
        <div class="mobile-drawer__header">
          <BrandMark tone="dark" />
          <button
            type="button"
            class="icon-button"
            aria-label="关闭管理导航"
            @click="closeMobileNavigation"
          >
            <CloseOutlined aria-hidden="true" />
          </button>
        </div>
        <nav class="shell-nav" aria-label="管理导航">
          <router-link
            v-for="item in navItems"
            :key="item.path"
            :to="item.path"
            class="shell-nav__link"
          >
            <component :is="item.icon" aria-hidden="true" />
            <span>{{ item.label }}</span>
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
