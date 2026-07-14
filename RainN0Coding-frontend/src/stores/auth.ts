import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { LoginUserVO } from '@/types/user'
import { login as loginApi, register as registerApi, logout as logoutApi, getLoginUser } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<LoginUserVO | null>(null)
  const initialized = ref(false)
  let mutationEpoch = 0
  let activeMutationEpoch: number | null = null
  let fetchSequence = 0
  let pendingMutationCount = 0
  let committedUser: LoginUserVO | null = null
  let mutationQueue: Promise<void> = Promise.resolve()

  const isAuthenticated = computed(() => !!user.value)
  const isAdmin = computed(() => user.value?.userRole === 'admin')
  const userName = computed(() => user.value?.userName || user.value?.userAccount || '')
  const userId = computed(() => user.value?.id)

  function beginMutation() {
    if (pendingMutationCount === 0) {
      committedUser = user.value
    }
    pendingMutationCount += 1
    mutationEpoch += 1
    activeMutationEpoch = mutationEpoch
    return mutationEpoch
  }

  function isCurrentMutation(epoch: number) {
    return epoch === mutationEpoch
  }

  function finishMutation(epoch: number) {
    pendingMutationCount -= 1
    if (activeMutationEpoch === epoch) {
      activeMutationEpoch = null
    }
  }

  function enqueueMutation<T>(operation: () => Promise<T>) {
    const result = mutationQueue.then(operation)
    mutationQueue = result.then(
      () => undefined,
      () => undefined,
    )
    return result
  }

  function beginFetch() {
    fetchSequence += 1
    return {
      sequence: fetchSequence,
      mutationEpoch,
      startedDuringMutation: activeMutationEpoch !== null,
    }
  }

  function canApplyFetch(request: ReturnType<typeof beginFetch>) {
    return (
      request.sequence === fetchSequence
      && request.mutationEpoch === mutationEpoch
      && !request.startedDuringMutation
      && activeMutationEpoch === null
    )
  }

  async function fetchCurrentUser() {
    const request = beginFetch()
    try {
      const data = await getLoginUser()
      if (canApplyFetch(request)) {
        committedUser = data
        user.value = data
      }
    } catch {
      if (canApplyFetch(request)) {
        committedUser = null
        user.value = null
      }
    } finally {
      if (canApplyFetch(request)) {
        initialized.value = true
      }
    }
  }

  async function login(account: string, password: string) {
    const epoch = beginMutation()
    try {
      await enqueueMutation(async () => {
        const data = await loginApi({ userAccount: account, userPassword: password })
        committedUser = data
      })
      if (!isCurrentMutation(epoch)) {
        return false
      }
      user.value = committedUser
      initialized.value = true
      return true
    } catch (error) {
      if (!isCurrentMutation(epoch)) {
        return false
      }
      user.value = committedUser
      initialized.value = true
      throw error
    } finally {
      finishMutation(epoch)
    }
  }

  async function register(account: string, password: string, checkPassword: string) {
    return registerApi({ userAccount: account, userPassword: password, checkPassword })
  }

  async function logout() {
    const epoch = beginMutation()
    try {
      await enqueueMutation(async () => {
        try {
          await logoutApi()
        } finally {
          committedUser = null
        }
      })
      if (!isCurrentMutation(epoch)) {
        return false
      }
      user.value = committedUser
      initialized.value = true
      return true
    } catch (error) {
      if (!isCurrentMutation(epoch)) {
        return false
      }
      user.value = committedUser
      initialized.value = true
      throw error
    } finally {
      finishMutation(epoch)
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
