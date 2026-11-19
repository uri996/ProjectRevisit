import { beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import { api } from "../src/api";
import {
  context,
  clearMessages,
  indexDocuments,
  generateQuestions,
  loadProject,
  selectProject,
  sendQuestion,
  state,
  uploadDocuments,
} from "../src/store";
import type { Message, Recommendations } from "../src/types";

beforeEach(() => {
  state.selected = "";
  state.contexts = {};
  state.projects = [];
  sessionStorage.clear();
  vi.restoreAllMocks();
});
const message = (id: string, content: string): Message => ({
  id,
  content,
  role: "assistant",
  status: "completed",
  created_at: "2026-01-01T00:00:00Z",
  citations: [],
});
const saved: Recommendations = {
  project_id: "a",
  description: "虚构图书目录",
  target_role: "后端开发",
  questions: [
    { question: "如何保存目录？", direction: "存储", reason: "核对虚构设计" },
  ],
  updated_at: "2026-01-01T00:00:00Z",
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
function projectReads() {
  vi.spyOn(api, "documents").mockResolvedValue([]);
  vi.spyOn(api, "messages").mockResolvedValue([]);
  vi.spyOn(api, "recommendations").mockResolvedValue(null);
}
describe("project-scoped workflow", () => {
  it("retries partial loads on reentry while keeping optional failures separate from chat", async () => {
    projectReads();
    vi.mocked(api.recommendations).mockRejectedValueOnce(
      new Error("推荐读取失败"),
    );
    await loadProject("a");
    expect(context("a").loaded).toBe(false);
    expect(context("a").error).toBe("");
    expect(context("a").recommendationError).toBe("推荐读取失败");
    await loadProject("a");
    expect(context("a").loaded).toBe(true);
    expect(context("a").recommendationError).toBe("");
    expect(api.messages).toHaveBeenCalledTimes(2);
    vi.mocked(api.messages).mockRejectedValueOnce(new Error("历史读取失败"));
    await loadProject("a", true);
    expect(context("a").loaded).toBe(false);
    await loadProject("a");
    expect(context("a").loaded).toBe(true);
  });
  it("does not let a late initial recommendation read overwrite newly generated results or an edited form", async () => {
    projectReads();
    const old = deferred<Recommendations | null>();
    vi.mocked(api.recommendations).mockReturnValueOnce(old.promise);
    const loading = loadProject("a");
    context("a").description = "新的虚构目录描述";
    const generated = { ...saved, description: context("a").description };
    vi.spyOn(api, "generate").mockResolvedValue(generated);
    await generateQuestions("a");
    old.resolve(saved);
    await loading;
    expect(context("a").recommendations).toEqual(generated);
    expect(context("a").description).toBe("新的虚构目录描述");
  });
  it("does not replace edits with a delayed saved form", async () => {
    projectReads();
    const old = deferred<Recommendations | null>();
    vi.mocked(api.recommendations).mockReturnValueOnce(old.promise);
    const loading = loadProject("a");
    context("a").description = "正在编辑的虚构资料";
    context("a").role = "虚构岗位";
    old.resolve(saved);
    await loading;
    expect(context("a").recommendations).toEqual(saved);
    expect(context("a").description).toBe("正在编辑的虚构资料");
    expect(context("a").role).toBe("虚构岗位");
  });
  it("blocks stale history reads launched during a question and keeps clear scoped to its project", async () => {
    projectReads();
    const ask = deferred<{ answer: string; status: string; citations: [] }>();
    const old = deferred<Message[]>();
    vi.spyOn(api, "ask").mockReturnValue(ask.promise);
    const pending = sendQuestion("a", "虚构问题");
    vi.mocked(api.messages).mockReturnValueOnce(old.promise);
    const loading = loadProject("a", true);
    vi.mocked(api.messages).mockResolvedValue([message("new", "新回答")]);
    ask.resolve({ answer: "新回答", status: "completed", citations: [] });
    await pending;
    old.resolve([]);
    await loading;
    expect(context("a").messages[0]?.id).toBe("new");
    const clear = deferred<{ status: string }>();
    vi.spyOn(api, "clear").mockReturnValue(clear.promise);
    state.selected = "b";
    context("b").messages = [message("b", "保留 B")];
    const clearing = clearMessages("a");
    expect(await clearMessages("a")).toBe(false);
    clear.resolve({ status: "ok" });
    expect(await clearing).toBe(true);
    expect(context("a").messages).toEqual([]);
    expect(context("b").messages[0]?.id).toBe("b");
  });
  it("uploads without indexing and retains a project task until refresh finishes", async () => {
    projectReads();
    const refresh = deferred<[]>();
    vi.mocked(api.documents).mockReturnValue(refresh.promise);
    vi.spyOn(api, "upload").mockResolvedValue({
      action: "created",
      document_id: "doc-a",
    });
    vi.spyOn(api, "index");
    const file = new File(["Fictional catalog"], "catalog.md");
    const pending = uploadDocuments("a", [file]);
    await nextTick();
    expect(context("a").task).not.toBe("");
    await uploadDocuments("a", [file]);
    expect(api.upload).toHaveBeenCalledTimes(1);
    expect(api.index).not.toHaveBeenCalled();
    refresh.resolve([]);
    expect(await pending).toContain("尚未发送");
    expect(context("a").task).toBe("");
  });
  it("indexes only requested documents, preserves failures through refresh and isolates project state", async () => {
    projectReads();
    vi.spyOn(api, "index")
      .mockRejectedValueOnce(new Error("模拟索引失败"))
      .mockResolvedValueOnce({
        document_id: "doc-2",
        chunk_count: 1,
        status: "completed",
      });
    state.selected = "b";
    expect(await indexDocuments("a", ["doc-1", "doc-2"])).toBe(1);
    expect(vi.mocked(api.index).mock.calls).toEqual([
      ["a", "doc-1"],
      ["a", "doc-2"],
    ]);
    expect(context("a").error).toBe("模拟索引失败");
    expect(context("a").task).toBe("");
    expect(context("b").error).toBe("");
  });
  it("shows the question synchronously, prevents duplicate sends and keeps late responses in the originating project", async () => {
    let finish!: () => void;
    vi.spyOn(api, "ask").mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = () =>
            resolve({ answer: "演示回答", status: "completed", citations: [] });
        }),
    );
    vi.spyOn(api, "messages").mockResolvedValue([
      message("reply-a", "只属于 A"),
    ]);
    state.selected = "a";
    const pending = sendQuestion("a", "目录如何保存？");
    expect(context("a").pending).toBe("目录如何保存？");
    expect(context("a").task).not.toBe("");
    await sendQuestion("a", "重复问题");
    expect(api.ask).toHaveBeenCalledTimes(1);
    state.selected = "b";
    await nextTick();
    finish();
    await pending;
    expect(context("b").messages).toEqual([]);
    expect(context("a").messages[0]?.content).toBe("只属于 A");
    expect(context("a").task).toBe("");
  });
  it("restores saved questions without regenerating and isolates drafts across projects", async () => {
    vi.spyOn(api, "documents").mockResolvedValue([]);
    vi.spyOn(api, "messages").mockResolvedValue([]);
    vi.spyOn(api, "recommendations").mockImplementation(async (id) =>
      id === "a" ? saved : null,
    );
    vi.spyOn(api, "generate");
    await loadProject("a");
    context("a").draft = "A 的草稿";
    await loadProject("b");
    await loadProject("a");
    expect(context("a").description).toBe(saved.description);
    expect(context("b").description).toBe("");
    expect(context("a").draft).toBe("A 的草稿");
    expect(api.generate).not.toHaveBeenCalled();
    selectProject("b");
    expect(sessionStorage.getItem("projectrevisit.selection")).toBe("b");
    expect(Object.keys(sessionStorage)).toEqual(["projectrevisit.selection"]);
  });
  it("preserves successful recommendations on failure and leaves chatting available", async () => {
    const p = context("a");
    p.recommendations = saved;
    p.description = saved.description;
    vi.spyOn(api, "generate").mockRejectedValue(new Error("模拟 API 失败"));
    await generateQuestions("a");
    expect(p.recommendations).toEqual(saved);
    expect(p.recommendationError).toContain("模拟 API 失败");
    expect(p.task).toBe("");
    vi.spyOn(api, "ask").mockRejectedValue(new Error("模拟网络错误"));
    vi.spyOn(api, "messages").mockResolvedValue([]);
    await sendQuestion("a", "测试问题");
    expect(p.error).toContain("模拟网络错误");
    expect(p.pending).toBe("");
    expect(p.draft).toBe("测试问题");
  });
});
