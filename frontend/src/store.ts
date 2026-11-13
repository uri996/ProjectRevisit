import { computed, reactive } from "vue";
import { api } from "./api";
import type { Document, Message, Project, Recommendations } from "./types";

export interface ProjectState {
  documents: Document[];
  messages: Message[];
  recommendations: Recommendations | null;
  loading: boolean;
  task: string;
  error: string;
  recommendationError: string;
  pending: string;
  draft: string;
  description: string;
  role: string;
  loaded: boolean;
  version: number;
  messageVersion: number;
}
export const state = reactive({
  projects: [] as Project[],
  selected: "",
  error: "",
  projectsLoading: false,
  contexts: {} as Record<string, ProjectState>,
  presets: {} as Record<string, string[]>,
});
export function context(id: string): ProjectState {
  if (!state.contexts[id])
    state.contexts[id] = {
      documents: [],
      messages: [],
      recommendations: null,
      loading: false,
      task: "",
      error: "",
      recommendationError: "",
      pending: "",
      draft: "",
      description: "",
      role: "通用项目面试",
      loaded: false,
      version: 0,
      messageVersion: 0,
    };
  return state.contexts[id]!;
}
export const current = computed(() =>
  state.selected ? context(state.selected) : null,
);
export const currentProject = computed(() =>
  state.projects.find((p) => p.id === state.selected),
);
export function errorText(error: unknown) {
  return error instanceof Error ? error.message : "操作失败，请手动重试。";
}
export async function loadProject(id: string, force = false) {
  const p = context(id);
  if (p.loaded && !force) return;
  const version = ++p.version;
  const messageVersion = p.messageVersion;
  p.loading = true;
  p.error = "";
  p.recommendationError = "";
  await Promise.all([
    api
      .documents(id)
      .then((value) => {
        if (p.version === version) p.documents = value;
      })
      .catch((e) => {
        if (p.version === version) p.error = errorText(e);
      }),
    api
      .messages(id)
      .then((value) => {
        if (p.version === version && p.messageVersion === messageVersion)
          p.messages = value;
      })
      .catch((e) => {
        if (p.version === version) p.error = errorText(e);
      }),
    api
      .recommendations(id)
      .then((value) => {
        if (p.version === version) {
          p.recommendations = value;
          if (!p.loaded && value) {
            p.description = value.description;
            p.role = value.target_role;
          }
        }
      })
      .catch((e) => {
        if (p.version === version) p.recommendationError = errorText(e);
      }),
  ]);
  if (p.version === version) {
    p.loading = false;
    p.loaded = true;
  }
}
export function selectProject(id: string) {
  state.selected = id;
  // Store only the selected UUID, per tab. No keys, documents, resumes or chat in web storage.
  try {
    sessionStorage.setItem("projectrevisit.selection", id);
  } catch {
    /* private-mode storage may be unavailable */
  }
  void loadProject(id);
}
export async function loadProjects() {
  state.projectsLoading = true;
  state.error = "";
  try {
    state.projects = await api.projects();
    let saved = "";
    try {
      saved = sessionStorage.getItem("projectrevisit.selection") || "";
    } catch {
      /* optional */
    }
    const selected =
      state.projects.find((p) => p.id === (state.selected || saved)) ||
      state.projects[0];
    if (selected) selectProject(selected.id);
  } catch (e) {
    state.error = errorText(e);
  } finally {
    state.projectsLoading = false;
  }
}
export async function sendQuestion(id: string, question: string) {
  const p = context(id);
  const text = question.trim();
  if (p.task || !text || text.length > 8000) return;
  p.task = "正在检索项目证据并生成回答…";
  p.pending = text;
  p.error = "";
  p.draft = "";
  p.messageVersion++;
  try {
    await api.ask(id, text);
  } catch (e) {
    p.error = errorText(e);
    p.draft = text;
  }
  try {
    p.messages = await api.messages(id);
  } catch (e) {
    p.error = `${p.error} ${errorText(e)}`.trim();
  } finally {
    p.task = "";
    p.pending = "";
  }
}
export async function generateQuestions(id: string) {
  const p = context(id);
  if (p.task) return;
  p.task = "正在生成个性化问题…";
  p.recommendationError = "";
  try {
    p.recommendations = await api.generate(id, p.description, p.role);
  } catch (e) {
    p.recommendationError = errorText(e);
  } finally {
    p.task = "";
  }
}
