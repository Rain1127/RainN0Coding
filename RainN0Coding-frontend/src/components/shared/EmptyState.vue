<template>
  <div class="flex flex-col items-center justify-center py-12 text-center">
    <div class="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mb-4">
      <InboxOutlined class="text-2xl text-gpt-text-muted" />
    </div>
    <h3 class="text-base font-medium text-gpt-text mb-1">{{ title }}</h3>
    <p class="text-sm text-gpt-text-muted max-w-xs">{{ description }}</p>
    <slot />
  </div>
</template>

<script setup lang="ts">
import { InboxOutlined } from '@ant-design/icons-vue'

defineProps<{
  title: string
  description?: string
}>()
</script>
