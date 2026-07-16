<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AdminLayout from '@/layouts/AdminLayout.vue'
import PageHeader from '@/components/shared/PageHeader.vue'
import { listUsers, updateUser } from '@/api/user'
import { useAuthStore } from '@/stores/auth'
import type { UserVO } from '@/types/user'
import { buildAdminListQuery, isCanonicalAdminListQuery, parseAdminListQuery } from '@/utils/adminListQuery'
import { formatDateTime, formatInteger } from '@/utils/formatters'
import { normalizePageResult } from '@/utils/pageResult'
import type { EntityId } from '@/types/entity'
import { sameEntityId } from '@/utils/entityId'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const users = ref<UserVO[]>([])
const searchAccount = ref('')
const roleFilter = ref<'' | 'user' | 'admin'>('')
const currentPage = ref(1)
const pageSize = ref(10)
const total = ref(0)
const serverPages = ref(1)
const loading = ref(false)
const loadError = ref('')
const actionError = ref('')
const feedback = ref('')
const updatingRoles = ref(new Set<EntityId>())
const roleOverrides = ref(new Map<EntityId, UserVO['userRole']>())
const roleSequences = new Map<EntityId, number>()
let requestSequence = 0

const totalPages = computed(() => Math.max(1, serverPages.value || Math.ceil(total.value / pageSize.value)))

watch(
  () => route.query,
  (query) => {
    const state = parseAdminListQuery(query, true)
    currentPage.value = state.page
    pageSize.value = state.pageSize
    searchAccount.value = state.search
    roleFilter.value = state.role ?? ''
    const canonical = buildAdminListQuery(state)
    if (!isCanonicalAdminListQuery(query, canonical)) {
      void router.replace({ query: canonical })
      return
    }
    void fetchUsers()
  },
  { deep: true, immediate: true },
)

async function fetchUsers() {
  const sequence = ++requestSequence
  const requestedPage = currentPage.value
  loading.value = true
  loadError.value = ''
  try {
    const result = await listUsers({
      pageNum: requestedPage,
      pageSize: pageSize.value,
      userAccount: searchAccount.value.trim() || undefined,
      userRole: roleFilter.value || undefined,
      sortField: 'createTime',
      sortOrder: 'descend',
    })
    if (sequence !== requestSequence) return
    const page = normalizePageResult(result, requestedPage, pageSize.value)
    const records = page.records
    const resultTotal = page.total
    const pages = page.pages
    total.value = resultTotal
    serverPages.value = pages
    if (records.length === 0 && resultTotal > 0 && requestedPage > pages) {
      updateRoute({ page: pages })
      return
    }
    users.value = records
    currentPage.value = Math.min(pages, page.current)
  } catch {
    if (sequence !== requestSequence) return
    users.value = []
    total.value = 0
    serverPages.value = 1
    loadError.value = '用户列表加载失败，请检查网络后重试。'
  } finally {
    if (sequence === requestSequence) loading.value = false
  }
}

function searchUsers() {
  updateRoute({ page: 1, search: searchAccount.value.trim(), role: roleFilter.value })
}

function changePage(next: number) {
  if (next < 1 || next > totalPages.value || next === currentPage.value) return
  updateRoute({ page: next })
}

function changePageSize(event: Event) {
  updateRoute({ page: 1, pageSize: Number((event.target as HTMLSelectElement).value) })
}

function changeRoleFilter(event: Event) {
  updateRoute({ page: 1, role: (event.target as HTMLSelectElement).value as '' | 'user' | 'admin' })
}

function updateRoute(patch: Partial<{ page: number; pageSize: number; search: string; role: '' | 'user' | 'admin' }>) {
  const state = {
    page: patch.page ?? currentPage.value,
    pageSize: patch.pageSize ?? pageSize.value,
    search: patch.search ?? searchAccount.value.trim(),
    role: patch.role ?? roleFilter.value,
  }
  const query = buildAdminListQuery(state)
  if (isCanonicalAdminListQuery(route.query, query)) void fetchUsers()
  else void router.replace({ query })
}

