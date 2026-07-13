import axios from 'axios'
import { message } from 'ant-design-vue'
import type { BaseResponse } from '@/types/api'
import { buildLoginRedirect, shouldRedirectToLogin } from '@/router/guards'

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE,
  withCredentials: true,
  timeout: 60000,
  headers: { 'Content-Type': 'application/json' },
})

apiClient.interceptors.response.use(
  (res) => {
    const body = res.data as BaseResponse
    if (body.code !== 0) {
      message.error(body.message || '请求失败')
      return Promise.reject(new Error(body.message))
    }
    return body.data as any
  },
  (err) => {
    if (err.response?.status === 401) {
      const { pathname, search } = window.location
      if (shouldRedirectToLogin(pathname)) {
        window.location.assign(buildLoginRedirect(pathname, search))
      }
    } else if (err.code === 'ECONNABORTED') {
      message.error('请求超时，请稍后重试')
    } else if (!err.response) {
      message.error('网络异常，请检查连接')
    } else {
      const msg = err.response?.data?.message || '请求失败'
      message.error(msg)
    }
    return Promise.reject(err)
  }
)

export default apiClient
