<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import type { Message } from "../types";
const props = defineProps<{ messages: Message[]; activeId: string | null }>();
const emit = defineEmits<{ jump: [id: string]; close: [] }>();
const close = ref<HTMLButtonElement | null>(null);
const rounds = computed(() => props.messages.filter((m) => m.role === "user"));
function preview(content: string) {
  const text = content.replace(/\s+/g, " ").trim();
  const chars = Array.from(text);
  return chars.length > 64 ? chars.slice(0, 64).join("") + "…" : text;
}
onMounted(() => close.value?.focus({ preventScroll: true }));
</script>
<template>
  <section
    class="conversation-locator"
    role="dialog"
    aria-label="对话定位"
    @keydown.esc.stop="emit('close')"
  >
    <header class="locator-heading">
      <div>
        <strong>对话定位</strong
        ><small>{{ rounds.length }} 轮对话 · 点击问题跳转</small>
      </div>
      <button
        ref="close"
        class="icon"
        aria-label="关闭对话定位"
        @click="emit('close')"
      >
        ×
      </button>
    </header>
    <nav class="conversation-list" aria-label="历史问题目录">
      <p v-if="!rounds.length" class="muted">尚无已保存的用户问题。</p>
      <button
        v-for="(message, index) in rounds"
        :key="message.id"
        :title="message.content"
        :aria-current="activeId === message.id ? 'true' : undefined"
        :class="{ selected: activeId === message.id }"
        :data-target-id="message.id"
        @click="emit('jump', message.id)"
      >
        <span class="round-number">{{ index + 1 }}</span><span
          class="round-preview"
          >{{ preview(message.content) }}</span
        >
      </button>
    </nav>
  </section>
</template>
