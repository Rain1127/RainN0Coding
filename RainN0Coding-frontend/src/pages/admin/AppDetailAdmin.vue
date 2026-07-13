<template>
  <AdminLayout>
    <a-breadcrumb class="mb-4">
      <a-breadcrumb-item>首页</a-breadcrumb-item>
      <a-breadcrumb-item><a @click="$router.push('/admin/apps')">应用管理</a></a-breadcrumb-item>
      <a-breadcrumb-item>{{ app?.appName || '应用详情' }}</a-breadcrumb-item>
    </a-breadcrumb>
    <div v-if="app" class="bg-white rounded-lg border border-gray-200 p-6">
      <h1 class="text-xl font-semibold text-gpt-text mb-6">{{ app.appName }}</h1>
      <div class="grid grid-cols-2 gap-4">
        <div><span class="text-gpt-text-muted">ID:</span> {{ app.id }}</div>
        <div><span class="text-gpt-text-muted">类型:</span> <a-tag>{{ app.codeGenType }}</a-tag></div>
        <div><span class="text-gpt-text-muted">DeployKey:</span> {{ app.deployKey || '未部署' }}</div>
        <div><span class="text-gpt-text-muted">优先级:</span> {{ app.priority }}</div>
        <div><span class="text-gpt-text-muted">创建时间:</span> {{ app.createTime }}</div>
        <div><span class="text-gpt-text-muted">更新时间:</span> {{ app.updateTime }}</div>
      </div>
      <div class="mt-4 flex gap-2">
        <a-button type="primary" @click="handleDeploy">部署</a-button>
        <a-button @click="handleDownload">下载代码</a-button>
      </div>
    </div>
  </AdminLayout>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import AdminLayout from '@/layouts/AdminLayout.vue'
import { adminGetAppVO, deployApp, downloadApp } from '@/api/app'
import type { AppVO } from '@/types/app'

const route = useRoute()
const app = ref<AppVO | null>(null)

onMounted(async () => {
  const appId = Number(route.params.appId)
  app.value = await adminGetAppVO(appId)
})

async function handleDeploy() {
  if (!app.value) return
  await deployApp(app.value.id)
  message.success('部署成功')
}

function handleDownload() {
  if (!app.value) return
  window.open(downloadApp(app.value.id))
}
</script>
