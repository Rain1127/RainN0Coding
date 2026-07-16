<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  FolderOpenOutlined,
  WarningOutlined,
} from '@ant-design/icons-vue'
import { createApp } from '@/api/app'
import PromptComposer, { type PromptExample } from '@/components/generation/PromptComposer.vue'
import ChatLayout from '@/layouts/ChatLayout.vue'
import { useAppsStore } from '@/stores/apps'

type HealthStatus = 'checking' | 'online' | 'offline'

const router = useRouter()
const apps = useAppsStore()
const creating = ref(false)
const createError = ref('')
const lastPrompt = ref('')
const pendingNavigation = ref<{ appId: number; prompt: string } | null>(null)
const javaStatus = ref<HealthStatus>('checking')
const pythonStatus = ref<HealthStatus>('checking')
let serviceCheckSequence = 0
let viewUnmounted = false

const examples: PromptExample[] = [
  {
    title: '运营数据看板',
    description: '响应式图表与筛选',
    prompt: '创建一个运营数据看板，包含趋势图、渠道筛选、关键指标卡片和响应式布局。',
  },
  {
    title: '团队任务中心',
    description: '分组、负责人和进度',
    prompt: '创建一个团队任务管理应用，支持看板分组、负责人筛选、截止日期和进度统计。',
  },
  {
    title: '内容管理后台',
    description: '列表、编辑与权限状态',
    prompt: '创建一个内容管理后台，包含文章列表、关键词搜索、编辑表单和发布状态。',
  },
]

function apiUrl(path: string) {
  const base = (import.meta.env.VITE_API_BASE ?? '/api').replace(/\/$/, '')
  return `${base}${path}`
}

async function probe(url: string, credentials?: RequestCredentials) {
  try {
    const response = await fetch(url, { credentials, signal: AbortSignal.timeout(4000) })
    return response.ok ? 'online' : 'offline'
  } catch {
    return 'offline'
  }
}

async function checkServices() {
  const requestId = ++serviceCheckSequence
  javaStatus.value = 'checking'
  pythonStatus.value = 'checking'
  const pythonBase = (import.meta.env.VITE_PYTHON_API_BASE ?? 'http://localhost:8000').replace(/\/$/, '')
  const [java, python] = await Promise.all([
    probe(apiUrl('/health/'), 'include'),
    probe(`${pythonBase}/api/health`),
  ])
  if (viewUnmounted || requestId !== serviceCheckSequence) return
  javaStatus.value = java
  pythonStatus.value = python
}

async function navigateToProject(appId: number, prompt: string) {
  await router.push({
    name: 'ChatDetail',
    params: { appId },
    state: { initialPrompt: prompt },
  })
}

async function handleSubmit(prompt: string) {
  if (creating.value) return
  const normalized = prompt.trim()
  if (!normalized) return
  creating.value = true
  createError.value = ''
  lastPrompt.value = normalized
  let createdThisAttempt = false

  try {
    let appId: number
    if (pendingNavigation.value?.prompt === normalized) {
      appId = pendingNavigation.value.appId
    } else {
      appId = await createApp({ initPrompt: normalized })
      pendingNavigation.value = { appId, prompt: normalized }
      createdThisAttempt = true
    }
    await navigateToProject(appId, normalized)
    pendingNavigation.value = null
  } catch {
    createError.value = createdThisAttempt || pendingNavigation.value
      ? '项目已创建，但工作台暂时无法打开。你可以直接重试。'
      : '项目创建失败，请检查网络后重试。'
  } finally {
    creating.value = false
  }
}

function retryCreate() {
  if (lastPrompt.value) void handleSubmit(lastPrompt.value)
}

onMounted(() => {
  void checkServices()
})

onUnmounted(() => {
  viewUnmounted = true
  serviceCheckSequence += 1
})
</script>

