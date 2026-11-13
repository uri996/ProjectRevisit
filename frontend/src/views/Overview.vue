<script setup lang="ts">
import { computed } from "vue";
import { current, currentProject, loadProject, state } from "../store";
const indexed = computed(
  () =>
    current.value?.documents.filter((d) => d.status === "completed").length ||
    0,
);
</script>
<template>
  <section class="page scroll-area">
    <div class="page-heading">
      <div>
        <h1 class="project-heading" :title="currentProject?.name">
          {{ currentProject?.name || "欢迎使用 ProjectRevisit" }}
        </h1>
        <p class="muted">
          从自己的项目资料出发，复盘决策、寻找证据、准备面试。
        </p>
      </div>
      <button
        v-if="state.selected"
        :disabled="current?.loading"
        @click="loadProject(state.selected, true)"
      >
        刷新状态
      </button>
    </div>
    <div v-if="!current" class="empty">
      <h2>先创建一个项目</h2>
      <p>使用左侧创建入口。未配置 API 也能创建项目和导入文件。</p>
    </div>
    <template v-else
      ><p v-if="current.error" class="error" role="alert">
        {{ current.error }}
      </p>
      <p v-if="current.loading" role="status">正在读取项目…</p>
      <div class="metrics">
        <article>
          <strong>{{ current.documents.length }}</strong><span>已导入文档</span>
        </article>
        <article>
          <strong>{{ indexed }}</strong><span>已完成兼容索引</span>
        </article>
        <article>
          <strong>{{ current.messages.length }}</strong><span>聊天消息</span>
        </article>
      </div>
      <div class="card">
        <h2>开始一次有依据的复盘</h2>
        <ol class="steps">
          <li>
            <RouterLink to="/knowledge">导入项目资料</RouterLink>
            <p>Markdown / TXT，仅保存到本机。</p>
          </li>
          <li>
            手动确认建立索引
            <p>确认目标 API 后再发送资料，不会自动重建。</p>
          </li>
          <li>
            <RouterLink to="/chat">提问，或使用推荐问题</RouterLink>
            <p>回答与引用按项目保存，刷新后可恢复。</p>
          </li>
        </ol>
      </div>
      <p class="muted small">项目 ID：{{ state.selected }}</p></template
    >
  </section>
</template>
