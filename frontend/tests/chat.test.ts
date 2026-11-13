import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { createApp, nextTick } from "vue";
import type { App } from "vue";
import Chat from "../src/views/Chat.vue";
import RecommendationPanel from "../src/components/RecommendationPanel.vue";
import { api } from "../src/api";
import { context, state } from "../src/store";
import type { Recommendations } from "../src/types";

let app: App, host: HTMLElement;
beforeEach(() => {
  state.contexts = {};
  state.selected = "a";
  state.presets = {
    项目复盘: ["虚构目录如何保存？"],
    面试准备: ["请介绍虚构项目。"],
  };
  host = document.createElement("div");
  document.body.append(host);
  Object.defineProperty(window, "innerWidth", {
    value: 1440,
    configurable: true,
  });
  Object.defineProperty(HTMLElement.prototype, "scrollTo", {
    value: vi.fn(),
    configurable: true,
  });
  vi.restoreAllMocks();
});
afterEach(() => {
  app?.unmount();
  host.remove();
});
const flush = async () => {
  await new Promise((r) => setTimeout(r, 0));
  await nextTick();
};
it("does not send during Chinese IME composition or a repeated Enter key", async () => {
  vi.spyOn(api, "ask").mockResolvedValue({});
  vi.spyOn(api, "messages").mockResolvedValue([]);
  context("a").draft = "虚构项目问题";
  app = createApp(Chat);
  app.mount(host);
  await nextTick();
  const input = host.querySelector("textarea")!;
  input.dispatchEvent(
    new KeyboardEvent("keydown", {
      key: "Enter",
      isComposing: true,
      bubbles: true,
      cancelable: true,
    }),
  );
  input.dispatchEvent(
    new KeyboardEvent("keydown", {
      key: "Enter",
      repeat: true,
      bubbles: true,
      cancelable: true,
    }),
  );
  expect(api.ask).not.toHaveBeenCalled();
  input.dispatchEvent(
    new KeyboardEvent("keydown", {
      key: "Enter",
      bubbles: true,
      cancelable: true,
    }),
  );
  await flush();
  expect(api.ask).toHaveBeenCalledTimes(1);
});
it("clicking a recommendation immediately displays a pending question and disables repeated clicks", async () => {
  let finish!: (v: unknown) => void;
  vi.spyOn(api, "ask").mockImplementation(
    () =>
      new Promise((r) => {
        finish = r;
      }),
  );
  vi.spyOn(api, "messages").mockResolvedValue([]);
  app = createApp(Chat);
  app.mount(host);
  await nextTick();
  const button = Array.from(host.querySelectorAll("button")).find((b) =>
    b.textContent?.includes("虚构目录如何保存"),
  )!;
  button.click();
  await nextTick();
  expect(host.querySelector(".pending")?.textContent).toContain(
    "虚构目录如何保存",
  );
  expect(host.querySelector("[role=status]")?.textContent).toContain(
    "正在检索",
  );
  expect(button.disabled).toBe(true);
  button.click();
  expect(api.ask).toHaveBeenCalledTimes(1);
  finish({});
  await flush();
  expect(button.disabled).toBe(false);
});
it("renders long content safely with independent message and recommendation containers", async () => {
  context("a").messages = Array.from({ length: 80 }, (_, i) => ({
    id: String(i),
    role: "assistant",
    content: "虚构长消息 <script>unsafe()</script>".repeat(200),
    created_at: "2026-01-01T00:00:00Z",
    status: "completed",
    citations: [],
  }));
  app = createApp(Chat);
  app.mount(host);
  await nextTick();
  expect(host.querySelectorAll(".message")).toHaveLength(80);
  expect(host.querySelector(".messages")).not.toBeNull();
  expect(host.querySelector(".recommendation-scroll")).not.toBeNull();
  expect(host.querySelector("script")).toBeNull();
});
it("generation requires explicit consent and is not repeated by a rerender", async () => {
  let finish!: (v: Recommendations) => void;
  vi.spyOn(api, "generate").mockImplementation(
    () =>
      new Promise((r) => {
        finish = r;
      }),
  );
  app = createApp(RecommendationPanel, { onAsk: vi.fn(), onClose: vi.fn() });
  app.mount(host);
  Array.from(host.querySelectorAll("button"))
    .find((b) => b.textContent === "根据简历生成")!
    .click();
  await nextTick();
  const p = context("a");
  p.description = "虚构图书目录";
  p.role = "后端开发";
  await nextTick();
  const form = host.querySelector("form")!;
  form.dispatchEvent(new Event("submit", { cancelable: true }));
  await nextTick();
  expect(api.generate).not.toHaveBeenCalled();
  const checkbox = host.querySelector(
    "input[type=checkbox]",
  ) as HTMLInputElement;
  checkbox.checked = true;
  checkbox.dispatchEvent(new Event("change"));
  await nextTick();
  form.dispatchEvent(new Event("submit", { cancelable: true }));
  await nextTick();
  expect(api.generate).toHaveBeenCalledTimes(1);
  await nextTick();
  expect(api.generate).toHaveBeenCalledTimes(1);
  finish({
    project_id: "a",
    description: p.description,
    target_role: p.role,
    questions: [],
    updated_at: "2026-01-01T00:00:00Z",
  });
  await flush();
});

it("locates stable message IDs in the independent viewport and does not follow new messages while reading history", async () => {
  const p = context("a");
  p.messages = [
    {
      id: "question-first",
      role: "user",
      content: "虚构的较早问题".repeat(20),
      created_at: "2026-01-01T00:00:00Z",
      status: "completed",
      citations: [],
    },
    {
      id: "answer-first",
      role: "assistant",
      content: "**虚构回答**",
      created_at: "2026-01-01T00:00:01Z",
      status: "completed",
      citations: [],
    },
    {
      id: "question-later",
      role: "user",
      content: "较新的虚构问题",
      created_at: "2026-01-01T00:01:00Z",
      status: "completed",
      citations: [],
    },
  ];
  app = createApp(Chat);
  app.mount(host);
  await flush();
  const viewport = host.querySelector(".messages") as HTMLElement;
  const target = host.querySelector(
    '[data-message-id="question-first"]',
  ) as HTMLElement;
  vi.spyOn(viewport, "getBoundingClientRect").mockReturnValue({
    top: 100,
  } as DOMRect);
  vi.spyOn(target, "getBoundingClientRect").mockReturnValue({
    top: 500,
  } as DOMRect);
  viewport.scrollTop = 200;
  (host.querySelector(".locator-launch") as HTMLButtonElement).click();
  await nextTick();
  const entry = host.querySelector(
    '[data-target-id="question-first"]',
  ) as HTMLButtonElement;
  expect(entry.title).toBe(p.messages[0]!.content);
  expect(entry.textContent).toContain("…");
  vi.mocked(viewport.scrollTo).mockClear();
  entry.click();
  await nextTick();
  expect(viewport.scrollTo).toHaveBeenCalledWith({
    top: 584,
    behavior: "smooth",
  });
  expect(target.classList.contains("located")).toBe(true);
  p.messages.push({
    id: "answer-new",
    role: "assistant",
    content: "新来的虚构回答",
    created_at: "2026-01-01T00:02:00Z",
    status: "completed",
    citations: [],
  });
  await flush();
  expect(viewport.scrollTo).toHaveBeenCalledTimes(1);
  state.selected = "b";
  await flush();
  expect(host.querySelector('[data-target-id="question-first"]')).toBeNull();
  (host.querySelector(".locator-launch") as HTMLButtonElement).click();
  await nextTick();
  expect(host.querySelectorAll(".conversation-list button")).toHaveLength(0);
});
