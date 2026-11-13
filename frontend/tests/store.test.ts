import { beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import { api } from "../src/api";
import {
  context,
  generateQuestions,
  loadProject,
  selectProject,
  sendQuestion,
  state,
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
describe("project-scoped workflow", () => {
  it("shows the question synchronously, prevents duplicate sends and keeps late responses in the originating project", async () => {
    let finish!: () => void;
    vi.spyOn(api, "ask").mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = () => resolve({});
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
