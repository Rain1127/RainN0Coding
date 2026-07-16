import apiClient from './client'
import type { LoginUserVO, UserLoginRequest, UserRegisterRequest } from '@/types/user'

export const login = (body: UserLoginRequest) =>
  apiClient.post<any, LoginUserVO>('/user/login', body)

export const register = (body: UserRegisterRequest) =>
  apiClient.post<any, number>('/user/register', body)

export const logout = () =>
  apiClient.post<any, boolean>('/user/logout')

export const getLoginUser = () =>
  apiClient.get<any, LoginUserVO>('/user/get/login')
