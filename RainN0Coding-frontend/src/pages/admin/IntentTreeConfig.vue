<template>
  <AdminLayout>
    <a-breadcrumb class="mb-4">
      <a-breadcrumb-item>首页</a-breadcrumb-item>
      <a-breadcrumb-item>意图树配置</a-breadcrumb-item>
    </a-breadcrumb>
    <div class="flex items-center justify-between mb-4">
      <div>
        <h1 class="text-xl font-semibold text-gpt-text">意图树配置</h1>
        <p class="text-sm text-gpt-text-muted">配置意图层级、类型和节点关系</p>
      </div>
      <div class="flex items-center gap-2">
        <a-button @click="handleReset">重置默认</a-button>
        <a-button type="primary" @click="handleSave">保存</a-button>
      </div>
    </div>

    <div class="flex gap-4">
      <!-- Tree Panel -->
      <div class="w-[360px] bg-white rounded-lg border border-gray-200 p-4 shrink-0">
        <h3 class="text-sm font-medium text-gpt-text mb-3">意图树结构</h3>
        <div v-if="treeError" class="text-sm text-red-500">{{ treeError }}</div>
        <a-spin v-else-if="treeLoading" class="flex justify-center py-8" />
        <div v-else-if="!treeJson" class="text-sm text-gpt-text-muted text-center py-8">
          暂无数据，请先创建意图树
        </div>
        <a-tree
          v-else
          :tree-data="treeData"
          :default-expand-all="true"
          :selected-keys="selectedKeys"
          @select="handleSelect"
        />
      </div>

      <!-- Detail Panel -->
      <div class="flex-1 bg-white rounded-lg border border-gray-200 p-4">
        <template v-if="selectedNode">
          <div class="flex items-center justify-between mb-4">
            <div class="flex items-center gap-2">
              <h2 class="text-lg font-semibold">{{ selectedNode.title }}</h2>
              <a-tag v-if="selectedNode.type" color="purple">{{ selectedNode.type }}</a-tag>
              <a-tag v-if="selectedNode.enabled !== false" color="green">启用</a-tag>
              <a-tag v-else color="red">禁用</a-tag>
            </div>
            <div class="flex gap-1">
              <a-button type="primary" size="small" @click="handleAddChild">新建子节点</a-button>
              <a-button size="small" @click="handleEditNode">编辑</a-button>
              <a-button size="small" danger @click="handleDeleteNode">删除</a-button>
            </div>
          </div>
          <div class="text-sm space-y-2">
            <div><span class="text-gpt-text-muted">Key:</span> {{ selectedNode.key }}</div>
            <div v-if="selectedNode.source"><span class="text-gpt-text-muted">来源:</span> {{ selectedNode.source }}</div>
            <div v-if="selectedNode.collection"><span class="text-gpt-text-muted">Collection:</span> {{ selectedNode.collection }}</div>
            <div><span class="text-gpt-text-muted">描述:</span> {{ selectedNode.description || '暂无描述' }}</div>
            <div><span class="text-gpt-text-muted">示例问题:</span> {{ selectedNode.examples?.join(', ') || '暂无示例' }}</div>
          </div>
        </template>
        <div v-else class="text-sm text-gpt-text-muted text-center py-12">
          点击左侧节点查看详情
        </div>
      </div>
    </div>
  </AdminLayout>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import AdminLayout from '@/layouts/AdminLayout.vue'
import { getIntentTree, saveIntentTree, resetIntentTree } from '@/api/intentConfig'
import type { IntentNode } from '@/types/intent'

const treeLoading = ref(false)
const treeError = ref<string | null>(null)
const treeJson = ref<string>('')
const treeData = ref<IntentNode[]>([])
const selectedKeys = ref<string[]>([])
const selectedNode = ref<IntentNode | null>(null)

onMounted(() => fetchTree())

async function fetchTree() {
  treeLoading.value = true
  treeError.value = null
  try {
    const res = await getIntentTree()
    treeJson.value = res.treeJson
    const root = JSON.parse(res.treeJson) as IntentNode[]
    treeData.value = root
  } catch (e: any) {
    treeError.value = e.message || '加载失败'
  } finally {
    treeLoading.value = false
  }
}

function handleSelect(keys: string[], _e: any) {
  selectedKeys.value = keys
  if (keys.length && treeData.value.length) {
    selectedNode.value = findNode(treeData.value, keys[0])
  }
}

function findNode(nodes: IntentNode[], key: string): IntentNode | null {
  for (const node of nodes) {
    if (node.key === key) return node
    if (node.children?.length) {
      const found = findNode(node.children, key)
      if (found) return found
    }
  }
  return null
}

async function handleSave() {
  await saveIntentTree(treeJson.value)
  message.success('保存成功')
}

async function handleReset() {
  await resetIntentTree()
  message.success('已重置')
  fetchTree()
}

function handleAddChild() {
  message.info('请编辑 JSON 添加节点')
}

function handleEditNode() {
  message.info('请编辑 JSON 修改节点')
}

function handleDeleteNode() {
  message.info('请编辑 JSON 删除节点')
}
</script>
