<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const missingPath = computed(() => {
  try { return decodeURIComponent(route.fullPath) } catch { return route.fullPath }
})
</script>

<template>
  <main class="error-page">
    <section class="error-card" aria-labelledby="not-found-title">
      <p class="error-code" aria-hidden="true">404</p>
      <h1 id="not-found-title">404 · 页面不存在</h1>
      <p>没有找到你请求的路径：</p>
      <code class="missing-path">{{ missingPath }}</code>
      <router-link class="home-link" to="/">返回首页</router-link>
    </section>
  </main>
</template>

<style scoped>
.error-page{display:grid;min-height:100dvh;place-items:center;padding:var(--space-5);background:var(--color-bg)}.error-card{width:min(100%,620px);border:1px solid var(--color-border);border-radius:var(--radius-lg);padding:clamp(32px,7vw,72px);background:var(--color-surface);box-shadow:var(--shadow-card);text-align:center}.error-code{margin:0;color:var(--color-primary);font-family:var(--font-mono);font-size:clamp(3.5rem,12vw,7rem);font-weight:900;line-height:1}.error-card h1{margin:var(--space-4) 0 0;font-size:clamp(1.5rem,4vw,2.25rem)}.error-card>p:not(.error-code){margin:var(--space-3) auto 0;color:var(--color-text-muted)}.missing-path{display:block;max-width:100%;margin:var(--space-3) auto 0;border-radius:var(--radius-sm);padding:var(--space-3);overflow-wrap:anywhere;color:var(--color-text);background:var(--color-surface-subtle);font-family:var(--font-mono)}.home-link{display:inline-flex;min-height:44px;align-items:center;margin-top:var(--space-6);border-radius:var(--radius-sm);padding:0 var(--space-5);color:#fff;background:var(--color-primary);font-weight:800;text-decoration:none}
</style>
