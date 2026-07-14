<script setup lang="ts">
withDefaults(defineProps<{
  size?: 'small' | 'default' | 'large'
  text?: string
}>(), {
  size: 'default',
  text: '正在加载…',
})
</script>

<template>
  <div class="loading-state" role="status" aria-live="polite">
    <a-spin :size="size" aria-hidden="true" />
    <span class="loading-state__text">{{ text }}</span>
  </div>
</template>
