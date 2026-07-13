<template>
  <div class="flex items-center justify-center min-h-full bg-gpt-bg-alt">
    <div class="w-full max-w-sm mx-auto p-8">
      <div class="text-center mb-8">
        <div class="w-12 h-12 bg-gpt-accent rounded-xl flex items-center justify-center mx-auto mb-4">
          <span class="text-white font-bold text-lg">AI</span>
        </div>
        <h1 class="text-2xl font-semibold text-gpt-text">创建账号</h1>
        <p class="text-gpt-text-muted mt-1">注册后即可使用 AI 代码生成</p>
      </div>
      <a-form :model="form" layout="vertical" @finish="handleRegister">
        <a-form-item name="userAccount" :rules="[{ required: true, message: '请输入账号' }]">
          <a-input v-model:value="form.userAccount" size="large" placeholder="账号" autocomplete="username" />
        </a-form-item>
        <a-form-item name="userPassword" :rules="[{ required: true, min: 8, message: '密码至少8位' }]">
          <a-input-password v-model:value="form.userPassword" size="large" placeholder="密码（至少8位）" autocomplete="new-password" />
        </a-form-item>
        <a-form-item name="checkPassword" :rules="[{ required: true, message: '请确认密码' }, { validator: validateCheckPassword }]">
          <a-input-password v-model:value="form.checkPassword" size="large" placeholder="确认密码" />
        </a-form-item>
        <a-form-item>
          <a-button type="primary" html-type="submit" size="large" block :loading="loading">注册</a-button>
        </a-form-item>
      </a-form>
      <div class="text-center text-sm text-gpt-text-muted">
        已有账号？<router-link to="/login" class="text-gpt-accent hover:underline">去登录</router-link>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)

const form = reactive({
  userAccount: '',
  userPassword: '',
  checkPassword: '',
})

function validateCheckPassword(_rule: any, value: string) {
  if (value !== form.userPassword) {
    return Promise.reject('两次密码不一致')
  }
  return Promise.resolve()
}

async function handleRegister() {
  loading.value = true
  try {
    await auth.register(form.userAccount, form.userPassword, form.checkPassword)
    message.success('注册成功，请登录')
    router.push('/login')
  } finally {
    loading.value = false
  }
}
</script>
