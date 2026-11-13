import MarkdownIt from "markdown-it";

// Only parser-generated HTML is rendered. Raw model HTML is always escaped.
const parser = new MarkdownIt({ html: false, linkify: false, breaks: true });
parser.disable("image"); // Do not fetch model-supplied images or tracking URLs.
const validateLink = parser.validateLink.bind(parser);
parser.validateLink = (url) => {
  if (!validateLink(url)) return false;
  try {
    return ["http:", "https:", "mailto:"].includes(
      new URL(url, "http://localhost").protocol,
    );
  } catch {
    return false;
  }
};
parser.renderer.rules.link_open = (tokens, index, options, _env, renderer) => {
  tokens[index]!.attrSet("target", "_blank");
  tokens[index]!.attrSet("rel", "noopener noreferrer");
  return renderer.renderToken(tokens, index, options);
};
parser.renderer.rules.table_open = () =>
  '<div class="markdown-table" role="region" aria-label="Markdown 表格" tabindex="0"><table>';
parser.renderer.rules.table_close = () => "</table></div>";

export function renderMarkdown(source: string): string {
  return parser
    .render(source)
    .replace(/<pre>/g, '<pre tabindex="0" aria-label="代码块">');
}
