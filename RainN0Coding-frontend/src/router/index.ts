import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/pages/auth/LoginPage.vue'),
      meta: { guest: true },
    },
    {
      path: '/register',
      name: 'Register',
      component: () => import('@/pages/auth/RegisterPage.vue'),
      meta: { guest: true },
    },
    {
      path: '/',
      name: 'ChatHome',
      component: () => import('@/pages/chat/ChatHome.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/chat/:appId',
      name: 'ChatDetail',
      component: () => import('@/pages/chat/ChatDetail.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/admin/apps',
      name: 'AdminApps',
      component: () => import('@/pages/admin/AppManagement.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/admin/apps/:appId',
      name: 'AdminAppDetail',
      component: () => import('@/pages/admin/AppDetailAdmin.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/admin/users',
      name: 'AdminUsers',
      component: () => import('@/pages/admin/UserManagement.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/admin/intent-tree',
      name: 'IntentTreeConfig',
      component: () => import('@/pages/admin/IntentTreeConfig.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/403',
      name: 'Forbidden',
      component: () => import('@/pages/error/Forbidden.vue'),
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'NotFound',
      component: () => import('@/pages/error/NotFound.vue'),
    },
  ],
})

router.beforeEach(async (to, _from, next) => {
  const auth = useAuthStore()
  if (!auth.initialized) {
    await auth.fetchCurrentUser()
  }

  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return next({ name: 'Login', query: { redirect: to.fullPath } })
  }
  if (to.meta.guest && auth.isAuthenticated) {
    return next({ name: 'ChatHome' })
  }
  if (to.meta.requiresAdmin && !auth.isAdmin) {
    return next({ name: 'Forbidden' })
  }
  next()
})

export default router
