<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { api } from "./api";
import { errorText, loadProjects, selectProject, state } from "./store";
const name = ref(""),
  creating = ref(false),
  menu = ref(false);
const mobileQuery = window.matchMedia("(max-width: 900px)");
const mobile = ref(mobileQuery.matches);
const collapsed = ref(false);
try {
  collapsed.value =
    localStorage.getItem("projectrevisit.nav-collapsed") === "true";
} catch {
  /* optional UI preference */
}
const projectName = computed(
  () =>
    state.projects.find((p) => p.id === state.selected)?.name || "请先创建项目",
);
function setCollapsed(value: boolean) {
  collapsed.value = value;
  try {
    localStorage.setItem("projectrevisit.nav-collapsed", String(value));
  } catch {
    /* optional UI preference */
  }
}
function toggleNavigation() {
  if (mobile.value) menu.value = !menu.value;
  else setCollapsed(!collapsed.value);
}
function resized() {
  mobile.value = mobileQuery.matches;
  menu.value = false;
}
mobileQuery.addEventListener("change", resized);
onBeforeUnmount(() => mobileQuery.removeEventListener("change", resized));
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
  <div class="app-shell" :class="{ 'nav-collapsed': collapsed && !mobile }">
    <div v-if="menu && mobile" class="scrim" @click="menu = false"></div>
    <aside
      id="app-navigation"
      class="navigation"
      :class="{ open: menu }"
      aria-label="应用导航"
      @keydown.esc="menu = false"
    >
      <div class="brand">
        <span class="brand-icon">↺</span>
        <div class="brand-text">
          ProjectRevisit<small>项目复盘 · 面试准备</small>
        </div>
        <button
          class="mobile-only icon"
          @click="menu = false"
          aria-label="关闭导航"
        >
          ×
        </button>
      </div>
      <button
        v-if="collapsed && !mobile"
        class="project-shortcut icon"
        aria-label="展开项目选择"
        :title="projectName + ' · 切换或创建项目'"
        @click="setCollapsed(false)"
      >
        ▾
      </button>
      <label v-show="!collapsed || mobile" class="field-label" for="project"
        >当前项目</label
      >
      <select
        v-show="!collapsed || mobile"
        id="project"
        aria-label="当前项目"
        :value="state.selected"
        :title="projectName"
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
          :aria-label="link[1]"
          :title="link[1]"
          @click="menu = false"
          ><span aria-hidden="true">{{ link[2] }}</span
          ><span class="nav-label">{{ link[1] }}</span></RouterLink
        >
      </nav>
      <form
        v-show="!collapsed || mobile"
        class="create-project"
        @submit.prevent="create"
      >
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
      <div v-show="!collapsed || mobile" class="nav-footer">
        <span class="status-dot"></span> 本机运行 · 资料留在本机<small
          >索引与 AI 请求需手动触发</small
        >
      </div>
    </aside>
    <main class="workspace">
      <header class="app-bar">
        <button
          class="icon nav-toggle"
          @click="toggleNavigation"
          :aria-label="
            mobile
              ? menu
                ? '关闭导航'
                : '打开导航'
              : collapsed
                ? '展开导航'
                : '收起导航'
          "
          :title="
            mobile ? '打开或关闭导航' : collapsed ? '展开导航' : '收起导航'
          "
          :aria-expanded="mobile ? menu : !collapsed"
          aria-controls="app-navigation"
        >
          ☰</button
        ><span>{{ links.find((l) => l[0] === route.path)?.[1] }}</span
        ><span
          class="muted truncate current-project-name"
          :title="projectName"
          >{{ projectName }}</span
        >
      </header>
      <RouterView />
    </main>
  </div>
</template>
