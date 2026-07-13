<template>
  <div class="flex items-center justify-center py-8">
    <a-spin :size="size" />
    <span v-if="text" class="ml-3 text-sm text-gpt-text-muted">{{ text }}</span>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  size?: 'small' | 'default' | 'large'
  text?: string
}>()
</script>
