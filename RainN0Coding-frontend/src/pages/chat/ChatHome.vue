<template>
  <ChatLayout>
    <div class="flex-1 flex flex-col items-center justify-center p-8">
      <div class="text-center max-w-2xl w-full">
        <div class="w-14 h-14 bg-gpt-accent rounded-2xl flex items-center justify-center mx-auto mb-6">
          <span class="text-white font-bold text-2xl">AI</span>
        </div>
        <h1 class="text-3xl font-semibold text-gpt-text mb-3">把想法变成<span class="text-gpt-accent">可运行代码</span></h1>
        <p class="text-gpt-text-muted text-base mb-10">
          支持 HTML、Vue、Python、Java、Go、Rust、Node.js 等多种语言
        </p>
        <div class="relative bg-gpt-bg border border-gpt-border rounded-2xl shadow-sm p-4">
          <a-textarea
            v-model:value="inputText"
            :auto-size="{ minRows: 2, maxRows: 6 }"
            placeholder="输入需要生成的代码描述..."
            class="chat-input"
            @press-enter="handleSend"
          />
          <div class="flex items-center justify-between mt-3">
            <a-button type="text" size="small" class="text-gpt-text-muted" @click="deepThink = !deepThink" :class="{ 'text-gpt-accent': deepThink }">
              <ThunderboltOutlined /> 深度思考
            </a-button>
            <a-button type="primary" shape="circle" :disabled="!inputText.trim()" @click="handleSend">
              <SendOutlined />
            </a-button>
          </div>
        </div>
        <p class="text-xs text-gpt-text-muted mt-3">Enter 发送，Shift + Enter 换行</p>

        <div class="mt-12">
          <p class="text-sm text-gpt-text-muted mb-4">试试这些开始</p>
          <div class="grid grid-cols-3 gap-3">
            <div v-for="card in recommendedCards" :key="card.title" class="bg-gpt-bg border border-gpt-border rounded-xl p-4 text-left cursor-pointer hover:border-gpt-accent transition-colors" @click="handleRecommend(card.prompt)">
              <component :is="card.icon" class="text-lg mb-2 text-gpt-accent" />
              <div class="text-sm font-medium text-gpt-text mb-1">{{ card.title }}</div>
              <div class="text-xs text-gpt-text-muted">{{ card.desc }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </ChatLayout>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ThunderboltOutlined, SendOutlined, CodeOutlined, LaptopOutlined, ApiOutlined } from '@ant-design/icons-vue'
import ChatLayout from '@/layouts/ChatLayout.vue'
import { createApp } from '@/api/app'

const router = useRouter()
const inputText = ref('')
const deepThink = ref(false)

const recommendedCards = [
  { icon: LaptopOutlined, title: 'Web 页面', desc: '创建一个响应式登录页面', prompt: '创建一个响应式登录页面，包含邮箱和密码输入框' },
  { icon: CodeOutlined, title: 'Python 脚本', desc: '编写数据分析工具', prompt: '用 Python 写一个 CSV 数据分析脚本' },
  { icon: ApiOutlined, title: 'Java 后端', desc: '生成 REST API 接口', prompt: '用 Spring Boot 写一个用户管理 REST API' },
]

async function handleSend() {
  const text = inputText.value.trim()
  if (!text) return
  try {
    const appId = await createApp({ initPrompt: text })
    router.push({ path: `/chat/${appId}`, query: { send: text } })
  } catch { /* handled */ }
}

function handleRecommend(prompt: string) {
  inputText.value = prompt
  handleSend()
}
</script>

<style scoped>
.chat-input :deep(textarea) {
  border: none !important;
  box-shadow: none !important;
  resize: none;
  font-size: 16px;
  line-height: 1.6;
  background: transparent;
}
</style>
