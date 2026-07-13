<template>
  <div class="flex items-center justify-center min-h-full bg-gpt-bg-alt">
    <div class="w-full max-w-sm mx-auto p-8">
      <div class="text-center mb-8">
        <div class="w-12 h-12 bg-gpt-accent rounded-xl flex items-center justify-center mx-auto mb-4">
          <span class="text-white font-bold text-lg">AI</span>
        </div>
        <h1 class="text-2xl font-semibold text-gpt-text">欢迎回来</h1>
        <p class="text-gpt-text-muted mt-1">登录以开始使用 AI 代码生成</p>
      </div>
      <a-form :model="form" layout="vertical" @finish="handleLogin">
        <a-form-item name="userAccount" :rules="[{ required: true, message: '请输入账号' }]">
          <a-input v-model:value="form.userAccount" size="large" placeholder="账号" autocomplete="username" />
        </a-form-item>
        <a-form-item name="userPassword" :rules="[{ required: true, message: '请输入密码' }]">
          <a-input-password v-model:value="form.userPassword" size="large" placeholder="密码" autocomplete="current-password" />
        </a-form-item>
        <a-form-item>
          <a-button type="primary" html-type="submit" size="large" block :loading="loading">登录</a-button>
        </a-form-item>
      </a-form>
      <div class="text-center text-sm text-gpt-text-muted">
        没有账号？<router-link to="/register" class="text-gpt-accent hover:underline">去注册</router-link>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const loading = ref(false)

const form = reactive({
  userAccount: '',
  userPassword: '',
})

async function handleLogin() {
  loading.value = true
  try {
    await auth.login(form.userAccount, form.userPassword)
    const redirect = (route.query.redirect as string) || '/'
    router.push(redirect)
  } finally {
    loading.value = false
  }
}
</script>