<template>
  <ChatLayout>
    <div class="home-page content-container">
      <section class="home-hero" aria-labelledby="home-title">
        <p class="home-hero__eyebrow">AI 多智能体开发工作台</p>
        <h1 id="home-title">把产品想法变成可运行项目</h1>
        <p class="home-hero__description">
          描述目标用户、核心页面和关键流程。八个智能体会协作完成需求分析、架构、编码与构建。
        </p>

        <PromptComposer :examples="examples" :loading="creating" @submit="handleSubmit" />

        <div v-if="createError" class="home-create-error" role="alert">
          <span>{{ createError }}</span>
          <button type="button" data-action="retry-create" :disabled="creating" @click="retryCreate">
            重试
          </button>
        </div>
      </section>

      <section class="home-section" aria-labelledby="recent-projects-title">
        <div class="home-section__header">
          <div>
            <p class="home-section__eyebrow">继续工作</p>
            <h2 id="recent-projects-title">最近项目</h2>
          </div>
          <router-link to="/projects" class="home-section__link">查看全部项目</router-link>
        </div>

        <div v-if="apps.recentLoading" class="recent-projects" aria-label="正在加载最近项目…" aria-busy="true">
          <div v-for="index in 3" :key="index" class="recent-project-card recent-project-card--skeleton" />
        </div>
        <p v-else-if="apps.recentError" class="home-inline-note" role="status">
          最近项目暂时无法加载，不影响创建新项目。
        </p>
        <div v-else-if="apps.recentApps.length" class="recent-projects">
          <router-link
            v-for="project in apps.recentApps.slice(0, 3)"
            :key="project.id"
            :to="`/chat/${project.id}`"
            class="recent-project-card"
          >
            <FolderOpenOutlined aria-hidden="true" />
            <span class="recent-project-card__name">{{ project.appName || '未命名项目' }}</span>
            <span class="recent-project-card__type mono">{{ project.codeGenType }}</span>
          </router-link>
        </div>
        <p v-else class="home-inline-note">还没有项目。提交上方需求，创建第一个可运行应用。</p>
      </section>

      <section class="home-section" aria-labelledby="service-status-title">
        <div class="home-section__header">
          <div>
            <p class="home-section__eyebrow">运行环境</p>
            <h2 id="service-status-title">服务状态</h2>
          </div>
          <button type="button" class="home-section__link home-section__link--button" @click="checkServices">
            重新检查
          </button>
        </div>
        <div class="service-statuses" aria-live="polite">
          <div class="service-status" :class="`service-status--${javaStatus}`">
            <ClockCircleOutlined v-if="javaStatus === 'checking'" aria-hidden="true" />
            <CheckCircleOutlined v-else-if="javaStatus === 'online'" aria-hidden="true" />
            <WarningOutlined v-else aria-hidden="true" />
            <span><strong>Java 服务</strong>{{ javaStatus === 'online' ? '运行正常' : javaStatus === 'offline' ? '暂不可用' : '检查中…' }}</span>
          </div>
          <div class="service-status" :class="`service-status--${pythonStatus}`">
            <ClockCircleOutlined v-if="pythonStatus === 'checking'" aria-hidden="true" />
            <CheckCircleOutlined v-else-if="pythonStatus === 'online'" aria-hidden="true" />
            <WarningOutlined v-else aria-hidden="true" />
            <span><strong>Python 服务</strong>{{ pythonStatus === 'online' ? '运行正常' : pythonStatus === 'offline' ? '暂不可用' : '检查中…' }}</span>
          </div>
        </div>
        <p class="home-inline-note">状态检查失败不会阻止你编写或保存需求。</p>
      </section>
    </div>
  </ChatLayout>
</template>

<style scoped>
.home-page {
  width: 100%;
  max-width: 1080px;
  margin: 0 auto;
  padding: clamp(32px, 6vw, 72px) clamp(20px, 5vw, 56px);
}

.home-hero {
  max-width: 820px;
  margin: 0 auto;
}

.home-hero__eyebrow,
.home-section__eyebrow {
  margin: 0 0 var(--space-2);
  color: var(--color-primary);
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.home-hero h1 {
  margin: 0;
  max-width: 14ch;
  color: var(--color-text);
  font-size: clamp(2rem, 5vw, 3.5rem);
  line-height: 1.08;
  letter-spacing: -0.04em;
}

.home-hero__description {
  max-width: 62ch;
  margin: var(--space-5) 0 var(--space-8);
  color: var(--color-text-muted);
  font-size: 1.05rem;
}

.home-create-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  margin-top: var(--space-4);
  padding: var(--space-3) var(--space-4);
  border: 1px solid #fecaca;
  border-radius: var(--radius-sm);
  color: var(--color-danger);
  background: var(--color-danger-soft);
}

.home-create-error button,
.home-section__link {
  display: inline-flex;
  min-height: 44px;
  align-items: center;
  border: 0;
  border-radius: var(--radius-sm);
  padding: 0 var(--space-3);
  color: var(--color-primary);
  background: transparent;
  font-weight: 800;
  text-decoration: none;
}

.home-create-error button {
  flex: 0 0 auto;
  color: var(--color-danger);
}

.home-create-error button:hover,
.home-section__link:hover {
  background: var(--color-primary-soft);
}

.home-section {
  margin-top: var(--space-12);
  padding-top: var(--space-8);
  border-top: 1px solid var(--color-border);
}

.home-section__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  margin-bottom: var(--space-4);
}

.home-section h2 {
  margin: 0;
  font-size: 1.35rem;
}

.home-section__link--button {
  font: inherit;
}

.recent-projects,
.service-statuses {
  display: grid;
  gap: var(--space-3);
}

.recent-projects {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.recent-project-card {
  display: grid;
  min-height: 120px;
  grid-template-columns: auto 1fr;
  align-content: center;
  gap: var(--space-2) var(--space-3);
  padding: var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text);
  background: var(--color-surface);
  text-decoration: none;
}

.recent-project-card:hover {
  border-color: var(--color-primary);
}

.recent-project-card__name {
  min-width: 0;
  overflow: hidden;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recent-project-card__type {
  grid-column: 2;
  color: var(--color-text-muted);
  font-size: 0.75rem;
}

.recent-project-card--skeleton {
  min-height: 120px;
  border-color: transparent;
  background: var(--color-surface-subtle);
}

.service-statuses {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.service-status {
  display: flex;
  min-height: 72px;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
  background: var(--color-surface);
}

.service-status strong {
  display: block;
  color: var(--color-text);
}

.service-status--online {
  border-color: #bbf7d0;
  color: var(--color-success);
}

.service-status--offline {
  border-color: #fecaca;
  color: var(--color-danger);
}

.home-inline-note {
  margin: var(--space-3) 0 0;
  color: var(--color-text-muted);
  font-size: 0.88rem;
}

@media (max-width: 767px) {
  .home-page {
    padding: var(--space-6) 0;
  }

  .recent-projects,
  .service-statuses {
    grid-template-columns: 1fr;
  }

  .home-create-error,
  .home-section__header {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
