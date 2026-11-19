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
  recommendationVersion: number;
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
      recommendationVersion: 0,
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
  const recommendationVersion = p.recommendationVersion;
  const description = p.description,
    role = p.role;
  let complete = true;
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
        complete = false;
        if (p.version === version) p.error = errorText(e);
      }),
    api
      .messages(id)
      .then((value) => {
        if (p.version === version && p.messageVersion === messageVersion)
          p.messages = value;
      })
      .catch((e) => {
        complete = false;
        if (p.version === version && p.messageVersion === messageVersion)
          p.error = errorText(e);
      }),
    api
      .recommendations(id)
      .then((value) => {
        if (
          p.version === version &&
          p.recommendationVersion === recommendationVersion
        ) {
          p.recommendations = value;
          if (!p.loaded && value) {
            if (!description && p.description === description)
              p.description = value.description;
            if (role === "通用项目面试" && p.role === role)
              p.role = value.target_role;
          }
        }
      })
      .catch((e) => {
        complete = false;
        if (
          p.version === version &&
          p.recommendationVersion === recommendationVersion
        )
          p.recommendationError = errorText(e);
      }),
  ]);
  if (p.version === version) {
    p.loading = false;
    p.loaded = complete;
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
  // Invalidate reads that started while the paid operation was in flight.
  p.messageVersion++;
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
  p.recommendationVersion++;
  try {
    p.recommendations = await api.generate(id, p.description, p.role);
  } catch (e) {
    p.recommendationError = errorText(e);
  } finally {
    p.recommendationVersion++;
    p.task = "";
  }
}

export async function clearMessages(id: string) {
  const p = context(id);
  if (p.task) return false;
  p.task = "正在清空当前项目聊天…";
  p.error = "";
  p.messageVersion++;
  try {
    await api.clear(id);
    p.messages = [];
    return true;
  } catch (e) {
    p.error = errorText(e);
    return false;
  } finally {
    p.messageVersion++;
    p.task = "";
  }
}

async function documentTask<T>(
  id: string,
  task: string,
  action: (p: ProjectState) => Promise<T>,
) {
  const p = context(id);
  if (p.task) return;
  p.task = task;
  p.error = "";
  try {
    return await action(p);
  } catch (e) {
    p.error = errorText(e);
  } finally {
    const error = p.error;
    // Keep the operation locked until its refreshed snapshot is installed.
    await loadProject(id, true);
    if (error) p.error = error;
    p.task = "";
  }
}

export function uploadDocuments(id: string, files: File[]) {
  const batch = [...files];
  if (!batch.length) return;
  return documentTask(id, "正在保存上传文件…", async (p) => {
    let feedback = "";
    for (let i = 0; i < batch.length; i++) {
      p.task = `保存文件 ${i + 1}/${batch.length}`;
      const result = await api.upload(id, batch[i]!);
      feedback =
        result.action === "duplicate"
          ? "相同内容已存在，未重复导入。"
          : "文件已保存，尚未发送 Embedding 请求。";
    }
    return feedback;
  });
}

export function indexDocuments(id: string, documentIds: string[]) {
  const docs = [...documentIds];
  if (!docs.length) return;
  return documentTask(id, "正在建立索引…", async (p) => {
    let failures = 0;
    for (let i = 0; i < docs.length; i++) {
      p.task = `正在建立索引 ${i + 1}/${docs.length}…`;
      try {
        await api.index(id, docs[i]!);
      } catch (e) {
        failures++;
        p.error = errorText(e);
      }
    }
    return failures;
  });
}
