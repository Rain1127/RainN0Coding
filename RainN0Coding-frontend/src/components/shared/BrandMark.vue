<script setup lang="ts">
withDefaults(defineProps<{
  tone?: 'default' | 'dark'
  compact?: boolean
}>(), {
  tone: 'default',
  compact: false,
})
</script>

<template>
  <span class="brand-mark" :class="{ 'brand-mark--dark': tone === 'dark' }">
    <span class="brand-mark__symbol" aria-hidden="true">RN</span>
    <span v-if="!compact" class="brand-mark__copy">
      <span class="brand-mark__name">RainN0Coding</span>
      <span class="brand-mark__tagline">AI 开发工作台</span>
    </span>
  </span>
</template>
