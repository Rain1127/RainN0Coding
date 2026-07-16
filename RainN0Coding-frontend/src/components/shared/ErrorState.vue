<script setup lang="ts">
import { ExclamationCircleOutlined } from '@ant-design/icons-vue'

defineProps<{
  title: string
  description: string
  retryable?: boolean
}>()

defineEmits<{
  retry: []
}>()
</script>

<template>
  <section class="state-panel state-panel--error" role="alert">
    <div class="state-panel__icon" aria-hidden="true">
      <ExclamationCircleOutlined />
    </div>
    <h2 class="state-panel__title">{{ title }}</h2>
    <p class="state-panel__description">{{ description }}</p>
    <button
      v-if="retryable"
      type="button"
      class="state-panel__action"
      @click="$emit('retry')"
    >
      重新加载
    </button>
  </section>
</template>
