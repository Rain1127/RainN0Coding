<template>
  <div class="flex items-center justify-center h-full bg-gpt-bg">
    <div class="text-center">
      <h1 class="text-6xl font-bold text-red-500 mb-4">403</h1>
      <p class="text-lg text-gpt-text-muted mb-6">无权限访问此页面</p>
      <a-button type="primary" @click="$router.push('/')">返回首页</a-button>
    </div>
  </div>
</template>
