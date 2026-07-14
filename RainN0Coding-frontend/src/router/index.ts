import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { decideRouteAccess } from './guards'

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
      name: 'Home',
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
      path: '/projects',
      name: 'Projects',
      component: () => import('@/pages/projects/ProjectsPage.vue'),
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

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.initialized) {
    await auth.fetchCurrentUser()
  }

  return decideRouteAccess(to.meta, auth.isAuthenticated, auth.isAdmin, to.fullPath)
})

export default router
