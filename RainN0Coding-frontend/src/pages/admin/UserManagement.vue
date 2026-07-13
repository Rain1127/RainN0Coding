<template>
  <AdminLayout>
    <a-breadcrumb class="mb-4">
      <a-breadcrumb-item>首页</a-breadcrumb-item>
      <a-breadcrumb-item>用户管理</a-breadcrumb-item>
    </a-breadcrumb>
    <div class="flex items-center justify-between mb-4">
      <div>
        <h1 class="text-xl font-semibold text-gpt-text">用户管理</h1>
        <p class="text-sm text-gpt-text-muted">管理系统用户</p>
      </div>
      <a-button type="primary" @click="showModal = true">新建用户</a-button>
    </div>

    <div class="bg-white rounded-lg border border-gray-200">
      <a-table :columns="columns" :data-source="userList" :loading="loading" :pagination="pagination" row-key="id" @change="handleTableChange">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'userRole'">
            <a-tag :color="record.userRole === 'admin' ? 'purple' : 'blue'">{{ record.userRole }}</a-tag>
          </template>
          <template v-if="column.key === 'action'">
            <a-button type="link" size="small" @click="handleEdit(record)">编辑</a-button>
            <a-popconfirm title="确认删除?" @confirm="handleDelete(record.id)">
              <a-button type="link" size="small" danger>删除</a-button>
            </a-popconfirm>
          </template>
        </template>
      </a-table>
    </div>

    <!-- Add/Edit Modal -->
    <a-modal v-model:open="showModal" :title="editingUser ? '编辑用户' : '新建用户'" @ok="handleSave" :confirm-loading="saving">
      <a-form layout="vertical">
        <a-form-item label="账号" required>
          <a-input v-model:value="form.userAccount" :disabled="!!editingUser" />
        </a-form-item>
        <a-form-item label="姓名" required>
          <a-input v-model:value="form.userName" />
        </a-form-item>
        <a-form-item label="角色" required>
          <a-select v-model:value="form.userRole">
            <a-select-option value="user">user</a-select-option>
            <a-select-option value="admin">admin</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="简介">
          <a-textarea v-model:value="form.userProfile" :rows="2" />
        </a-form-item>
      </a-form>
    </a-modal>
  </AdminLayout>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import AdminLayout from '@/layouts/AdminLayout.vue'
import { listUsers, addUser, updateUser, deleteUser } from '@/api/user'
import type { UserVO } from '@/types/user'

const userList = ref<UserVO[]>([])
const loading = ref(false)
const pagination = reactive({ current: 1, pageSize: 10, total: 0 })

const showModal = ref(false)
const saving = ref(false)
const editingUser = ref<UserVO | null>(null)
const form = reactive({ userAccount: '', userName: '', userRole: 'user', userProfile: '' })

const columns = [
  { title: '账号', dataIndex: 'userAccount' },
  { title: '姓名', dataIndex: 'userName' },
  { title: '角色', key: 'userRole', dataIndex: 'userRole', width: 100 },
  { title: '简介', dataIndex: 'userProfile', ellipsis: true },
  { title: '创建时间', dataIndex: 'createTime', width: 180 },
  { title: '操作', key: 'action', width: 150 },
]

onMounted(() => fetchData())

async function fetchData() {
  loading.value = true
  try {
    const res = await listUsers({ pageNum: pagination.current, pageSize: pagination.pageSize, sortField: 'createTime', sortOrder: 'descend' })
    userList.value = res.records
    pagination.total = res.total
  } finally {
    loading.value = false
  }
}

function handleTableChange(pag: { current: number; pageSize: number }) {
  pagination.current = pag.current
  pagination.pageSize = pag.pageSize
  fetchData()
}

function handleEdit(record: UserVO) {
  editingUser.value = record
  form.userAccount = record.userAccount
  form.userName = record.userName
  form.userRole = record.userRole
  form.userProfile = record.userProfile || ''
  showModal.value = true
}

async function handleSave() {
  saving.value = true
  try {
    if (editingUser.value) {
      await updateUser({ id: editingUser.value.id, userName: form.userName, userRole: form.userRole, userProfile: form.userProfile })
    } else {
      await addUser({ userAccount: form.userAccount, userName: form.userName, userRole: form.userRole, userProfile: form.userProfile })
    }
    showModal.value = false
    editingUser.value = null
    form.userAccount = form.userName = form.userProfile = ''
    form.userRole = 'user'
    fetchData()
  } finally {
    saving.value = false
  }
}

async function handleDelete(id: number) {
  await deleteUser({ id })
  message.success('已删除')
  fetchData()
}
</script>
