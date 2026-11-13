import { test, expect } from "@playwright/test";
import { Buffer } from "node:buffer";

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
