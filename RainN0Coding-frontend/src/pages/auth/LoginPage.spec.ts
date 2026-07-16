import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Antd from 'ant-design-vue'
import { useAuthStore } from '@/stores/auth'
import AuthLayout from '@/layouts/AuthLayout.vue'
import LoginPage from './LoginPage.vue'

vi.mock('@/stores/auth', () => ({ useAuthStore: vi.fn() }))

const AForm = defineComponent({
  name: 'AForm',
  props: { model: Object, layout: String },
  emits: ['finish'],
  template: '<form @submit.prevent="$emit(\'finish\')"><slot /></form>',
})

const AFormItem = defineComponent({
  name: 'AFormItem',
  props: { validateStatus: String },
  template: '<div><slot /><p class="ant-form-item-explain-error"><slot name="help" /></p></div>',
})

const AInput = defineComponent({
  name: 'AInput',
  inheritAttrs: false,
  props: { value: String, disabled: Boolean, size: String, placeholder: String, autocomplete: String },
  emits: ['update:value'],
  template: '<input v-bind="$attrs" :value="value" :disabled="disabled" :placeholder="placeholder" :autocomplete="autocomplete" @input="$emit(\'update:value\', $event.target.value)" />',
})

const AInputPassword = defineComponent({
  name: 'AInputPassword',
  inheritAttrs: false,
  props: { value: String, disabled: Boolean, size: String, placeholder: String, autocomplete: String },
  emits: ['update:value'],
  template: '<input v-bind="$attrs" type="password" :value="value" :disabled="disabled" :placeholder="placeholder" :autocomplete="autocomplete" @input="$emit(\'update:value\', $event.target.value)" />',
})

const AButton = defineComponent({
  name: 'AButton',
  inheritAttrs: false,
  props: { htmlType: String, loading: Boolean, disabled: Boolean, size: String, block: Boolean, type: String },
  template: '<button v-bind="$attrs" :type="htmlType" :disabled="disabled || loading"><slot /></button>',
})

async function createLoginRouter(redirect?: string | string[]) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<p>首页</p>' } },
      { path: '/login', component: LoginPage },
      { path: '/register', component: { template: '<p>注册页</p>' } },
      { path: '/chat/:id', component: { template: '<p>工作台</p>' } },
    ],
  })
  await router.push({ path: '/login', query: redirect === undefined ? {} : { redirect } })
  await router.isReady()
  return router
}

function mountLoginOnRouter(
  router: Awaited<ReturnType<typeof createLoginRouter>>,
  login: ReturnType<typeof vi.fn>,
) {
  vi.mocked(useAuthStore).mockReturnValue({ login } as unknown as ReturnType<typeof useAuthStore>)
  return mount(LoginPage, {
    attachTo: document.body,
    global: {
      plugins: [router],
      stubs: {
        AButton,
        AForm,
        AFormItem,
        AInput,
        AInputPassword,
        BrandMark: { template: '<span>RainN0Coding</span>' },
      },
    },
  })
}

async function mountLogin(redirect?: string | string[], login = vi.fn().mockResolvedValue(true)) {
  const router = await createLoginRouter(redirect)
  const wrapper = mountLoginOnRouter(router, login)
  return { login, router, wrapper }
}

