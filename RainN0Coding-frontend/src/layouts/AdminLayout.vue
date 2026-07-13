<template>
  <div class="flex h-full">
    <!-- Admin Sidebar -->
    <div class="w-[220px] bg-admin-sidebar flex flex-col shrink-0">
      <div class="p-4 flex items-center gap-3">
        <div class="w-9 h-9 bg-admin-accent rounded-lg flex items-center justify-center">
          <span class="text-white font-bold text-sm">R</span>
        </div>
        <div>
          <div class="text-white text-sm font-medium">管理后台</div>
          <div class="text-gray-400 text-xs">Admin Console</div>
        </div>
      </div>
      <div class="flex-1 px-3 py-2">
        <div class="text-xs text-gray-500 px-3 py-2 font-medium uppercase">导航</div>
        <router-link v-for="item in navItems" :key="item.path" :to="item.path"
          class="flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm transition-colors my-0.5"
          :class="$route.path.startsWith(item.path) ? 'bg-admin-sidebar-hover text-white' : 'text-gray-300 hover:text-white hover:bg-admin-sidebar-hover'">
          <component :is="item.icon" />
          <span>{{ item.label }}</span>
        </router-link>
        <div class="text-xs text-gray-500 px-3 py-2 font-medium uppercase mt-4">设置</div>
        <router-link to="/admin/users"
          class="flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm transition-colors my-0.5"
          :class="$route.path === '/admin/users' ? 'bg-admin-sidebar-hover text-white' : 'text-gray-300 hover:text-white hover:bg-admin-sidebar-hover'">
          <UserOutlined /><span>用户管理</span>
        </router-link>
      </div>
    </div>
    <!-- Main -->
    <div class="flex-1 flex flex-col min-w-0">
      <div class="flex items-center justify-between px-6 py-3 border-b border-gray-200 bg-white">
        <div />
        <div class="flex items-center gap-3">
          <a-button type="link" size="small" @click="$router.push('/')">返回聊天</a-button>
          <a-dropdown>
            <a-avatar :size="32" class="cursor-pointer">{{ auth.userName?.charAt(0) }}</a-avatar>
            <template #overlay>
              <a-menu>
                <a-menu-item @click="handleLogout"><LogoutOutlined /> 退出登录</a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </div>
      </div>
      <div class="flex-1 overflow-y-auto bg-gray-50 p-6">
        <slot />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { AppstoreOutlined, ApartmentOutlined, UserOutlined, LogoutOutlined } from '@ant-design/icons-vue'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

const navItems = [
  { path: '/admin/apps', label: '应用管理', icon: AppstoreOutlined },
  { path: '/admin/intent-tree', label: '意图树配置', icon: ApartmentOutlined },
]

async function handleLogout() {
  await auth.logout()
  router.push('/login')
}
</script>
