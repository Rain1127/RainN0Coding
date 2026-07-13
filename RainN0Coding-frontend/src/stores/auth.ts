import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { LoginUserVO } from '@/types/user'
import { login as loginApi, register as registerApi, logout as logoutApi, getLoginUser } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<LoginUserVO | null>(null)
  const initialized = ref(false)

  const isAuthenticated = computed(() => !!user.value)
  const isAdmin = computed(() => user.value?.userRole === 'admin')
  const userName = computed(() => user.value?.userName || user.value?.userAccount || '')
  const userId = computed(() => user.value?.id)

  async function fetchCurrentUser() {
    try {
      const data = await getLoginUser()
      user.value = data
    } catch {
      user.value = null
    } finally {
      initialized.value = true
    }
  }

  async function login(account: string, password: string) {
    const data = await loginApi({ userAccount: account, userPassword: password })
    user.value = data
    return data
  }

  async function register(account: string, password: string, checkPassword: string) {
    return registerApi({ userAccount: account, userPassword: password, checkPassword })
  }

  async function logout() {
    try {
      await logoutApi()
    } finally {
      user.value = null
    }
  }

  return {
    user,
    initialized,
    isAuthenticated,
    isAdmin,
    userName,
    userId,
    fetchCurrentUser,
    login,
    register,
    logout,
  }
})
