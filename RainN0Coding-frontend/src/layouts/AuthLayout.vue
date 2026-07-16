<script setup lang="ts">
import BrandMark from '@/components/shared/BrandMark.vue'
</script>

<template>
  <div class="auth-shell">
    <a class="skip-link" href="#main-content">跳到主要内容</a>
    <aside class="auth-shell__brand-panel" aria-label="产品介绍">
      <BrandMark tone="dark" />
      <div class="auth-shell__pitch">
        <p class="auth-shell__eyebrow">从想法到可运行应用</p>
        <p class="auth-shell__title">让多个 AI 角色协作完成你的下一次构建</p>
        <p class="auth-shell__description">
          描述需求，RainN0Coding 会完成产品分析、架构、编码、审查与构建，并保留清晰的生成过程。
        </p>
      </div>
      <p class="auth-shell__description">Vue · Spring Boot · LangGraph</p>
    </aside>
    <main id="main-content" class="auth-shell__main" tabindex="-1">
      <slot />
    </main>
  </div>
</template>
