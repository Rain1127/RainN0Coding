<script setup lang="ts">
import { useId } from 'vue'
import { InboxOutlined } from '@ant-design/icons-vue'

defineProps<{
  title: string
  description?: string
}>()

const titleId = useId()
</script>

<template>
  <section class="state-panel" :aria-labelledby="titleId">
    <div class="state-panel__icon" aria-hidden="true">
      <InboxOutlined />
    </div>
    <h2 :id="titleId" class="state-panel__title">{{ title }}</h2>
    <p v-if="description" class="state-panel__description">{{ description }}</p>
    <div v-if="$slots.default" class="state-panel__actions">
      <slot />
    </div>
  </section>
</template>