async function submitValidLogin(wrapper: ReturnType<typeof mount>) {
  await wrapper.get('#login-account').setValue('builder')
  await wrapper.get('#login-password').setValue('safe-pass-123')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
}

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    })
  })

  it('uses the shared authentication layout and correct autocomplete metadata', async () => {
    const { wrapper } = await mountLogin()

    expect(wrapper.findComponent(AuthLayout).exists()).toBe(true)
    expect(wrapper.get('label[for="login-account"]').text()).toContain('账号')
    expect(wrapper.get('#login-account').attributes('autocomplete')).toBe('username')
    expect(wrapper.get('#login-account').attributes('name')).toBe('userAccount')
    expect(wrapper.get('#login-account').attributes('spellcheck')).toBe('false')
    expect(wrapper.get('#login-account').attributes('placeholder')).toMatch(/…$/)
    expect(wrapper.get('#login-password').attributes('autocomplete')).toBe('current-password')
    expect(wrapper.get('#login-password').attributes('name')).toBe('userPassword')
  })

  it('renders required semantics through real Ant Design inputs', async () => {
    const login = vi.fn().mockResolvedValue(true)
    vi.mocked(useAuthStore).mockReturnValue({ login } as unknown as ReturnType<typeof useAuthStore>)
    const router = await createLoginRouter()
    const wrapper = mount(LoginPage, {
      global: {
        plugins: [router, Antd],
        stubs: { BrandMark: { template: '<span>RainN0Coding</span>' } },
      },
    })

    for (const selector of ['#login-account', '#login-password']) {
      expect(wrapper.get(`input${selector}`).attributes('required')).toBeDefined()
      expect(wrapper.get(`input${selector}`).attributes('aria-required')).toBe('true')
    }
  })

  it.each([
    ['abc', 'safe-pass-123', '账号至少需要 4 个字符'],
    ['abcd', '1234567', '密码至少需要 8 个字符'],
    ['abcd', '        ', '密码不能只包含空格'],
  ])('blocks invalid backend boundary values for account %s', async (account, password, error) => {
    const { login, wrapper } = await mountLogin()
    await wrapper.get('#login-account').setValue(account)
    await wrapper.get('#login-password').setValue(password)

    await wrapper.get('form').trigger('submit')
    await nextTick()

    expect(wrapper.text()).toContain(error)
    expect(login).not.toHaveBeenCalled()
  })

  it('accepts the 4/8 boundary and trims the account', async () => {
    const { login, wrapper } = await mountLogin()
    await wrapper.get('#login-account').setValue('  abcd  ')
    await wrapper.get('#login-password').setValue('pass1234')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(login).toHaveBeenCalledWith('abcd', 'pass1234')
  })

  it('does not trim a non-blank password', async () => {
    const { login, wrapper } = await mountLogin()
    await wrapper.get('#login-account').setValue('abcd')
    await wrapper.get('#login-password').setValue(' pass123 ')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(login).toHaveBeenCalledWith('abcd', ' pass123 ')
  })

  it('focuses the first invalid field after submit', async () => {
    const { wrapper } = await mountLogin()

    await wrapper.get('form').trigger('submit')
    await nextTick()

    expect(document.activeElement).toBe(wrapper.get('#login-account').element)
  })

  it('allows a single-slash internal redirect after login', async () => {
    const { login, router, wrapper } = await mountLogin('/chat/42?tab=files#preview')

    await submitValidLogin(wrapper)

    expect(login).toHaveBeenCalledWith('builder', 'safe-pass-123')
    expect(router.currentRoute.value.fullPath).toBe('/chat/42?tab=files#preview')
  })

  it.each([
    '//evil.example/steal',
    'https://evil.example/steal',
    'javascript:alert(1)',
    '\\\\evil.example\\steal',
    '/\\evil.example/steal',
  ])('falls back to home for an unsafe redirect: %s', async (redirect) => {
    const { router, wrapper } = await mountLogin(redirect)

    await submitValidLogin(wrapper)

    expect(router.currentRoute.value.fullPath).toBe('/')
  })

  it('falls back to home when the redirect query has multiple values', async () => {
    const { router, wrapper } = await mountLogin(['/chat/42', '//evil.example'])

    await submitValidLogin(wrapper)

    expect(router.currentRoute.value.fullPath).toBe('/')
  })

  it('disables the form while login is pending', async () => {
    let resolveLogin!: (value: boolean) => void
    const login = vi.fn().mockReturnValue(new Promise((resolve) => { resolveLogin = resolve }))
    const { wrapper } = await mountLogin(undefined, login)
    await wrapper.get('#login-account').setValue('builder')
    await wrapper.get('#login-password').setValue('safe-pass-123')

    await wrapper.get('form').trigger('submit')
    await nextTick()

    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('button[type="submit"]').attributes('aria-busy')).toBe('true')
    expect(wrapper.get('button[type="submit"]').text()).toBe('正在登录…')
    resolveLogin(true)
    await flushPromises()
  })

  it('keeps credentials and shows a local error when login fails', async () => {
    const login = vi.fn().mockRejectedValue(new Error('账号或密码错误'))
    const { wrapper } = await mountLogin(undefined, login)

    await submitValidLogin(wrapper)

    expect(wrapper.get('[role="alert"]').text()).toContain('账号或密码错误')
    expect((wrapper.get('#login-account').element as HTMLInputElement).value).toBe('builder')
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined()
  })

  it('allows only the latest of two page instances to navigate after out-of-order logins', async () => {
    let resolveFirst!: (value: boolean) => void
    let resolveSecond!: (value: boolean) => void
    const login = vi.fn()
      .mockReturnValueOnce(new Promise<boolean>((resolve) => { resolveFirst = resolve }))
      .mockReturnValueOnce(new Promise<boolean>((resolve) => { resolveSecond = resolve }))
    const router = await createLoginRouter()
    const replace = vi.spyOn(router, 'replace')
    const first = mountLoginOnRouter(router, login)
    const second = mountLoginOnRouter(router, login)

    await first.get('#login-account').setValue('first')
    await first.get('#login-password').setValue('password-1')
    await first.get('form').trigger('submit')
    await second.get('#login-account').setValue('second')
    await second.get('#login-password').setValue('password-2')
    await second.get('form').trigger('submit')

    resolveSecond(true)
    await flushPromises()
    resolveFirst(false)
    await flushPromises()

    expect(replace).toHaveBeenCalledTimes(1)
  })

  it('does not navigate after the submitting page unmounts', async () => {
    let resolveLogin!: (value: boolean) => void
    const login = vi.fn().mockReturnValue(new Promise<boolean>((resolve) => { resolveLogin = resolve }))
    const { router, wrapper } = await mountLogin(undefined, login)
    const replace = vi.spyOn(router, 'replace')
    await wrapper.get('#login-account').setValue('builder')
    await wrapper.get('#login-password').setValue('safe-pass-123')
    await wrapper.get('form').trigger('submit')

    wrapper.unmount()
    resolveLogin(true)
    await flushPromises()

    expect(replace).not.toHaveBeenCalled()
  })
})
