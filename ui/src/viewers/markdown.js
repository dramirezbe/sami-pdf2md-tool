import MarkdownIt from "markdown-it";
import texmath from "markdown-it-texmath";
import katex from "katex";
import DOMPurify from "dompurify";

const markdown = new MarkdownIt({
  html: true,
  linkify: true,
  breaks: false,
  typographer: true,
  highlight: null,
});

markdown.use(texmath, { engine: katex, delimiters: ["dollars", "brackets"] });

const tableTags = ["table", "caption", "thead", "tbody", "tfoot", "tr", "th", "td", "br", "em", "strong", "code"];
for (const rule of ["html_block", "html_inline"]) {
  markdown.renderer.rules[rule] = (tokens, index) => DOMPurify.sanitize(tokens[index].content, {
    ALLOWED_TAGS: tableTags,
    ALLOWED_ATTR: ["colspan", "rowspan", "scope"],
  });
}

function safeRelativePath(value) {
  if (typeof value !== "string" || !value || value.includes("\0")) return null;
  if (/^(?:[a-z][a-z0-9+.-]*:|\/|\\)/i.test(value)) return null;

  try {
    const decoded = decodeURIComponent(value).replaceAll("\\", "/");
    const segments = decoded.split("/");
    if (segments.some((segment) => segment === ".." || segment === ".")) return null;
    return segments.filter(Boolean).join("/");
  } catch {
    return null;
  }
}

function resourceUrl(relativePath, resources) {
  const safePath = safeRelativePath(relativePath);
  if (!safePath) return null;

  for (const [key, url] of Object.entries(resources ?? {})) {
    if (safeRelativePath(key) === safePath && typeof url === "string" && url.startsWith("sami-doc://preview/")) {
      return url;
    }
  }
  return null;
}

function mapDocumentResources(tokens, resources, missingLabel) {
  for (const token of tokens) {
    if (token.type === "inline" && token.children) {
      mapDocumentResources(token.children, resources, missingLabel);
      continue;
    }

    if (token.type !== "image" && token.type !== "link_open") continue;
    const destination = token.attrGet("src") ?? token.attrGet("href");
    if (!destination) continue;

    if (token.type === "image") {
      const url = resourceUrl(destination, resources);
      if (url) {
        token.attrSet("src", url);
        token.attrSet("alt", token.content || missingLabel);
      } else {
        token.attrSet("src", "");
        token.attrSet("alt", missingLabel);
        token.attrJoin("class", "missing-resource-image");
      }
      continue;
    }

    if (/^https?:\/\//i.test(destination)) {
      token.attrSet("target", "_blank");
      token.attrSet("rel", "noopener noreferrer");
      continue;
    }
    if (destination.startsWith("mailto:")) continue;

    const url = resourceUrl(destination, resources);
    if (url) {
      token.attrSet("href", url);
    } else if (!destination.startsWith("#")) {
      token.attrSet("href", "#");
      token.attrSet("data-sami-missing-link", "true");
    }
  }
}

export function renderMarkdown(source, resources, missingLabel) {
  const tokens = markdown.parse(source, {});
  mapDocumentResources(tokens, resources, missingLabel);
  const rendered = markdown.renderer.render(tokens, markdown.options, {});
  return DOMPurify.sanitize(rendered, {
    ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto):|sami-doc:|#)/i,
    ADD_ATTR: ["target", "rel", "data-sami-missing-link"],
  });
}
