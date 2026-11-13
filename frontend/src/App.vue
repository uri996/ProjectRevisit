<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { api } from "./api";
import { errorText, loadProjects, selectProject, state } from "./store";
const name = ref(""),
  creating = ref(false),
  menu = ref(false);
const route = useRoute();
const links = [
  ["/", "项目概况", "◫"],
  ["/knowledge", "知识库管理", "▤"],
  ["/chat", "智能问答", "◇"],
  ["/settings", "AI 设置", "⚙"],
];
async function create() {
  if (creating.value || !name.value.trim()) return;
  creating.value = true;
  state.error = "";
  try {
    const p = await api.createProject(name.value);
    state.projects.push(p);
    selectProject(p.id);
    name.value = "";
  } catch (e) {
    state.error = errorText(e);
  } finally {
    creating.value = false;
  }
}
onMounted(async () => {
  await loadProjects();
  try {
    state.presets = await api.presets();
  } catch (e) {
    state.error = errorText(e);
  }
});
</script>
<template>
  <div class="app-shell">
    <div v-if="menu" class="scrim" @click="menu = false"></div>
    <aside class="navigation" :class="{ open: menu }">
      <div class="brand">
        <span class="brand-icon">↺</span>
        <div>ProjectRevisit<small>项目复盘 · 面试准备</small></div>
        <button
          class="mobile-only icon"
          @click="menu = false"
          aria-label="关闭导航"
        >
          ×
        </button>
      </div>
      <label class="field-label" for="project">当前项目</label>
      <select
        id="project"
        aria-label="当前项目"
        :value="state.selected"
        @change="selectProject(($event.target as HTMLSelectElement).value)"
      >
        <option v-if="!state.projects.length" value="">暂无项目</option>
        <option v-for="p in state.projects" :key="p.id" :value="p.id">
          {{ p.name }}
        </option>
      </select>
      <nav>
        <RouterLink
          v-for="link in links"
          :key="link[0]"
          :to="link[0]!"
          :class="{ active: route.path === link[0] }"
          @click="menu = false"
          ><span>{{ link[2] }}</span
          >{{ link[1] }}</RouterLink
        >
      </nav>
      <form class="create-project" @submit.prevent="create">
        <label for="new-project">创建项目</label
        ><input
          id="new-project"
          v-model="name"
          maxlength="100"
          placeholder="新项目名称"
          required
        /><button :disabled="creating || !name.trim()">
          {{ creating ? "创建中…" : "+ 创建项目" }}
        </button>
      </form>
      <p v-if="state.error" role="alert" class="error">{{ state.error }}</p>
      <button v-if="state.error" @click="loadProjects">重试加载</button>
      <div class="nav-footer">
        <span class="status-dot"></span> 本机运行 · 资料留在本机<small
          >索引与 AI 请求需手动触发</small
        >
      </div>
    </aside>
    <main class="workspace">
      <header class="app-bar">
        <button
          class="mobile-only icon"
          @click="menu = true"
          aria-label="打开导航"
        >
          ☰</button
        ><span>{{ links.find((l) => l[0] === route.path)?.[1] }}</span
        ><span class="muted truncate">{{
          state.projects.find((p) => p.id === state.selected)?.name ||
          "请先创建项目"
        }}</span>
      </header>
      <RouterView />
    </main>
  </div>
</template>
