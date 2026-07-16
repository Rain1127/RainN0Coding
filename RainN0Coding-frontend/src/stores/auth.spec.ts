import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  getLoginUser,
  login as loginApi,
  logout as logoutApi,
  register as registerApi,
} from '@/api/auth'
import type { LoginUserVO } from '@/types/user'
import { useAuthStore } from './auth'

vi.mock('@/api/auth', () => ({
  getLoginUser: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  register: vi.fn(),
}))

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, reject, resolve }
}

async function flushMicrotasks() {
  await Promise.resolve()
  await Promise.resolve()
}

function user(id: number, account: string): LoginUserVO {
  return {
    id,
    userAccount: account,
    userName: account,
    userAvatar: '',
    userProfile: '',
    userRole: 'user',
    createTime: '2026-07-14T00:00:00',
    updateTime: '2026-07-14T00:00:00',
  }
}

describe('auth store request ordering', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    vi.mocked(registerApi).mockResolvedValue(1)
    vi.mocked(logoutApi).mockResolvedValue(true)
  })

  it('lets only the latest login result update the authenticated user', async () => {
    const first = deferred<LoginUserVO>()
    const second = deferred<LoginUserVO>()
    vi.mocked(loginApi)
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)
    const store = useAuthStore()

    const firstResult = store.login('first', 'password-1')
    const secondResult = store.login('second', 'password-2')
    await flushMicrotasks()
    expect(loginApi).toHaveBeenCalledTimes(1)
    expect(loginApi).toHaveBeenLastCalledWith({
      userAccount: 'first',
      userPassword: 'password-1',
    })

    first.resolve(user(1, 'first'))
    await expect(firstResult).resolves.toBe(false)
    await flushMicrotasks()
    expect(loginApi).toHaveBeenCalledTimes(2)

    second.resolve(user(2, 'second'))
    await expect(secondResult).resolves.toBe(true)
    expect(store.user?.id).toBe(2)
  })

  it('suppresses a stale login error after a newer login succeeds', async () => {
    const first = deferred<LoginUserVO>()
    const second = deferred<LoginUserVO>()
    vi.mocked(loginApi)
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)
    const store = useAuthStore()

    const firstResult = store.login('first', 'password-1')
    const secondResult = store.login('second', 'password-2')
    await flushMicrotasks()
    expect(loginApi).toHaveBeenCalledTimes(1)

    first.reject(new Error('old request failed'))
    await expect(firstResult).resolves.toBe(false)
    await flushMicrotasks()
    expect(loginApi).toHaveBeenCalledTimes(2)

    second.resolve(user(2, 'second'))
    await expect(secondResult).resolves.toBe(true)
    expect(store.user?.id).toBe(2)
  })

  it('keeps the previous successful server session when the latest queued login fails', async () => {
    const first = deferred<LoginUserVO>()
    const second = deferred<LoginUserVO>()
    vi.mocked(loginApi)
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)
    const store = useAuthStore()

    const firstResult = store.login('first', 'password-1')
    const secondResult = store.login('second', 'password-2')
    first.resolve(user(1, 'first'))
    await expect(firstResult).resolves.toBe(false)

    second.reject(new Error('latest login failed'))
    await expect(secondResult).rejects.toThrow('latest login failed')
    expect(store.user?.id).toBe(1)
    expect(store.initialized).toBe(true)
  })

  it('keeps a newer login when an earlier initialization resolves late', async () => {
    const initialization = deferred<LoginUserVO>()
    const login = deferred<LoginUserVO>()
    vi.mocked(getLoginUser).mockReturnValueOnce(initialization.promise)
    vi.mocked(loginApi).mockReturnValueOnce(login.promise)
    const store = useAuthStore()

    const initializationResult = store.fetchCurrentUser()
    const loginResult = store.login('latest', 'password-1')
    login.resolve(user(2, 'latest'))
    await expect(loginResult).resolves.toBe(true)

    initialization.resolve(user(1, 'initial'))
    await initializationResult
    expect(store.user?.id).toBe(2)
    expect(store.initialized).toBe(true)
  })

  it('marks initialization complete when the latest login fails', async () => {
    const initialization = deferred<LoginUserVO>()
    vi.mocked(getLoginUser).mockReturnValueOnce(initialization.promise)
    vi.mocked(loginApi).mockRejectedValueOnce(new Error('invalid credentials'))
    const store = useAuthStore()

    const initializationResult = store.fetchCurrentUser()
    await expect(store.login('latest', 'password-1')).rejects.toThrow('invalid credentials')
    expect(store.initialized).toBe(true)

    initialization.resolve(user(1, 'stale-session'))
    await initializationResult
    expect(store.user).toBeNull()
    expect(store.initialized).toBe(true)
  })

  it('does not let a fetch started during login invalidate or overwrite the login', async () => {
    const login = deferred<LoginUserVO>()
    const initialization = deferred<LoginUserVO>()
    vi.mocked(loginApi).mockReturnValueOnce(login.promise)
    vi.mocked(getLoginUser).mockReturnValueOnce(initialization.promise)
    const store = useAuthStore()
    store.user = user(1, 'current')

    const loginResult = store.login('latest-login', 'password-1')
    const initializationResult = store.fetchCurrentUser()
    login.resolve(user(2, 'latest-login'))
    await expect(loginResult).resolves.toBe(true)
    expect(store.user?.id).toBe(2)

    initialization.resolve(user(1, 'stale-session'))
    await initializationResult
    expect(store.user?.id).toBe(2)
    expect(store.initialized).toBe(true)
  })

  it('ignores an unauthenticated fetch that resolves while login is active', async () => {
    const login = deferred<LoginUserVO>()
    const initialization = deferred<LoginUserVO>()
    vi.mocked(loginApi).mockReturnValueOnce(login.promise)
    vi.mocked(getLoginUser).mockReturnValueOnce(initialization.promise)
    const store = useAuthStore()
    store.user = user(1, 'current')

    const loginResult = store.login('latest-login', 'password-1')
    const initializationResult = store.fetchCurrentUser()
    initialization.reject(new Error('not logged in'))
    await initializationResult
    expect(store.user?.id).toBe(1)
    expect(store.initialized).toBe(false)

    login.resolve(user(2, 'latest-login'))
    await expect(loginResult).resolves.toBe(true)
    expect(store.user?.id).toBe(2)
    expect(store.initialized).toBe(true)
  })

  it('does not let a fetch started during logout preserve a stale user', async () => {
    const logout = deferred<boolean>()
    const initialization = deferred<LoginUserVO>()
    vi.mocked(logoutApi).mockReturnValueOnce(logout.promise)
    vi.mocked(getLoginUser).mockReturnValueOnce(initialization.promise)
    const store = useAuthStore()
    store.user = user(2, 'current')

    const logoutResult = store.logout()
    const initializationResult = store.fetchCurrentUser()
    initialization.resolve(user(1, 'stale-session'))
    await initializationResult
    expect(store.user?.id).toBe(2)

    logout.resolve(true)
    await expect(logoutResult).resolves.toBe(true)
    expect(store.user).toBeNull()
    expect(store.initialized).toBe(true)
  })

  it('does not let a fetch started before logout overwrite the completed logout', async () => {
    const initialization = deferred<LoginUserVO>()
    vi.mocked(getLoginUser).mockReturnValueOnce(initialization.promise)
    const store = useAuthStore()
    store.user = user(1, 'current')

    const initializationResult = store.fetchCurrentUser()
    await store.logout()
    expect(store.user).toBeNull()

    initialization.resolve(user(1, 'stale-session'))
    await initializationResult
    expect(store.user).toBeNull()
  })

  it('lets only the latest ordinary fetch update the session', async () => {
    const first = deferred<LoginUserVO>()
    const second = deferred<LoginUserVO>()
    vi.mocked(getLoginUser)
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)
    const store = useAuthStore()

    const firstResult = store.fetchCurrentUser()
    const secondResult = store.fetchCurrentUser()
    second.resolve(user(2, 'latest-fetch'))
    await secondResult
    expect(store.user?.id).toBe(2)

    first.resolve(user(1, 'stale-fetch'))
    await firstResult
    expect(store.user?.id).toBe(2)
    expect(store.initialized).toBe(true)
  })

  it('invalidates a pending login when logout starts', async () => {
    const login = deferred<LoginUserVO>()
    const logout = deferred<boolean>()
    vi.mocked(loginApi).mockReturnValueOnce(login.promise)
    vi.mocked(logoutApi).mockReturnValueOnce(logout.promise)
    const store = useAuthStore()
    store.user = user(1, 'current')

    const loginResult = store.login('pending', 'password-1')
    const logoutResult = store.logout()
    await flushMicrotasks()
    expect(loginApi).toHaveBeenCalledTimes(1)
    expect(logoutApi).not.toHaveBeenCalled()

    login.resolve(user(2, 'pending'))
    await expect(loginResult).resolves.toBe(false)
    await flushMicrotasks()
    expect(logoutApi).toHaveBeenCalledTimes(1)

    logout.resolve(true)
    await expect(logoutResult).resolves.toBe(true)
    expect(store.user).toBeNull()
  })

  it('waits for logout before starting a newer login', async () => {
    const logout = deferred<boolean>()
    const login = deferred<LoginUserVO>()
    vi.mocked(logoutApi).mockReturnValueOnce(logout.promise)
    vi.mocked(loginApi).mockReturnValueOnce(login.promise)
    const store = useAuthStore()
    store.user = user(1, 'current')

    const logoutResult = store.logout()
    const loginResult = store.login('next', 'password-1')
    await flushMicrotasks()
    expect(logoutApi).toHaveBeenCalledTimes(1)
    expect(loginApi).not.toHaveBeenCalled()

    logout.resolve(true)
    await expect(logoutResult).resolves.toBe(false)
    expect(store.user?.id).toBe(1)
    await flushMicrotasks()
    expect(loginApi).toHaveBeenCalledTimes(1)

    login.resolve(user(2, 'next'))
    await expect(loginResult).resolves.toBe(true)
    expect(store.user?.id).toBe(2)
  })

  it('reflects a completed logout when the newer queued login fails', async () => {
    const logout = deferred<boolean>()
    const login = deferred<LoginUserVO>()
    vi.mocked(logoutApi).mockReturnValueOnce(logout.promise)
    vi.mocked(loginApi).mockReturnValueOnce(login.promise)
    const store = useAuthStore()
    store.user = user(1, 'current')

    const logoutResult = store.logout()
    const loginResult = store.login('next', 'password-1')
    logout.resolve(true)
    await expect(logoutResult).resolves.toBe(false)

    login.reject(new Error('latest login failed'))
    await expect(loginResult).rejects.toThrow('latest login failed')
    expect(store.user).toBeNull()
    expect(store.initialized).toBe(true)
  })
})
