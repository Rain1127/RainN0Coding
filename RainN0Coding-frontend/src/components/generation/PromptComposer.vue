<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowUpOutlined } from '@ant-design/icons-vue'

export interface PromptExample {
  title: string
  prompt: string
  description?: string
}

const props = withDefaults(defineProps<{
  examples?: PromptExample[]
  loading?: boolean
}>(), {
  examples: () => [],
  loading: false,
})

const emit = defineEmits<{
  submit: [prompt: string]
}>()

const prompt = ref('')
const composing = ref(false)
const canSubmit = computed(() => !props.loading && prompt.value.trim().length > 0)

function submit() {
  if (!canSubmit.value) return
  emit('submit', prompt.value.trim())
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key !== 'Enter' || (!event.ctrlKey && !event.metaKey) || composing.value || event.isComposing) {
    return
  }
  event.preventDefault()
  submit()
}

function selectExample(example: PromptExample) {
  if (props.loading) return
  prompt.value = example.prompt
}
</script>

<template>
  <form class="prompt-composer" :aria-busy="loading" @submit.prevent="submit">
    <label for="generation-prompt" class="prompt-composer__label">描述你想构建的应用</label>
    <p id="prompt-description" class="prompt-composer__description">
      说明核心页面、用户和功能。按 Ctrl + Enter 或 Command + Enter 提交。
    </p>
    <div class="prompt-composer__field">
      <textarea
        id="generation-prompt"
        v-model="prompt"
        name="prompt"
        rows="5"
        maxlength="4000"
        autocomplete="off"
        required
        :disabled="loading"
        aria-describedby="prompt-description"
        placeholder="例如：创建一个项目管理看板，支持任务分组、负责人筛选和进度统计…"
        @compositionstart="composing = true"
        @compositionend="composing = false"
        @keydown="handleKeydown"
      />
      <button
        type="submit"
        class="prompt-composer__submit"
        :disabled="!canSubmit"
      >
        <ArrowUpOutlined aria-hidden="true" />
        <span>{{ loading ? '正在创建项目…' : '开始生成' }}</span>
      </button>
    </div>

    <div v-if="examples.length" class="prompt-composer__examples" aria-label="提示词示例">
      <p class="prompt-composer__examples-label">从示例开始</p>
      <div class="prompt-composer__example-grid">
        <button
          v-for="example in examples"
          :key="example.title"
          type="button"
          class="prompt-composer__example"
          :data-example="example.title"
          :disabled="loading"
          @click="selectExample(example)"
        >
          <span class="prompt-composer__example-title">{{ example.title }}</span>
          <span v-if="example.description" class="prompt-composer__example-description">
            {{ example.description }}
          </span>
        </button>
      </div>
    </div>
  </form>
</template>

<style scoped>
.prompt-composer {
  width: 100%;
}

.prompt-composer__label {
  display: block;
  margin-bottom: var(--space-2);
  color: var(--color-text);
  font-size: 1rem;
  font-weight: 800;
}

.prompt-composer__description {
  margin: 0 0 var(--space-4);
  color: var(--color-text-muted);
  font-size: 0.9rem;
}

.prompt-composer__field {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  box-shadow: var(--shadow-card);
}

.prompt-composer textarea {
  width: 100%;
  min-height: 132px;
  border: 0;
  padding: var(--space-2);
  color: var(--color-text);
  background: transparent;
  line-height: 1.6;
  resize: vertical;
}

.prompt-composer__field:focus-within {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgb(79 70 229 / 16%), var(--shadow-card);
}

.prompt-composer__submit {
  display: inline-flex;
  min-height: 44px;
  align-items: center;
  justify-content: center;
  justify-self: end;
  gap: var(--space-2);
  border: 0;
  border-radius: var(--radius-sm);
  padding: 0 var(--space-5);
  color: #ffffff;
  background: var(--color-primary);
  font-weight: 800;
}

.prompt-composer__submit:not(:disabled):hover {
  background: var(--color-primary-hover);
}

.prompt-composer__examples {
  margin-top: var(--space-6);
}

.prompt-composer__examples-label {
  margin: 0 0 var(--space-3);
  color: var(--color-text-muted);
  font-size: 0.85rem;
  font-weight: 700;
}

.prompt-composer__example-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-3);
}

.prompt-composer__example {
  min-height: 76px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4);
  color: var(--color-text);
  background: var(--color-surface);
  text-align: left;
}

.prompt-composer__example:not(:disabled):hover {
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
}

.prompt-composer__example-title,
.prompt-composer__example-description {
  display: block;
}

.prompt-composer__example-title {
  font-weight: 800;
}

.prompt-composer__example-description {
  margin-top: var(--space-1);
  color: var(--color-text-muted);
  font-size: 0.8rem;
}

@media (max-width: 767px) {
  .prompt-composer__example-grid {
    grid-template-columns: 1fr;
  }

  .prompt-composer__submit {
    width: 100%;
  }
}
</style>
