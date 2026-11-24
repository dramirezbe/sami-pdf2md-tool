import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { Documents } from "../src/documents.js";

test("previews and grouped exports use only selected inputs and published paths", async () => {
  const root = await mkdtemp(join(tmpdir(), "sami-documents-"));
  try {
    const docs = new Documents();
    const pdf = join(root, "Fuente ñ.pdf");
    const output = join(root, "output");
    const destination = join(root, "destination");
    const md = join(output, "Fuente ñ.md");
    const assets = join(output, "Fuente ñ_assets");
    const chart = join(assets, "figura.png");
    await mkdir(assets, { recursive: true });
    await mkdir(destination);
    await writeFile(pdf, "%PDF-1.4");
    await writeFile(md, "# Results\n![Figure](Fuente%20%C3%B1_assets/figura.png)");
    await writeFile(chart, "image");
    await assert.rejects(docs.loadPreview({ pdfPath: pdf }), /Choose a PDF/);
    assert.throws(() => docs.validateRequest({ inputs: [pdf] }), /Choose the files/);
    await docs.selectInputs([pdf]);
    docs.selectOutput(output);
    const request = docs.validateRequest({ inputs: [pdf], output, mode: "balanced", flat: true });
    docs.beginRun(request);
    docs.addEvent({
      event: "job_finished", data: { result: { status: "succeeded", output_paths: [md, chart, pdf] } },
    });

    const preview = await docs.loadPreview({ pdfPath: pdf, markdownPath: md });
    assert.match(preview.markdown, /Results/);
    assert.equal(docs.previewResource(preview.pdfUrl).type, "application/pdf");
    assert.deepEqual(Object.keys(preview.resourceUrls), ["Fuente ñ_assets/figura.png"]);
    assert.equal(docs.previewResource(preview.resourceUrls["Fuente ñ_assets/figura.png"]).file, chart);
    await docs.loadPreview();
    assert.equal(docs.previewResource(preview.pdfUrl), undefined);
    assert.deepEqual(await docs.dragPaths(md), [md, assets]);

    const first = await docs.exportResult(md, destination);
    const second = await docs.exportResult(md, destination);
    assert.notEqual(first, second);
    assert.equal(await readFile(join(first, "Fuente ñ_assets", "figura.png"), "utf8"), "image");
    assert.match(await readFile(join(second, "Fuente ñ.md"), "utf8"), /Results/);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("folder inputs get leaf preview permissions from CLI discovery", async () => {
  const docs = new Documents();
  const parent = join(tmpdir(), "sami-folder");
  const path = join(parent, "foobar.pdf");
  await docs.selectInputs([parent]);
  await assert.rejects(docs.loadPreview({ pdfPath: path }), /Choose a PDF/);
  docs.addEvent({ event: "inputs_resolved", data: { inputs: [path] } });
  assert.equal(docs.previewResource((await docs.loadPreview({ pdfPath: path })).pdfUrl).file, path);
});
