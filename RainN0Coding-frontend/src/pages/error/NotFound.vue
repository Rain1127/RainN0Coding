<template>
  <div class="flex items-center justify-center h-full bg-gpt-bg">
    <div class="text-center">
      <h1 class="text-6xl font-bold text-gpt-accent mb-4">404</h1>
      <p class="text-lg text-gpt-text-muted mb-6">页面不存在</p>
      <a-button type="primary" @click="$router.push('/')">返回首页</a-button>
    </div>
  </div>
</template>
