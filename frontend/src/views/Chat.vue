<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from "vue";
import type { ComponentPublicInstance } from "vue";
import type { Citation } from "../types";
import RecommendationPanel from "../components/RecommendationPanel.vue";
import MarkdownMessage from "../components/MarkdownMessage.vue";
import ConversationLocator from "../components/ConversationLocator.vue";
import { api } from "../api";
import { context, current, errorText, sendQuestion, state } from "../store";
const recommendationsOpen = ref(window.innerWidth >= 1100),
  viewport = ref<HTMLElement | null>(null),
  stick = ref(true),
  clearConfirm = ref(false);
const locatorOpen = ref(false),
  activeMessage = ref<string | null>(null),
  browsingHistory = ref(false);
const messageNodes = new Map<string, HTMLElement>();
const wideQuery = window.matchMedia("(min-width: 1100px)");
function keepPanelsSeparate() {
  if (!wideQuery.matches && locatorOpen.value)
    recommendationsOpen.value = false;
}
wideQuery.addEventListener("change", keepPanelsSeparate);
onBeforeUnmount(() =>
  wideQuery.removeEventListener("change", keepPanelsSeparate),
);
function messageRef(
  id: string,
  element: Element | ComponentPublicInstance | null,
) {
  if (element instanceof HTMLElement) messageNodes.set(id, element);
  else messageNodes.delete(id);
}
function toggleLocator() {
  locatorOpen.value = !locatorOpen.value;
  if (locatorOpen.value && window.innerWidth < 1100)
    recommendationsOpen.value = false;
}
function openRecommendations() {
  locatorOpen.value = false;
  recommendationsOpen.value = true;
}
function jump(id: string) {
  const container = viewport.value,
    target = messageNodes.get(id);
  if (!container || !target) return;
  activeMessage.value = id;
  browsingHistory.value = true;
  stick.value = false;
  const top =
    container.scrollTop +
    target.getBoundingClientRect().top -
    container.getBoundingClientRect().top -
    16;
  container.scrollTo({
    top,
    behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
      ? "auto"
      : "smooth",
  });
  if (window.innerWidth < 1100) locatorOpen.value = false;
}
const count = computed(
  () =>
    `${state.selected}:${current.value?.messages.length}:${current.value?.pending}`,
);
function scrollState() {
  const el = viewport.value;
  if (el)
    stick.value =
      !browsingHistory.value &&
      el.scrollHeight - el.scrollTop - el.clientHeight < 80;
}
async function latest() {
  stick.value = true;
  browsingHistory.value = false;
  await nextTick();
  viewport.value?.scrollTo({
    top: viewport.value.scrollHeight,
    behavior: "auto",
  });
}
async function ask(question: string) {
  if (!current.value || current.value.task || !question.trim()) return;
  const id = state.selected;
  locatorOpen.value = false;
  stick.value = true;
  recommendationsOpen.value =
    window.innerWidth < 1100 ? false : recommendationsOpen.value;
  const request = sendQuestion(id, question);
  await latest();
  await request;
}
function enter(event: KeyboardEvent) {
  if (event.isComposing || event.keyCode === 229) return;
  event.preventDefault();
  if (!event.repeat && current.value) void ask(current.value.draft);
}
watch(count, async () => {
  if (stick.value) await latest();
});
watch(
  () => state.selected,
  () => {
    stick.value = true;
    clearConfirm.value = false;
    locatorOpen.value = false;
    activeMessage.value = null;
    browsingHistory.value = false;
    messageNodes.clear();
    void latest();
  },
);
onMounted(latest);
async function clear() {
  const id = state.selected,
    p = context(id);
  if (p.task || !clearConfirm.value) return;
  p.messageVersion++;
  p.task = "正在清空当前项目聊天…";
  try {
    await api.clear(id);
    p.messages = [];
    clearConfirm.value = false;
  } catch (e) {
    p.error = errorText(e);
  } finally {
    p.task = "";
  }
}
const time = (value: string) => {
  const d = new Date(value);
  return Number.isNaN(d.getTime())
    ? "时间未知"
    : d.toLocaleString("zh-CN", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      });
};
function sourceLabel(citation: Citation) {
  if (citation.reference == null)
    return citation.cited ? "模型标记支持（旧回答）" : "旧检索上下文";
  if (citation.cited)
    return citation.analysis_basis ? "事实来源 / 分析依据" : "支持对应事实段落";
  return citation.analysis_basis
    ? "仅作为分析依据，不证明建议已实施"
    : "仅检索上下文，未用于结论";
}
</script>
<template>
  <div v-if="!current" class="empty page">请先在左侧创建项目。</div>
  <div
    v-else
    class="chat-layout"
    :class="{ 'with-recommendations': recommendationsOpen }"
  >
    <section
      class="chat-workspace"
      aria-label="项目聊天"
      @keydown.esc="locatorOpen = false"
    >
      <header class="chat-toolbar">
        <span
          ><span class="status-dot"></span> 项目事实有依据 ·
          分析与建议分开标注</span
        >
        <div class="toolbar-actions">
          <button
            class="locator-toolbar-button"
            :aria-expanded="locatorOpen"
            @click="toggleLocator"
          >
            对话定位
          </button>
          <details class="clear-chat">
            <summary>清空聊天</summary>
            <div class="popover">
              <label class="check"
                ><input
                  v-model="clearConfirm"
                  type="checkbox"
                />永久清空当前项目聊天，保留资料与索引</label
              ><button
                :disabled="!clearConfirm || !!current.task"
                @click="clear"
              >
                确认清空
              </button>
            </div>
          </details>
          <button v-if="!recommendationsOpen" @click="openRecommendations">
            推荐问题 ◇
          </button>
        </div>
      </header>
      <button
        class="locator-launch icon"
        aria-label="打开对话定位"
        title="对话定位"
        :aria-expanded="locatorOpen"
        @click="toggleLocator"
      >
        ☷
      </button>
      <div
        v-if="locatorOpen"
        class="locator-scrim"
        @click="locatorOpen = false"
      ></div>
      <ConversationLocator
        v-if="locatorOpen"
        :messages="current.messages"
        :active-id="activeMessage"
        @jump="jump"
        @close="locatorOpen = false"
      />
      <div
        ref="viewport"
        class="messages"
        aria-label="聊天消息"
        @scroll="scrollState"
      >
        <div
          v-if="current.loading && !current.messages.length"
          class="empty"
          role="status"
        >
          正在恢复聊天记录…
        </div>
        <div
          v-else-if="!current.messages.length && !current.pending"
          class="chat-empty"
        >
          <div class="empty-symbol">◇</div>
          <h1>从一个好问题开始</h1>
          <p>
            直接提问，或从右侧选择推荐问题。<br />项目事实附真实来源，分析建议与通用知识单独标注。
          </p>
          <p class="muted small">
            项目事实需有资料支持；没有可用证据时，可提供明确标注的通用知识与建议。
          </p>
          <button @click="openRecommendations">浏览推荐问题 ↗</button>
        </div>
        <article
          v-for="message in current.messages"
          :key="message.id"
          :ref="(element) => messageRef(message.id, element)"
          :data-message-id="message.id"
          class="message"
          :class="[message.role, { located: activeMessage === message.id }]"
        >
          <div class="message-avatar">
            {{ message.role === "user" ? "你" : "↺" }}
          </div>
          <div class="message-body">
            <div class="message-meta">
              {{ message.role === "user" ? "你" : "ProjectRevisit"
              }}<time>{{ time(message.created_at) }}</time
              ><span v-if="message.status === 'failed'" class="error-text"
                >失败</span
              ><span v-else-if="message.status === 'insufficient'"
                >项目事实待核实</span
              >
            </div>
            <MarkdownMessage
              v-if="message.role === 'assistant'"
              :content="message.content"
            />
            <div v-else class="message-content">{{ message.content }}</div>
            <details v-if="message.citations.length" class="citations">
              <summary>来源证据 · {{ message.citations.length }} 条</summary>
              <section
                v-for="(citation, citationIndex) in message.citations"
                :key="citation.chunk_id"
                class="citation"
              >
                <span class="badge"
                  >资料 {{ citation.reference ?? citationIndex + 1 }}</span
                >
                <strong>{{ citation.source }}</strong>
                <p class="muted small">
                  {{ citation.heading || "无章节标题" }} ·
                  {{ sourceLabel(citation) }}
                </p>
                <div
                  v-if="citation.supporting_quotes?.length"
                  class="supporting-quotes"
                >
                  <span class="muted small">本次引用原文</span>
                  <p v-for="quote in citation.supporting_quotes" :key="quote">
                    {{ quote }}
                  </p>
                </div>
                <blockquote>{{ citation.text }}</blockquote>
                <details>
                  <summary class="small">完整 Chunk ID</summary>
                  <code>{{ citation.chunk_id }}</code>
                </details>
              </section>
            </details>
          </div>
        </article>
        <article v-if="current.pending" class="message user pending">
          <div class="message-avatar">你</div>
          <div class="message-body">
            <div class="message-meta">你 · 已发送</div>
            <div class="message-content">{{ current.pending }}</div>
          </div>
        </article>
        <div v-if="current.task" class="processing" role="status">
          <span class="spinner"></span>{{ current.task }}
        </div>
      </div>
      <div class="composer-area">
        <button v-if="!stick" class="latest" @click="latest">
          ↓ 返回最新消息
        </button>
        <p v-if="current.error" class="error" role="alert">
          {{ current.error }}
        </p>
        <form class="composer" @submit.prevent="ask(current!.draft)">
          <textarea
            v-model="current.draft"
            aria-label="询问当前项目"
            placeholder="询问当前项目…（Enter 发送，Shift+Enter 换行）"
            rows="2"
            maxlength="8000"
            :disabled="!!current.task"
            @keydown.enter.exact="enter"
          ></textarea
          ><button
            class="primary send"
            :disabled="!!current.task || !current.draft.trim()"
          >
            {{ current.pending ? "处理中…" : "发送 ↑" }}
          </button>
        </form>
        <p class="composer-note">
          发送问题将向已配置 API
          发送问题、必要历史和检索证据，可能产生费用。请核对引用。
        </p>
      </div>
    </section>
    <div
      v-if="recommendationsOpen"
      class="recommendation-scrim"
      @click="recommendationsOpen = false"
    ></div>
    <RecommendationPanel
      v-if="recommendationsOpen"
      @ask="ask"
      @close="recommendationsOpen = false"
    />
  </div>
</template>
