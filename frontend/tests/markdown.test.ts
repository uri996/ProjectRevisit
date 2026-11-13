import { describe, expect, it } from "vitest";
import { renderMarkdown } from "../src/markdown";
import { markdownAnswer } from "./fixtures";

function render(source: string) {
  const host = document.createElement("div");
  host.innerHTML = renderMarkdown(source);
  return host;
}
describe("safe Markdown rendering", () => {
  it("renders Chinese, headings, emphasis, lists, quotations, tables and code without changing the source", () => {
    const original = markdownAnswer;
    const host = render(markdownAnswer);
    expect(host.querySelector("h1")?.textContent).toBe("虚构图书目录复盘");
    expect(host.querySelector("strong")?.textContent).toBe("加粗内容");
    expect(host.querySelector("em")?.textContent).toBe("斜体内容");
    expect(host.querySelectorAll("ul li").length).toBeGreaterThanOrEqual(3);
    expect(host.querySelectorAll("ol li")).toHaveLength(2);
    expect(host.querySelector("blockquote")?.textContent).toContain(
      "虚构的引用",
    );
    expect(host.querySelector(".markdown-table table")).not.toBeNull();
    expect(
      host.querySelector("pre code.language-typescript")?.textContent,
    ).toContain("fictionalCatalog");
    expect(host.querySelector("a")?.getAttribute("rel")).toBe(
      "noopener noreferrer",
    );
    expect(markdownAnswer).toBe(original);
  });
  it("shows ordinary text and line breaks naturally", () => {
    const host = render("中文普通文本\n另一行，没有 Markdown。");
    expect(host.querySelector("p")?.textContent).toContain("中文普通文本");
    expect(host.querySelector("br")).not.toBeNull();
  });
  it.each([
    '<script>alert(1)</script><svg onload="alert(1)"></svg>',
    '<a href="javascript:alert(1)" onclick="alert(1)">unsafe</a>',
    "[unsafe](javascript:alert(1))",
    "[unsafe](jav&#x61;script:alert(1))",
    "[unsafe](data:text/html;base64,PHNjcmlwdD4=)",
    "[unsafe](file:///private/data)",
    "![tracking](https://example.com/track)",
  ])(
    "does not create executable HTML or automatic remote images: %s",
    (source) => {
      const host = render(source);
      expect(
        host.querySelector("script, svg, img, iframe, object, embed"),
      ).toBeNull();
      for (const element of host.querySelectorAll("*")) {
        expect(
          element.getAttributeNames().some((name) => /^on/i.test(name)),
        ).toBe(false);
        expect(element.getAttribute("href") || "").not.toMatch(
          /^(javascript|vbscript|data|file|blob):/i,
        );
      }
    },
  );
});
