export interface LoginUserVO {
  id: number
  userAccount: string
  userName: string
  userAvatar: string
  userProfile: string
  userRole: 'user' | 'admin'
  createTime: string
  updateTime: string
}

export interface UserVO {
  id: number
  userAccount: string
  userName: string
  userAvatar: string
  userProfile: string
  userRole: 'user' | 'admin'
  createTime: string
}

export interface UserLoginRequest {
  userAccount: string
  userPassword: string
}

export interface UserRegisterRequest {
  userAccount: string
  userPassword: string
  checkPassword: string
}

export interface UserAddRequest {
  userName: string
  userAccount: string
  userAvatar?: string
  userProfile?: string
  userRole: string
}

export interface UserUpdateRequest {
  id: number
  userName?: string
  userAvatar?: string
  userProfile?: string
  userRole?: string
}

export interface UserQueryRequest {
  pageNum: number
  pageSize: number
  sortField?: string
  sortOrder?: string
  id?: number
  userName?: string
  userAccount?: string
  userProfile?: string
  userRole?: string
}
