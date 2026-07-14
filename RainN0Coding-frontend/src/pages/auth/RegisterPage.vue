<script setup lang="ts">
import { nextTick, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { useRouter } from 'vue-router'
import AuthLayout from '@/layouts/AuthLayout.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

const loading = ref(false)
const requestError = ref('')
const formAnnouncement = ref('')
type FocusableInput = { focus?: () => void; $el?: HTMLElement }
const accountInput = ref<FocusableInput | null>(null)
const passwordInput = ref<FocusableInput | null>(null)
const checkPasswordInput = ref<FocusableInput | null>(null)
const form = reactive({
  userAccount: '',
  userPassword: '',
  checkPassword: '',
})
const fieldErrors = reactive({
  userAccount: '',
  userPassword: '',
  checkPassword: '',
})

function validateAccount() {
  const account = form.userAccount.trim()
  if (!account) {
    fieldErrors.userAccount = '请输入账号'
  } else if (account.length < 4) {
    fieldErrors.userAccount = '账号至少需要 4 个字符'
  } else {
    fieldErrors.userAccount = ''
  }
  return !fieldErrors.userAccount
}

function validatePassword() {
  if (!form.userPassword) {
    fieldErrors.userPassword = '请输入密码'
  } else if (!form.userPassword.trim()) {
    fieldErrors.userPassword = '密码不能只包含空格'
  } else if (form.userPassword.length < 8) {
    fieldErrors.userPassword = '密码至少需要 8 个字符'
  } else {
    fieldErrors.userPassword = ''
  }
  return !fieldErrors.userPassword
}

function validateCheckPassword() {
  if (!form.checkPassword) {
    fieldErrors.checkPassword = '请再次输入密码'
  } else if (form.checkPassword !== form.userPassword) {
    fieldErrors.checkPassword = '两次输入的密码不一致'
  } else {
    fieldErrors.checkPassword = ''
  }
  return !fieldErrors.checkPassword
}

function validateForm() {
  const accountValid = validateAccount()
  const passwordValid = validatePassword()
  const checkPasswordValid = validateCheckPassword()
  formAnnouncement.value = (
    fieldErrors.userAccount
    || fieldErrors.userPassword
    || fieldErrors.checkPassword
  )
  return accountValid && passwordValid && checkPasswordValid
}

function focusControl(control: FocusableInput | null) {
  if (control?.focus) {
    control.focus()
    return
  }
  const element = control?.$el
  if (element instanceof HTMLInputElement) {
    element.focus()
  } else {
    element?.querySelector('input')?.focus()
  }
}

function focusFirstError() {
  void nextTick(() => {
    const control = fieldErrors.userAccount
      ? accountInput.value
      : fieldErrors.userPassword
        ? passwordInput.value
        : checkPasswordInput.value
    focusControl(control)
  })
}

function errorMessage(error: unknown) {
  if (error instanceof Error && error.message.trim()) {
    return `${error.message.trim()}，请修改后重试`
  }
  return '注册失败，请检查填写内容后重试'
}

async function handleRegister() {
  if (loading.value) {
    return
  }
  if (!validateForm()) {
    focusFirstError()
    return
  }

  requestError.value = ''
  formAnnouncement.value = ''
  loading.value = true
  try {
    await auth.register(form.userAccount.trim(), form.userPassword, form.checkPassword)
    message.success('注册成功，请登录')
    await router.replace('/login')
  } catch (error) {
    requestError.value = errorMessage(error)
    formAnnouncement.value = requestError.value
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <AuthLayout>
    <section class="auth-card" aria-labelledby="register-title">
      <header class="auth-card__header">
        <p class="auth-card__eyebrow">开始新的构建</p>
        <h1 id="register-title" class="auth-card__title">创建账号</h1>
        <p class="auth-card__description">注册后即可让多个 AI 角色协作完成你的应用。</p>
      </header>

      <a-form :model="form" layout="vertical" class="auth-form" novalidate @finish="handleRegister">
        <a-form-item :validate-status="fieldErrors.userAccount ? 'error' : undefined">
          <label class="auth-form__label" for="register-account">
            账号<span class="auth-form__required" aria-hidden="true">*</span>
          </label>
          <a-input
            ref="accountInput"
            id="register-account"
            name="userAccount"
            v-model:value="form.userAccount"
            size="large"
            autocomplete="username"
            spellcheck="false"
            required
            aria-required="true"
            placeholder="例如：builder_01…"
            :disabled="loading"
            :aria-invalid="Boolean(fieldErrors.userAccount)"
            :aria-describedby="fieldErrors.userAccount ? 'register-account-error' : undefined"
            @blur="validateAccount"
          />
          <template #help>
            <span v-if="fieldErrors.userAccount" id="register-account-error">
              {{ fieldErrors.userAccount }}
            </span>
          </template>
        </a-form-item>

        <a-form-item :validate-status="fieldErrors.userPassword ? 'error' : undefined">
          <label class="auth-form__label" for="register-password">
            密码<span class="auth-form__required" aria-hidden="true">*</span>
          </label>
          <a-input-password
            ref="passwordInput"
            id="register-password"
            name="userPassword"
            v-model:value="form.userPassword"
            size="large"
            autocomplete="new-password"
            required
            aria-required="true"
            placeholder="设置至少 8 个字符的密码…"
            :disabled="loading"
            :aria-invalid="Boolean(fieldErrors.userPassword)"
            :aria-describedby="fieldErrors.userPassword ? 'register-password-error' : 'register-password-hint'"
            @blur="validatePassword"
          />
          <p v-if="!fieldErrors.userPassword" id="register-password-hint" class="auth-form__hint">
            至少 8 个字符，建议组合字母、数字与符号。
          </p>
          <template #help>
            <span v-if="fieldErrors.userPassword" id="register-password-error">
              {{ fieldErrors.userPassword }}
            </span>
          </template>
        </a-form-item>

        <a-form-item :validate-status="fieldErrors.checkPassword ? 'error' : undefined">
          <label class="auth-form__label" for="register-check-password">
            确认密码<span class="auth-form__required" aria-hidden="true">*</span>
          </label>
          <a-input-password
            ref="checkPasswordInput"
            id="register-check-password"
            name="checkPassword"
            v-model:value="form.checkPassword"
            size="large"
            autocomplete="new-password"
            required
            aria-required="true"
            placeholder="再次输入密码…"
            :disabled="loading"
            :aria-invalid="Boolean(fieldErrors.checkPassword)"
            :aria-describedby="fieldErrors.checkPassword ? 'register-check-password-error' : undefined"
            @blur="validateCheckPassword"
          />
          <template #help>
            <span v-if="fieldErrors.checkPassword" id="register-check-password-error">
              {{ fieldErrors.checkPassword }}
            </span>
          </template>
        </a-form-item>

        <p v-if="requestError" class="auth-card__error" role="alert">
          {{ requestError }}
        </p>
        <p class="sr-only" aria-live="polite">{{ formAnnouncement }}</p>

        <a-button
          class="auth-form__submit"
          type="primary"
          html-type="submit"
          size="large"
          block
          :loading="loading"
          :disabled="loading"
          :aria-busy="loading"
        >
          {{ loading ? '正在注册…' : '创建账号' }}
        </a-button>
      </a-form>

      <p class="auth-card__footer">
        已有账号？
        <router-link to="/login">返回登录</router-link>
      </p>
    </section>
  </AuthLayout>
</template>

<style scoped>
.auth-card {
  width: min(100%, 440px);
  padding: clamp(var(--space-6), 5vw, var(--space-10));
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  box-shadow: var(--shadow-card);
}

.auth-card__header {
  margin-bottom: var(--space-8);
}

.auth-card__eyebrow {
  margin: 0 0 var(--space-2);
  color: var(--color-primary);
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.auth-card__title {
  margin: 0;
  font-size: clamp(1.75rem, 5vw, 2.25rem);
  line-height: 1.2;
  letter-spacing: -0.03em;
  text-wrap: balance;
}

.auth-card__description {
  margin: var(--space-3) 0 0;
  color: var(--color-text-muted);
}

.auth-form__label {
  display: inline-block;
  margin-bottom: var(--space-2);
  color: var(--color-text);
  font-weight: 700;
}

.auth-form__required {
  margin-left: var(--space-1);
  color: var(--color-danger);
}

.auth-form__hint {
  margin: var(--space-2) 0 0;
  color: var(--color-text-muted);
  font-size: 0.875rem;
}

.auth-card__error {
  margin: 0 0 var(--space-4);
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--color-danger);
  border-radius: var(--radius-sm);
  color: var(--color-danger);
  background: var(--color-danger-soft);
}

.auth-form__submit {
  min-height: 44px;
  margin-top: var(--space-2);
}

.auth-card__footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: var(--space-1);
  margin: var(--space-6) 0 0;
  color: var(--color-text-muted);
  text-align: center;
}

.auth-card__footer a {
  display: inline-flex;
  min-height: 44px;
  align-items: center;
  border-radius: var(--radius-sm);
  color: var(--color-primary);
  font-weight: 700;
  text-decoration: none;
}

.auth-card__footer a:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}

:deep(.ant-input),
:deep(.ant-input-affix-wrapper) {
  min-height: 44px;
  font-size: 16px;
}

@media (max-width: 767px) {
  .auth-card {
    padding: var(--space-6) var(--space-5);
  }
}
</style>
