import { copyFile, mkdir, readFile, realpath, rm, stat } from "node:fs/promises";
import { basename, dirname, extname, isAbsolute, join, normalize, relative, sep } from "node:path";
import { randomUUID } from "node:crypto";

const imageTypes = new Map([
  [".png", "image/png"], [".jpg", "image/jpeg"], [".jpeg", "image/jpeg"],
  [".gif", "image/gif"], [".webp", "image/webp"], [".bmp", "image/bmp"],
  [".svg", "image/svg+xml"], [".avif", "image/avif"],
]);

function key(path) {
  const normalized = normalize(path);
  return process.platform === "win32" ? normalized.toLowerCase() : normalized;
}

export function relativeInside(parent, file) {
  const path = relative(parent, file);
  if (!path || path === ".." || path.startsWith(`..${sep}`) || isAbsolute(path)) {
    throw new Error("File must be inside the result folder.");
  }
  return path;
}

function contentType(file) {
  const extension = extname(file).toLowerCase();
  return extension === ".pdf" ? "application/pdf" : imageTypes.get(extension);
}

export class Documents {
  #selected = new Set();
  #outputFolders = new Set();
  #pdfs = new Set();
  #results = new Map();
  #previewFiles = new Map();
  #flat = false;

  async selectInputs(paths) {
    const selected = [];
    for (const path of paths) {
      if (typeof path !== "string" || !isAbsolute(path)) continue;
      const absolute = normalize(path);
      this.#selected.add(key(absolute));
      if (extname(absolute).toLowerCase() === ".pdf") {
        this.#pdfs.add(key(absolute));
        try {
          this.#pdfs.add(key(await realpath(absolute)));
        } catch {
          // The CLI reports inaccessible inputs with the other selection issues.
        }
      }
      selected.push(absolute);
    }
    return selected;
  }

  selectOutput(path) {
    this.#outputFolders.add(key(path));
    return path;
  }

  validateRequest(request) {
    if (!request || !Array.isArray(request.inputs) || !request.inputs.length ||
        request.inputs.some(path => typeof path !== "string" || !this.#selected.has(key(path)))) {
      throw new Error("Choose the files or folders to convert first.");
    }
    if (request.output != null && (typeof request.output !== "string" ||
        !this.#outputFolders.has(key(request.output)))) {
      throw new Error("Choose the output folder first.");
    }
    return {
      inputs: request.inputs.map(path => normalize(path)),
      output: request.output || null,
      mode: request.mode,
      recursive: request.recursive === true,
      flat: request.flat === true,
    };
  }

  beginRun({ flat }) {
    this.#flat = flat;
  }

  addEvent(event) {
    if (event.event === "inputs_resolved" && Array.isArray(event.data.inputs)) {
      for (const path of event.data.inputs) {
        if (typeof path === "string" && isAbsolute(path)) this.#pdfs.add(key(path));
      }
    }
    if (event.event !== "job_finished") return;
    const result = event.data.result;
    if (!result || !["succeeded", "partial"].includes(result.status)) return;
    const [markdown, ...assets] = result.output_paths || [];
    if (typeof markdown !== "string" || !isAbsolute(markdown) || extname(markdown).toLowerCase() !== ".md") return;
    // The CLI returns Markdown first. Each resource must be under that folder.
    const resources = assets.filter(path => {
      if (typeof path !== "string" || !isAbsolute(path)) return false;
      try {
        relativeInside(dirname(markdown), path);
        return true;
      } catch {
        return false;
      }
    });
    this.#results.set(key(markdown), { markdown, resources, flat: this.#flat });
  }

  result(markdownPath) {
    const result = typeof markdownPath === "string" && this.#results.get(key(markdownPath));
    if (!result) throw new Error("Choose a published result first.");
    return result;
  }

  async loadPreview({ pdfPath, markdownPath } = {}) {
    const approved = new Map();
    const resourceUrls = Object.create(null);
    const approve = file => {
      const type = contentType(file);
      if (!type) return null;
      const id = randomUUID();
      approved.set(id, { file, type });
      return `sami-doc://preview/${id}`;
    };
    let pdfUrl = null;
    if (pdfPath) {
      if (typeof pdfPath !== "string" || !this.#pdfs.has(key(pdfPath))) throw new Error("Choose a PDF first.");
      pdfUrl = approve(pdfPath);
    }
    let markdown = null;
    if (markdownPath) {
      const result = this.result(markdownPath);
      markdown = await readFile(result.markdown, "utf8");
      for (const file of result.resources) {
        const url = approve(file);
        if (url) resourceUrls[relativeInside(dirname(result.markdown), file).split(sep).join("/")] = url;
      }
    }
    this.#previewFiles = approved;
    return { pdfUrl, markdown, resourceUrls };
  }

  previewResource(url) {
    const request = new URL(url);
    return request.hostname === "preview" && this.#previewFiles.get(request.pathname.slice(1));
  }

  async dragPaths(markdownPath) {
    const result = this.result(markdownPath);
    if (!result.resources.length) return [result.markdown];
    const folder = dirname(result.markdown);
    if (!result.flat) return [folder];
    const topLevel = new Set(result.resources.map(file => join(folder, relativeInside(folder, file).split(sep)[0])));
    return [result.markdown, ...topLevel];
  }

  async exportResult(markdownPath, folder) {
    const result = this.result(markdownPath);
    const stem = basename(result.markdown, extname(result.markdown));
    const parent = dirname(result.markdown);
    if (!(await stat(folder)).isDirectory()) throw new Error("Choose a folder for the export.");
    let destination = join(folder, stem);
    for (let number = 2; ; number += 1) {
      try {
        await mkdir(destination);
        break;
      } catch (error) {
        if (error.code !== "EEXIST") throw error;
        destination = join(folder, `${stem}_${number}`);
      }
    }
    try {
      for (const source of [...result.resources, result.markdown]) {
        const target = join(destination, relativeInside(parent, source));
        await mkdir(dirname(target), { recursive: true });
        await copyFile(source, target);
      }
      return destination;
    } catch (error) {
      await rm(destination, { recursive: true, force: true });
      throw error;
    }
  }
}
