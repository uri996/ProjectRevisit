import { test, expect } from "@playwright/test";
import { Buffer } from "node:buffer";
import { markdownAnswer } from "../fixtures";
import type { Message } from "../../src/types";

test.afterAll(async ({ request }) => {
  await request.post("/__test__/stop").catch(() => {});
});
test("complete Vue + FastAPI workflow with isolated SQLite/Chroma and mock Qwen", async ({
  page,
  request,
}) => {
  await page.goto("/");
  await page
    .getByLabel("新项目名称", { exact: false })
    .count()
    .then(() => {});
  await page.locator("#new-project").fill("示例项目 A");
  await page.getByRole("button", { name: "+ 创建项目", exact: true }).click();
  await expect(page.locator("#project option")).toHaveCount(1);
  const sidebarToggle = page
    .locator(".navigation")
    .getByRole("button", { name: "收起导航", exact: true });
  await expect(sidebarToggle).toBeVisible();
  await expect(page.locator(".app-bar .nav-toggle")).toHaveCount(0);
  const navBounds = (await page.locator(".navigation").boundingBox())!,
    toggleBounds = (await sidebarToggle.boundingBox())!;
  expect(toggleBounds.x).toBeGreaterThanOrEqual(navBounds.x);
  expect(toggleBounds.x + toggleBounds.width).toBeLessThanOrEqual(
    navBounds.x + navBounds.width,
  );
  await sidebarToggle.click();
  await expect(
    page
      .locator(".navigation")
      .getByRole("button", { name: "展开导航", exact: true }),
  ).toBeVisible();
  await page.screenshot({ path: "test-results/sidebar-toggle-collapsed.png" });
  await page
    .locator(".navigation")
    .getByRole("button", { name: "展开导航", exact: true })
    .click();
  await page.screenshot({ path: "test-results/sidebar-toggle-expanded.png" });
  const first = await page.locator("#project").inputValue();
  await page.locator("#new-project").fill("示例项目 B");
  await page.getByRole("button", { name: "+ 创建项目", exact: true }).click();
  await expect(page.locator("#project option")).toHaveCount(2);
  const second = await page.locator("#project").inputValue();
  await page.locator("#project").selectOption(first);
  await page.getByRole("link", { name: "知识库管理", exact: false }).click();
  await page.getByLabel("选择项目资料").setInputFiles({
    name: "catalog.md",
    mimeType: "text/markdown",
    buffer: Buffer.from(
      "# Fictional catalog\nCatalog 使用 CSV 保存图书目录，编号必须唯一。",
    ),
  });
  await page
    .getByRole("button", { name: "保存上传文件", exact: false })
    .click();
  await expect(page.getByText("未索引", { exact: true })).toBeVisible();
  expect((await (await request.get("/__test__/counts")).json()).embedding).toBe(
    0,
  );
  await page.getByLabel("选择 catalog.md", { exact: true }).check();
  await page
    .getByRole("checkbox", {
      name: "我确认向 AI 设置中已保存的 API 地址发送所选资料，可能产生费用。",
    })
    .check();
  await page
    .getByRole("button", { name: "建立索引 / 重新索引", exact: true })
    .click();
  await expect(page.getByText("已完成", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "智能问答", exact: false }).click();
  await page
    .getByLabel("询问当前项目", { exact: true })
    .fill("Catalog CSV 图书如何保存？");
  await page.getByRole("button", { name: "发送 ↑", exact: true }).click();
  await expect(page.locator(".pending")).toContainText(
    "Catalog CSV 图书如何保存？",
  );
  await expect(page.getByRole("status")).toContainText("正在检索");
  await expect(page.locator(".pending")).toHaveCount(0);
  await expect(page.locator(".message")).toHaveCount(2);
  await page.locator(".citations > summary").first().click();
  await expect(page.locator(".citation strong").first()).toHaveText(
    "catalog.md",
  );
  await page.getByRole("button", { name: "根据简历生成", exact: true }).click();
  await page
    .getByRole("textbox", { name: "项目简历描述", exact: true })
    .fill("虚构图书目录，Catalog 使用 CSV 保存图书，编号唯一。");
  await page
    .getByRole("textbox", { name: "目标岗位", exact: true })
    .fill("后端开发");
  await page
    .getByRole("checkbox", { name: "确认发送至已配置 LLM API，可能产生费用。" })
    .check();
  const before = await (await request.get("/__test__/counts")).json();
  await page
    .getByRole("button", { name: "生成 / 重新生成问题", exact: true })
    .click();
  await expect(page.locator(".personal-question")).toHaveCount(6);
  const after = await (await request.get("/__test__/counts")).json();
  expect(after.embedding).toBe(before.embedding);
  expect(after.llm).toBe(before.llm + 1);
  const recommended = page.getByRole("button", {
    name: "Catalog 如何使用 CSV 保存图书目录？",
    exact: false,
  });
  await recommended.click();
  await expect(page.locator(".pending")).toContainText("Catalog 如何使用 CSV");
  await expect(recommended).toBeDisabled();
  await page.screenshot({ path: "test-results/pending.png" });
  await expect(page.locator(".message")).toHaveCount(4);
  await page
    .getByLabel("询问当前项目", { exact: true })
    .fill("Catalog CSV 的另一个问题");
  await page.getByRole("button", { name: "发送 ↑", exact: true }).click();
  await page.locator("#project").selectOption(second);
  await expect(page.locator(".message")).toHaveCount(0);
  await expect(page.locator(".personal-question")).toHaveCount(0);
  await page.waitForTimeout(1200);
  await expect(page.locator(".message")).toHaveCount(0);
  await page.locator("#project").selectOption(first);
  await expect(page.locator(".message")).toHaveCount(6);
  await request.post("/__test__/long-history/" + first);
  const calls = await (await request.get("/__test__/counts")).json();
  await page.reload();
  await expect(page.locator(".message")).toHaveCount(86);
  await expect(page.locator(".personal-question")).toHaveCount(6);
  expect((await (await request.get("/__test__/counts")).json()).llm).toBe(
    calls.llm,
  );
  const layout = await page.evaluate(() => {
    const messages = document.querySelector(".messages") as HTMLElement,
      recommendations = document.querySelector(
        ".recommendation-scroll",
      ) as HTMLElement;
    messages.scrollTop = 0;
    recommendations.scrollTop = 300;
    return {
      chatOverflow: messages.scrollHeight > messages.clientHeight,
      recOverflow: recommendations.scrollHeight > recommendations.clientHeight,
      chatTop: messages.scrollTop,
      body: document.documentElement.scrollHeight,
      height: innerHeight,
    };
  });
  expect(layout.chatOverflow).toBe(true);
  expect(layout.recOverflow).toBe(true);
  expect(layout.chatTop).toBe(0);
  expect(layout.body).toBeLessThanOrEqual(layout.height + 1);
  await page.screenshot({ path: "test-results/desktop.png" });
  await page
    .getByRole("button", { name: "↓ 返回最新消息", exact: true })
    .click();
  await request.post("/__test__/fail-next");
  await page
    .getByLabel("询问当前项目", { exact: true })
    .fill("Catalog CSV 模拟失败问题");
  await page.getByRole("button", { name: "发送 ↑", exact: true }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByLabel("询问当前项目", { exact: true })).toBeEnabled();
  expect(await page.textContent("body")).not.toContain(
    "synthetic-private-provider-error",
  );
  await page.setViewportSize({ width: 760, height: 900 });
  await page.getByRole("button", { name: "收起推荐面板", exact: true }).click();
  await expect(page.locator(".recommendation-panel")).toHaveCount(0);
  await page.getByRole("button", { name: "推荐问题 ◇", exact: true }).click();
  await expect(page.locator(".recommendation-panel")).toBeVisible();
  await page.screenshot({ path: "test-results/narrow.png" });
  await page.getByRole("button", { name: "收起推荐面板", exact: true }).click();
  await page.setViewportSize({ width: 480, height: 850 });
  await expect(page.locator(".navigation")).not.toBeInViewport();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({ path: "test-results/mobile.png" });
  await page.getByRole("button", { name: "打开导航", exact: true }).click();
  await page.getByRole("link", { name: "AI 设置", exact: false }).click();
  await expect(
    page.getByRole("heading", { name: "模型与目标地址", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "LLM 模型 ID", exact: true })
    .fill("synthetic-llm");
  await page
    .getByRole("checkbox", {
      name: "我已核对实际地址、地域和模型。更改 Embedding 或分块配置后需要手动重建索引。",
    })
    .check();
  await page.getByRole("button", { name: "保存设置", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("设置已保存");
  await page
    .getByRole("checkbox", { name: "确认测试已保存配置并可能产生 API 费用。" })
    .check();
  await page
    .getByRole("button", { name: "测试已保存配置的 API 连接", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("Embedding 与 LLM");
});

test("readable UI, persistent compact navigation, safe Markdown and stable history location at five widths", async ({
  page,
  request,
}) => {
  test.setTimeout(90000);
  const origin = "http://127.0.0.1:18765";
  const longName = "示例项目 A：" + "虚构图书目录".repeat(12);
  const first = (
    await (
      await request.post("/api/projects", {
        headers: { Origin: origin },
        data: { name: longName },
      })
    ).json()
  ).id as string;
  const second = (
    await (
      await request.post("/api/projects", {
        headers: { Origin: origin },
        data: { name: "示例项目 B（界面验收）" },
      })
    ).json()
  ).id as string;
  await request.post("/__test__/long-history/" + first);
  const persisted = (await (
    await request.get(`/api/projects/${first}/messages`)
  ).json()) as Message[];
  const early = persisted.filter((m) => m.role === "user")[3]!;
  await page.route("**/api/projects/*/messages", async (route) => {
    const response = await route.fetch();
    const rows = (await response.json()) as Message[];
    if (
      route.request().method() === "GET" &&
      route.request().url().includes(first)
    ) {
      for (const row of rows)
        if (row.role === "assistant") row.content = markdownAnswer;
      const answer = rows.find((m) => m.role === "assistant");
      if (answer)
        answer.citations = [
          {
            source: "catalog.md",
            heading: "虚构证据",
            chunk_id: "synthetic-document:synthetic-generation:0",
            document_id: "synthetic-document",
            text: "证据原文 **保留原样**，只用于虚构界面测试。",
            distance: 0.1,
            cited: true,
          },
        ];
    }
    await route.fulfill({ response, json: rows });
  });
  await page.goto("/chat");
  await page.locator("#project").selectOption(first);
  await expect(page.locator(".message")).toHaveCount(80);
  const calls = await (await request.get("/__test__/counts")).json();
  const workspaceBefore = await page.locator(".workspace").boundingBox();
  await page.getByRole("button", { name: "收起导航", exact: true }).click();
  await expect(page.locator(".app-shell")).toHaveClass(/nav-collapsed/);
  await page.screenshot({ path: "test-results/nav-collapsed.png" });
  expect(
    (await page.locator(".workspace").boundingBox())!.width,
  ).toBeGreaterThan(workspaceBefore!.width);
  await expect(
    page.getByRole("link", { name: "知识库管理", exact: true }),
  ).toHaveAttribute("title", "知识库管理");
  await page.reload();
  await expect(page.locator(".app-shell")).toHaveClass(/nav-collapsed/);
  await expect(page.locator(".message")).toHaveCount(80);
  expect(
    await page.evaluate(() =>
      localStorage.getItem("projectrevisit.nav-collapsed"),
    ),
  ).toBe("true");
  await page.getByRole("button", { name: "展开项目选择", exact: true }).click();
  await expect(page.locator("#project")).toBeVisible();
  if (
    await page
      .getByRole("button", { name: "收起推荐面板", exact: true })
      .count()
  )
    await page
      .getByRole("button", { name: "收起推荐面板", exact: true })
      .click();
  for (const width of [1920, 1440, 1024, 760, 480]) {
    await page.setViewportSize({ width, height: 900 });
    if (width <= 900)
      await expect(page.locator(".navigation")).not.toBeInViewport();
    else {
      await page.getByRole("button", { name: "收起导航", exact: true }).click();
      expect((await page.locator(".navigation").boundingBox())!.width).toBe(72);
      await page.getByRole("button", { name: "展开导航", exact: true }).click();
    }
    if (width <= 900) {
      await page.getByRole("button", { name: "打开导航", exact: true }).click();
      await expect(page.locator(".navigation")).toBeInViewport();
      await expect(page.locator("#project")).toBeVisible();
      await page
        .locator(".navigation")
        .getByRole("button", { name: "关闭导航", exact: true })
        .click();
      await expect(page.locator(".navigation")).not.toBeInViewport();
    }
    const open =
      width >= 1100
        ? page.getByRole("button", { name: "打开对话定位", exact: true })
        : page.getByRole("button", { name: "对话定位", exact: true });
    await open.click();
    const directory = page.getByRole("dialog", {
      name: "对话定位",
      exact: true,
    });
    await expect(directory.locator(".conversation-list button")).toHaveCount(
      40,
    );
    if (width >= 1100) {
      const locatorBox = (await directory.boundingBox())!;
      expect(locatorBox.y + locatorBox.height).toBeLessThanOrEqual(
        (await page.locator(".composer-area").boundingBox())!.y,
      );
    }
    await page.screenshot({ path: `test-results/locator-${width}.png` });
    const entry = directory.locator(`[data-target-id="${early.id}"]`);
    await expect(entry).toHaveAttribute("title", early.content);
    await entry.click();
    const target = page.locator(`[data-message-id="${early.id}"]`);
    await expect
      .poll(async () =>
        Math.abs(
          (await target.boundingBox())!.y -
            (await page.locator(".messages").boundingBox())!.y -
            16,
        ),
      )
      .toBeLessThan(4);
    if (width >= 1100)
      await page
        .getByRole("button", { name: "关闭对话定位", exact: true })
        .click();
    await expect(
      page.getByRole("button", { name: "↓ 返回最新消息", exact: true }),
    ).toBeVisible();
    const answer = page.locator(".markdown-body").nth(3);
    await expect(answer.locator("h1")).toHaveText("虚构图书目录复盘");
    await expect(answer.locator("strong").first()).toHaveText("加粗内容");
    await expect(answer.locator("ol li")).toHaveCount(2);
    const overflow = await answer.evaluate((el) => {
      const table = el.querySelector(".markdown-table") as HTMLElement,
        code = el.querySelector("pre") as HTMLElement;
      return {
        table: table.scrollWidth > table.clientWidth,
        code: code.scrollWidth > code.clientWidth,
        body: document.documentElement.scrollWidth <= innerWidth,
      };
    });
    expect(overflow.body).toBe(true);
    expect(overflow.code).toBe(true);
    if (width <= 1024) expect(overflow.table).toBe(true);
    expect(
      await page
        .locator(
          ".markdown-body script,.markdown-body img,.markdown-body [onclick],.markdown-body [onerror]",
        )
        .count(),
    ).toBe(0);
    expect(await page.evaluate(() => "__markdownUnsafe" in window)).toBe(false);
    await page.screenshot({ path: `test-results/ui-${width}.png` });
    await page.getByRole("button", { name: "推荐问题 ◇", exact: true }).click();
    await expect(page.locator(".recommendation-panel")).toBeVisible();
    await page
      .getByRole("button", { name: "收起推荐面板", exact: true })
      .click();
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.route(`**/api/projects/${first}/questions`, async (route) => {
    const response = await route.fetch();
    await new Promise((resolve) => setTimeout(resolve, 2000));
    await route.fulfill({ response });
  });
  await page
    .getByLabel("询问当前项目", { exact: true })
    .fill("虚构的新增复盘问题");
  await page.getByRole("button", { name: "发送 ↑", exact: true }).click();
  await expect(page.locator(".pending")).toBeVisible();
  await page.getByRole("button", { name: "打开对话定位", exact: true }).click();
  await page.locator(`[data-target-id="${early.id}"]`).click();
  await expect
    .poll(async () =>
      Math.abs(
        (await page.locator(`[data-message-id="${early.id}"]`).boundingBox())!
          .y -
          (await page.locator(".messages").boundingBox())!.y -
          16,
      ),
    )
    .toBeLessThan(4);
  await page.getByRole("button", { name: "关闭对话定位", exact: true }).click();
  const readingTop = await page
    .locator(".messages")
    .evaluate((el) => el.scrollTop);
  // The new reply arrives while the user reads an earlier question.
  await expect(page.locator(".pending")).toHaveCount(0);
  await expect(page.locator(".message")).toHaveCount(82);
  expect(
    Math.abs(
      (await page.locator(".messages").evaluate((el) => el.scrollTop)) -
        readingTop,
    ),
  ).toBeLessThan(4);
  await page.getByRole("button", { name: "打开对话定位", exact: true }).click();
  await expect(page.locator(".conversation-list button")).toHaveCount(41);
  await page.getByRole("button", { name: "关闭对话定位", exact: true }).click();
  expect(readingTop).toBeGreaterThan(0);
  await page.locator("#project").selectOption(second);
  await expect(page.locator(".message")).toHaveCount(0);
  await page.getByRole("button", { name: "打开对话定位", exact: true }).click();
  await expect(page.locator(".conversation-list button")).toHaveCount(0);
  await page.getByRole("button", { name: "关闭对话定位", exact: true }).click();
  await page.locator("#project").selectOption(first);
  await page.reload();
  await expect(page.locator(".message")).toHaveCount(82);
  await page.getByRole("button", { name: "打开对话定位", exact: true }).click();
  await expect(page.locator(`[data-target-id="${early.id}"]`)).toHaveAttribute(
    "title",
    early.content,
  );
  await page.getByRole("button", { name: "关闭对话定位", exact: true }).click();
  expect((await (await request.get("/__test__/counts")).json()).llm).toBe(
    calls.llm + 1,
  );
  const raw = (await (
    await request.get(`/api/projects/${first}/messages`)
  ).json()) as Message[];
  expect(raw.find((m) => m.id === persisted[1]!.id)?.content).toBe(
    persisted[1]!.content,
  );
  for (const [path, label] of [
    ["/", "项目概况"],
    ["/knowledge", "知识库管理"],
    ["/settings", "AI 设置"],
  ]) {
    await page.goto(path!);
    await expect(page.locator(".page h1")).toBeVisible();
    if (path === "/")
      await expect(page.locator(".project-heading")).toHaveAttribute(
        "title",
        longName,
      );
    if (path === "/knowledge")
      await expect(page.getByLabel("选择项目资料")).toBeVisible();
    if (path === "/settings")
      await expect(
        page.getByRole("heading", { name: "模型与目标地址", exact: true }),
      ).toBeVisible();
    expect(
      await page
        .locator(".page h1")
        .evaluate((el) => parseFloat(getComputedStyle(el).fontSize)),
    ).toBeGreaterThanOrEqual(22);
    await page.screenshot({
      path: `test-results/page-${path === "/" ? "overview" : path!.slice(1)}.png`,
    });
  }
});
