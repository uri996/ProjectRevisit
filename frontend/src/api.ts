import type {
  Answer,
  UploadResult,
  IndexResult,
  Document,
  Message,
  Project,
  Recommendations,
  Settings,
  SettingsView,
} from "./types";

async function request<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      credentials: "same-origin",
      headers:
        body instanceof FormData ? {} : { "Content-Type": "application/json" },
      body:
        body === undefined
          ? undefined
          : body instanceof FormData
            ? body
            : JSON.stringify(body),
    });
  } catch {
    throw new Error("无法连接本机服务。请检查启动窗口；请求不会自动重发。");
  }
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error(
      "本机服务返回了无效响应，请刷新状态后手动重试；请求不会自动重发。",
    );
  }
  if (!response.ok)
    throw new Error(
      data && typeof data.error === "string"
        ? data.error
        : "请求失败，请检查输入或稍后手动重试。",
    );
  return data as T;
}
const operation = () => ({ request_id: crypto.randomUUID(), confirmed: true });
const projectPath = (id: string) => `/projects/${encodeURIComponent(id)}`;
export const api = {
  projects: () => request<Project[]>("/projects"),
  createProject: (name: string) =>
    request<Project>("/projects", "POST", { name }),
  documents: (id: string) =>
    request<Document[]>(`${projectPath(id)}/documents`),
  upload: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<UploadResult>(`${projectPath(id)}/documents`, "POST", form);
  },
  index: (id: string, doc: string) =>
    request<IndexResult>(
      `${projectPath(id)}/documents/${encodeURIComponent(doc)}/index`,
      "POST",
      operation(),
    ),
  messages: (id: string) => request<Message[]>(`${projectPath(id)}/messages`),
  ask: (id: string, question: string) =>
    request<Answer>(`${projectPath(id)}/questions`, "POST", {
      ...operation(),
      question,
    }),
  clear: (id: string) =>
    request<{ status: string }>(
      `${projectPath(id)}/messages`,
      "DELETE",
      operation(),
    ),
  presets: () => request<Record<string, string[]>>("/recommendations/presets"),
  recommendations: (id: string) =>
    request<Recommendations | null>(`${projectPath(id)}/recommendations`),
  generate: (id: string, description: string, target_role: string) =>
    request<Recommendations>(`${projectPath(id)}/recommendations`, "POST", {
      ...operation(),
      description,
      target_role,
    }),
  settings: () => request<SettingsView>("/settings"),
  saveSettings: (settings: Settings, api_key: string) =>
    request<SettingsView>("/settings", "PUT", {
      settings,
      api_key,
      confirmed: true,
    }),
  testSettings: () =>
    request<{ message: string }>("/settings/test", "POST", operation()),
  dataLocation: () => request<{ path: string }>("/settings/data-location"),
};