async function changeRole(user: UserVO, event: Event) {
  const role = (event.target as HTMLSelectElement).value as UserVO['userRole']
  const userId = user.id
  if (sameEntityId(userId, auth.userId) || role === displayRole(user) || updatingRoles.value.has(userId)) return
  const sequence = (roleSequences.get(userId) ?? 0) + 1
  roleSequences.set(userId, sequence)
  updatingRoles.value = new Set(updatingRoles.value).add(user.id)
  roleOverrides.value = new Map(roleOverrides.value).set(userId, role)
  actionError.value = ''
  feedback.value = ''
  try {
    const updated = await updateUser({ id: userId, userRole: role })
    if (sequence !== roleSequences.get(userId)) return
    if (!updated) throw new Error('update rejected')
    const currentUser = users.value.find(item => sameEntityId(item.id, userId))
    if (currentUser) currentUser.userRole = role
    feedback.value = `已将 ${currentUser?.userName || currentUser?.userAccount || `用户 #${userId}`} 的角色更新为 ${role}。`
  } catch {
    if (sequence !== roleSequences.get(userId)) return
    actionError.value = '角色更新失败，账号信息未被移除，请稍后重试。'
  } finally {
    if (sequence !== roleSequences.get(userId)) return
    const next = new Set(updatingRoles.value)
    next.delete(userId)
    updatingRoles.value = next
    const overrides = new Map(roleOverrides.value)
    overrides.delete(userId)
    roleOverrides.value = overrides
  }
}

function displayRole(user: UserVO) {
  return roleOverrides.value.get(user.id) ?? user.userRole
}
</script>

