import { build } from "esbuild";
import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const source = join(root, "src");
const dist = join(root, "dist");
const dependencies = join(root, "node_modules");
const pdf = join(dependencies, "pdfjs-dist");
const [manifest, index] = await Promise.all([
  readFile(join(root, "package.json"), "utf8"),
  readFile(join(source, "index.html"), "utf8"),
]);
const { version } = JSON.parse(manifest);

await rm(dist, { recursive: true, force: true });
await mkdir(join(dist, "pdfjs"), { recursive: true });
await mkdir(join(dist, "vendor", "katex"), { recursive: true });

await Promise.all([
  build({
    entryPoints: [join(source, "renderer.js")],
    outfile: join(dist, "renderer.js"),
    bundle: true,
    format: "esm",
    platform: "browser",
    target: "es2024",
    legalComments: "eof",
    minify: true,
  }),
  writeFile(join(dist, "index.html"), index.replaceAll("{{SAMI_VERSION}}", version)),
  cp(join(source, "styles.css"), join(dist, "styles.css")),
  cp(join(source, "styles"), join(dist, "styles"), { recursive: true }),
  cp(join(root, "assets", "icons"), join(dist, "assets", "icons"), { recursive: true }),
  cp(join(pdf, "build", "pdf.worker.min.mjs"), join(dist, "pdfjs", "pdf.worker.min.mjs")),
  cp(join(pdf, "cmaps"), join(dist, "pdfjs", "cmaps"), { recursive: true }),
  cp(join(pdf, "iccs"), join(dist, "pdfjs", "iccs"), { recursive: true }),
  cp(join(pdf, "standard_fonts"), join(dist, "pdfjs", "standard_fonts"), { recursive: true }),
  cp(join(pdf, "wasm"), join(dist, "pdfjs", "wasm"), { recursive: true }),
  cp(join(dependencies, "katex", "dist", "katex.min.css"), join(dist, "vendor", "katex", "katex.min.css")),
  cp(join(dependencies, "katex", "dist", "fonts"), join(dist, "vendor", "katex", "fonts"), { recursive: true }),
]);
