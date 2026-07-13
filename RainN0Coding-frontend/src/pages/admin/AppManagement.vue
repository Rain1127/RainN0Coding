<template>
  <AdminLayout>
    <a-breadcrumb class="mb-4">
      <a-breadcrumb-item>首页</a-breadcrumb-item>
      <a-breadcrumb-item>应用管理</a-breadcrumb-item>
    </a-breadcrumb>
    <div class="flex items-center justify-between mb-4">
      <div>
        <h1 class="text-xl font-semibold text-gpt-text">应用管理</h1>
        <p class="text-sm text-gpt-text-muted">管理所有应用及其状态</p>
      </div>
      <div class="flex items-center gap-3">
        <a-input-search v-model:value="searchName" placeholder="搜索应用名称" @search="handleSearch" style="width: 220px" />
        <a-button @click="fetchData">刷新</a-button>
      </div>
    </div>

    <!-- Stats -->
    <div class="grid grid-cols-4 gap-4 mb-6">
      <div v-for="stat in stats" :key="stat.label" class="bg-white rounded-lg p-4 border border-gray-200">
        <div class="text-sm text-gpt-text-muted">{{ stat.label }}</div>
        <div class="text-2xl font-semibold text-gpt-text mt-1">{{ stat.value }}</div>
      </div>
    </div>

    <!-- Table -->
    <div class="bg-white rounded-lg border border-gray-200">
      <a-table :columns="columns" :data-source="appList" :loading="loading" :pagination="pagination" row-key="id" @change="handleTableChange">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'appName'">
            <a @click="$router.push(`/admin/apps/${record.id}`)">{{ record.appName || '未命名' }}</a>
          </template>
          <template v-if="column.key === 'codeGenType'">
            <a-tag>{{ record.codeGenType }}</a-tag>
          </template>
          <template v-if="column.key === 'priority'">
            <a-tag v-if="record.priority === 99" color="green">精选</a-tag>
            <span v-else>{{ record.priority }}</span>
          </template>
          <template v-if="column.key === 'action'">
            <a-button type="link" size="small" @click="handleDeploy(record)">部署</a-button>
            <a-button type="link" size="small" @click="handleDownload(record)">下载</a-button>
            <a-popconfirm title="确认删除?" @confirm="handleDelete(record.id)">
              <a-button type="link" size="small" danger>删除</a-button>
            </a-popconfirm>
          </template>
        </template>
      </a-table>
    </div>
  </AdminLayout>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import AdminLayout from '@/layouts/AdminLayout.vue'
import { adminListApps, adminDeleteApp, deployApp, downloadApp } from '@/api/app'
import type { AppVO } from '@/types/app'

const searchName = ref('')
const appList = ref<AppVO[]>([])
const loading = ref(false)
const pagination = reactive({ current: 1, pageSize: 10, total: 0 })

const stats = computed(() => [
  { label: '应用总数', value: pagination.total },
  { label: '精选应用', value: appList.value.filter(a => a.priority === 99).length },
  { label: '已部署', value: appList.value.filter(a => a.deployKey).length },
  { label: '语言类型', value: new Set(appList.value.map(a => a.codeGenType)).size },
])

const columns = [
  { title: '名称', key: 'appName', dataIndex: 'appName' },
  { title: '类型', key: 'codeGenType', dataIndex: 'codeGenType', width: 100 },
  { title: 'DeployKey', dataIndex: 'deployKey', ellipsis: true, width: 120 },
  { title: '优先级', key: 'priority', dataIndex: 'priority', width: 80 },
  { title: '创建时间', dataIndex: 'createTime', width: 180 },
  { title: '操作', key: 'action', width: 200 },
]

onMounted(() => fetchData())

async function fetchData() {
  loading.value = true
  try {
    const res = await adminListApps({
      pageNum: pagination.current,
      pageSize: pagination.pageSize,
      appName: searchName.value || undefined,
      sortField: 'createTime',
      sortOrder: 'descend',
    })
    appList.value = res.records
    pagination.total = res.total
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  pagination.current = 1
  fetchData()
}

function handleTableChange(pag: { current: number; pageSize: number }) {
  pagination.current = pag.current
  pagination.pageSize = pag.pageSize
  fetchData()
}

async function handleDelete(id: number) {
  await adminDeleteApp({ id })
  message.success('已删除')
  fetchData()
}

async function handleDeploy(record: AppVO) {
  try {
    const result = await deployApp(record.id)
    message.success(`部署成功: ${result.url}`)
  } catch { /* handled */ }
}

function handleDownload(record: AppVO) {
  window.open(downloadApp(record.id))
}
</script>