<template>
  <AdminLayout>
    <PageHeader title="用户管理" description="查看平台账号并安全调整访问角色。" eyebrow="Administration">
      <template #actions><button type="button" class="secondary-button" :disabled="loading" @click="fetchUsers">刷新</button></template>
    </PageHeader>

    <section class="admin-card admin-toolbar" aria-label="用户筛选">
      <label class="field-label" for="user-account-search">用户账号</label>
      <div class="search-row">
        <input id="user-account-search" v-model="searchAccount" name="user-account-search" autocomplete="off" aria-label="搜索用户账号" type="search" placeholder="例如：operator_01…" @keyup.enter="searchUsers">
        <select name="user-role-filter" autocomplete="off" :value="roleFilter" aria-label="用户角色筛选" @change="changeRoleFilter">
          <option value="">全部角色</option><option value="user">普通用户</option><option value="admin">管理员</option>
        </select>
        <button type="button" class="primary-button" data-action="search-users" @click="searchUsers">搜索</button>
      </div>
    </section>

    <p v-if="feedback" class="inline-feedback" role="status">{{ feedback }}</p>
    <p v-if="actionError" class="inline-alert" role="alert">{{ actionError }}</p>

    <section class="admin-card" aria-labelledby="users-title">
      <div class="section-heading"><div><h2 id="users-title">平台用户</h2><p class="tabular-nums">共 {{ formatInteger(total) }} 个账号</p></div></div>
      <div v-if="loading" class="admin-state" role="status">正在加载用户…</div>
      <div v-else-if="loadError" class="admin-state" role="alert">
        <strong>加载失败</strong><span>{{ loadError }}</span>
        <button type="button" class="secondary-button" data-action="retry-users" @click="fetchUsers">重新加载</button>
      </div>
      <div v-else-if="users.length === 0" class="admin-state"><strong>没有找到用户</strong><span>尝试更换账号关键词。</span></div>
      <template v-else-if="users.length > 0">
        <div class="admin-table-scroll" tabindex="0" aria-label="用户表格，可横向滚动">
          <table>
            <thead><tr><th>账号</th><th>姓名</th><th>角色</th><th>简介</th><th>创建时间</th></tr></thead>
            <tbody>
              <tr v-for="user in users" :key="user.id" :data-user-id="user.id">
                <td><strong>{{ user.userAccount }}</strong><span v-if="sameEntityId(user.id, auth.userId)" class="current-badge">当前账号</span></td>
                <td>{{ user.userName || '未设置' }}</td>
                <td>
                  <select
                    :name="`user-role-${user.id}`"
                    autocomplete="off"
                    :value="displayRole(user)"
                    :aria-label="`调整 ${user.userAccount} 的角色`"
                    data-action="change-role"
                    :disabled="sameEntityId(user.id, auth.userId) || updatingRoles.has(user.id)"
                    @change="changeRole(user, $event)"
                  >
                    <option value="user">普通用户</option><option value="admin">管理员</option>
                  </select>
                </td>
                <td>{{ user.userProfile || '—' }}</td><td class="tabular-nums">{{ formatDateTime(user.createTime) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
        <div v-if="!loading && !loadError && total > 0" class="pagination" aria-label="用户分页">
          <label>每页 <select name="user-page-size" autocomplete="off" :value="pageSize" aria-label="每页用户数" @change="changePageSize"><option :value="10">10</option><option :value="20">20</option><option :value="50">50</option></select></label>
          <button type="button" :disabled="currentPage === 1" @click="changePage(currentPage - 1)">上一页</button>
          <span class="tabular-nums">第 {{ formatInteger(currentPage) }} / {{ formatInteger(totalPages) }} 页</span>
          <button type="button" :disabled="currentPage >= totalPages" @click="changePage(currentPage + 1)">下一页</button>
        </div>
    </section>
  </AdminLayout>
</template>

<style scoped>
.admin-card{margin-bottom:var(--space-5);border:1px solid var(--color-border);border-radius:var(--radius-lg);background:var(--color-surface);box-shadow:var(--shadow-card)}.admin-toolbar{padding:var(--space-5)}.field-label{display:block;margin-bottom:var(--space-2);font-weight:700}.search-row{display:flex;max-width:620px;gap:var(--space-2)}
input,select{min-height:44px;border:1px solid var(--color-border);border-radius:var(--radius-sm);padding:0 var(--space-3);color:var(--color-text);background:#fff}input{min-width:0;flex:1}.primary-button,.secondary-button{min-height:44px;border-radius:var(--radius-sm);padding:0 var(--space-4);font-weight:700}.primary-button{border:1px solid var(--color-primary);color:#fff;background:var(--color-primary)}.secondary-button{border:1px solid var(--color-border);background:#fff}
.inline-feedback,.inline-alert{margin:0 0 var(--space-4);border-radius:var(--radius-sm);padding:var(--space-3) var(--space-4)}.inline-feedback{color:#166534;background:#ecfdf3}.inline-alert{color:#991b1b;background:var(--color-danger-soft)}.section-heading{padding:var(--space-5);border-bottom:1px solid var(--color-border)}.section-heading h2,.section-heading p{margin:0}.section-heading p{margin-top:var(--space-1);color:var(--color-text-muted)}
.admin-state{display:flex;min-height:240px;align-items:center;justify-content:center;flex-direction:column;gap:var(--space-2);padding:var(--space-6);text-align:center}.admin-state span{color:var(--color-text-muted)}.admin-table-scroll{max-width:100%;overflow-x:auto}table{width:100%;min-width:780px;border-collapse:collapse}th,td{padding:var(--space-3) var(--space-4);border-bottom:1px solid var(--color-border);text-align:left;vertical-align:middle}th{color:var(--color-text-muted);background:var(--color-surface-subtle);font-size:.8rem;letter-spacing:.04em;text-transform:uppercase}.tabular-nums{font-variant-numeric:tabular-nums}.current-badge{margin-left:var(--space-2);border-radius:999px;padding:.2rem .5rem;color:var(--color-primary);background:var(--color-primary-soft);font-size:.75rem;font-weight:700}.pagination{display:flex;align-items:center;justify-content:flex-end;gap:var(--space-3);padding:var(--space-4)}.pagination button{min-height:44px;border:1px solid var(--color-border);border-radius:var(--radius-sm);padding:0 var(--space-3);background:#fff}
@media(max-width:640px){.search-row{flex-direction:column}.pagination{justify-content:flex-start}}
</style>
