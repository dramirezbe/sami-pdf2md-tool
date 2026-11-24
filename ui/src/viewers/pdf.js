import * as pdfjs from "pdfjs-dist/build/pdf.mjs";

const localAssetDirectory = new URL("./pdfjs/", window.location.href).toString();
pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdf.worker.min.mjs", localAssetDirectory).toString();

export class PdfPreview {
  constructor({ canvas, pageLabel, zoomLabel, previousButton, nextButton, zoomInButton, zoomOutButton }) {
    this.canvas = canvas;
    this.pageLabel = pageLabel;
    this.zoomLabel = zoomLabel;
    this.context = canvas.getContext("2d");
    this.pdf = null;
    this.loadingTask = null;
    this.page = 1;
    this.scale = 1;
    this.renderTask = null;

    previousButton.addEventListener("click", () => this.setPage(this.page - 1));
    nextButton.addEventListener("click", () => this.setPage(this.page + 1));
    zoomInButton.addEventListener("click", () => this.setScale(this.scale + 0.15));
    zoomOutButton.addEventListener("click", () => this.setScale(this.scale - 0.15));
  }

  async open(url) {
    this.destroy();
    this.page = 1;
    this.scale = 1;
    const loading = pdfjs.getDocument({
      url,
      disableRange: true,
      isEvalSupported: false,
      cMapUrl: new URL("cmaps/", localAssetDirectory).toString(),
      cMapPacked: true,
      standardFontDataUrl: new URL("standard_fonts/", localAssetDirectory).toString(),
      wasmUrl: new URL("wasm/", localAssetDirectory).toString(),
      iccUrl: new URL("iccs/", localAssetDirectory).toString(),
    });
    this.loadingTask = loading;
    try {
      const pdf = await loading.promise;
      if (loading !== this.loadingTask) return;
      this.pdf = pdf;
      await this.render();
    } catch (error) {
      if (loading === this.loadingTask) throw error;
    }
  }

  async setPage(page) {
    if (!this.pdf || page < 1 || page > this.pdf.numPages) return;
    this.page = page;
    await this.render();
  }

  async setScale(scale) {
    this.scale = Math.min(2.25, Math.max(0.5, scale));
    await this.render();
  }

  async render() {
    if (!this.pdf) return;
    this.renderTask?.cancel();
    const document = this.pdf;
    const page = await document.getPage(this.page);
    if (document !== this.pdf) return;
    const viewport = page.getViewport({ scale: this.scale });
    const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
    this.canvas.width = Math.ceil(viewport.width * pixelRatio);
    this.canvas.height = Math.ceil(viewport.height * pixelRatio);
    this.canvas.style.width = `${Math.ceil(viewport.width)}px`;
    this.canvas.style.height = `${Math.ceil(viewport.height)}px`;
    this.pageLabel.textContent = `${this.page} / ${this.pdf.numPages}`;
    this.zoomLabel.textContent = `${Math.round(this.scale * 100)}%`;
    const transform = pixelRatio === 1 ? null : [pixelRatio, 0, 0, pixelRatio, 0, 0];
    this.renderTask = page.render({ canvasContext: this.context, viewport, transform });
    try {
      await this.renderTask.promise;
    } catch (error) {
      if (error?.name !== "RenderingCancelledException") throw error;
    }
  }

  destroy() {
    this.renderTask?.cancel();
    void this.loadingTask?.destroy().catch(() => {});
    this.loadingTask = null;
    this.renderTask = null;
    this.pdf = null;
  }
}
