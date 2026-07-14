import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Antd from 'ant-design-vue'
import { useAuthStore } from '@/stores/auth'
import AuthLayout from '@/layouts/AuthLayout.vue'
import RegisterPage from './RegisterPage.vue'

vi.mock('@/stores/auth', () => ({ useAuthStore: vi.fn() }))
vi.mock('ant-design-vue', async (importOriginal) => {
  const actual = await importOriginal<typeof import('ant-design-vue')>()
  return { ...actual, message: { success: vi.fn() } }
})

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

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, reject, resolve }
}

async function mountRegister(register = vi.fn().mockResolvedValue(1)) {
  vi.mocked(useAuthStore).mockReturnValue({ register } as unknown as ReturnType<typeof useAuthStore>)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/register', component: RegisterPage },
      { path: '/login', component: { template: '<p>登录页</p>' } },
    ],
  })
  await router.push('/register')
  await router.isReady()

  const wrapper = mount(RegisterPage, {
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
  return { register, router, wrapper }
}

describe('RegisterPage', () => {
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

  it('uses the shared authentication layout and accessible field metadata', async () => {
    const { wrapper } = await mountRegister()

    expect(wrapper.findComponent(AuthLayout).exists()).toBe(true)
    expect(wrapper.get('label[for="register-account"]').text()).toContain('账号')
    expect(wrapper.get('#register-account').attributes('autocomplete')).toBe('username')
    expect(wrapper.get('#register-account').attributes('name')).toBe('userAccount')
    expect(wrapper.get('#register-account').attributes('spellcheck')).toBe('false')
    expect(wrapper.get('#register-account').attributes('placeholder')).toMatch(/…$/)
    expect(wrapper.get('#register-password').attributes('autocomplete')).toBe('new-password')
    expect(wrapper.get('#register-password').attributes('name')).toBe('userPassword')
    expect(wrapper.get('#register-check-password').attributes('autocomplete')).toBe('new-password')
    expect(wrapper.get('#register-check-password').attributes('name')).toBe('checkPassword')
  })

  it('renders required semantics through real Ant Design inputs', async () => {
    const register = vi.fn().mockResolvedValue(1)
    vi.mocked(useAuthStore).mockReturnValue({ register } as unknown as ReturnType<typeof useAuthStore>)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/register', component: RegisterPage },
        { path: '/login', component: { template: '<p>登录页</p>' } },
      ],
    })
    await router.push('/register')
    await router.isReady()
    const wrapper = mount(RegisterPage, {
      global: {
        plugins: [router, Antd],
        stubs: { BrandMark: { template: '<span>RainN0Coding</span>' } },
      },
    })

    for (const selector of [
      '#register-account',
      '#register-password',
      '#register-check-password',
    ]) {
      expect(wrapper.get(`input${selector}`).attributes('required')).toBeDefined()
      expect(wrapper.get(`input${selector}`).attributes('aria-required')).toBe('true')
    }
  })

  it.each([
    ['abc', '12345678', '12345678', '账号至少需要 4 个字符'],
    ['abcd', '1234567', '1234567', '密码至少需要 8 个字符'],
    ['abcd', '        ', '        ', '密码不能只包含空格'],
  ])('blocks invalid backend boundary values for account %s', async (
    account,
    password,
    checkPassword,
    error,
  ) => {
    const { register, wrapper } = await mountRegister()
    await wrapper.get('#register-account').setValue(account)
    await wrapper.get('#register-password').setValue(password)
    await wrapper.get('#register-check-password').setValue(checkPassword)

    await wrapper.get('form').trigger('submit')
    await nextTick()

    expect(wrapper.text()).toContain(error)
    expect(register).not.toHaveBeenCalled()
  })

  it('accepts the 4/8 boundary and trims the account', async () => {
    const { register, wrapper } = await mountRegister()
    await wrapper.get('#register-account').setValue('  abcd  ')
    await wrapper.get('#register-password').setValue('pass1234')
    await wrapper.get('#register-check-password').setValue('pass1234')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(register).toHaveBeenCalledWith('abcd', 'pass1234', 'pass1234')
  })

  it('does not trim a non-blank password', async () => {
    const { register, wrapper } = await mountRegister()
    await wrapper.get('#register-account').setValue('abcd')
    await wrapper.get('#register-password').setValue(' pass123 ')
    await wrapper.get('#register-check-password').setValue(' pass123 ')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(register).toHaveBeenCalledWith('abcd', ' pass123 ', ' pass123 ')
  })

  it('focuses the first invalid field after submit', async () => {
    const { wrapper } = await mountRegister()

    await wrapper.get('form').trigger('submit')
    await nextTick()

    expect(document.activeElement).toBe(wrapper.get('#register-account').element)
  })

  it('shows an inline mismatch error and does not call register', async () => {
    const { register, wrapper } = await mountRegister()
    await wrapper.get('#register-account').setValue('builder')
    await wrapper.get('#register-password').setValue('safe-pass-123')
    await wrapper.get('#register-check-password').setValue('different-pass')

    await wrapper.get('form').trigger('submit')
    await nextTick()

    expect(wrapper.text()).toContain('两次输入的密码不一致')
    expect(wrapper.get('#register-check-password').attributes('aria-describedby')).toBe(
      'register-check-password-error',
    )
    expect(wrapper.get('#register-check-password').attributes('aria-invalid')).toBe('true')
    expect(register).not.toHaveBeenCalled()
  })

  it('disables the form while registration is pending and prevents duplicate requests', async () => {
    const pending = deferred<number>()
    const register = vi.fn().mockReturnValue(pending.promise)
    const { wrapper } = await mountRegister(register)
    await wrapper.get('#register-account').setValue('builder')
    await wrapper.get('#register-password').setValue('safe-pass-123')
    await wrapper.get('#register-check-password').setValue('safe-pass-123')

    await wrapper.get('form').trigger('submit')
    await nextTick()

    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('button[type="submit"]').attributes('aria-busy')).toBe('true')
    expect(wrapper.get('button[type="submit"]').text()).toBe('正在注册…')
    await wrapper.get('form').trigger('submit')
    expect(register).toHaveBeenCalledTimes(1)

    pending.resolve(1)
    await flushPromises()
  })

  it('routes to login after a successful registration', async () => {
    const { register, router, wrapper } = await mountRegister()
    await wrapper.get('#register-account').setValue('builder')
    await wrapper.get('#register-password').setValue('safe-pass-123')
    await wrapper.get('#register-check-password').setValue('safe-pass-123')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(register).toHaveBeenCalledWith('builder', 'safe-pass-123', 'safe-pass-123')
    expect(router.currentRoute.value.fullPath).toBe('/login')
  })

  it('keeps entered values and shows a local error when registration fails', async () => {
    const register = vi.fn().mockRejectedValue(new Error('账号已存在'))
    const { router, wrapper } = await mountRegister(register)
    await wrapper.get('#register-account').setValue('builder')
    await wrapper.get('#register-password').setValue('safe-pass-123')
    await wrapper.get('#register-check-password').setValue('safe-pass-123')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('账号已存在')
    expect((wrapper.get('#register-account').element as HTMLInputElement).value).toBe('builder')
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined()
    expect(router.currentRoute.value.fullPath).toBe('/register')
  })
})
