import { _electron as electron, expect, test } from "@playwright/test";
import { access, copyFile, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ui = resolve(fileURLToPath(new URL("../../", import.meta.url)));
const pkg = JSON.parse(await readFile(join(ui, "package.json"), "utf8"));
const source = fileURLToPath(new URL("../../../test-pdfs/test_document.pdf", import.meta.url));
const fixture = new URL("fake-cli.mjs", import.meta.url).href;
const image = join(ui, "assets", "icons", "sami-icon-128.png");
const desktopVersion = `v${pkg.version}`;

test("keeps the desktop version in view while scrolling without an installed CLI", async () => {
  const temporary = await mkdtemp(join(tmpdir(), "sami-desktop-version-"));
  let app;
  try {
    app = await electron.launch({
      args: [`--user-data-dir=${join(temporary, "profile")}`, ui],
      env: { ...process.env, SAMI_HOME: join(temporary, "no-cli") },
    });
    const page = await app.firstWindow();
    const version = page.locator("#app-version");
    await expect(page.locator("#health-pill")).toHaveClass(/\brepair\b/);
    await expect(version).toHaveText(desktopVersion);
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setContentSize(720, 560));
    await page.locator("#convert-button").scrollIntoViewIfNeeded();
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(0);
    await expect(version).toBeInViewport({ ratio: 1 });
  } finally {
    if (app) await app.close();
    await rm(temporary, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  }
});

test("opens the desktop app, stages a mixed batch, previews and exports the results, and cancels", async () => {
  const temporary = await mkdtemp(join(tmpdir(), "sami-desktop-"));
  const home = join(temporary, "home");
  const folder = join(temporary, "PDF folder");
  const output = join(temporary, "output");
  const exportFolder = join(temporary, "export");
  const input = join(temporary, "Informe ñ.pdf");
  const second = join(folder, "Another.pdf");
  const dropped = [join(temporary, "Dropped 1.pdf"), join(temporary, "Dropped 2.pdf")];
  const selectedCli = process.env.SAMI_TEST_REAL_CLI_HOME;
  for (const path of [home, folder, output, exportFolder]) await mkdir(path);
  await copyFile(source, input);
  await copyFile(source, second);
  await Promise.all(dropped.map(path => copyFile(source, path)));
  await writeFile(join(home, "installation.json"), JSON.stringify({
    schema_version: 1, installation_id: "demo-ui-test", executable: process.execPath,
    protocol_version: 1, cli_version: pkg.version, sami_home: home,
  }));
  const env = { ...process.env, SAMI_HOME: selectedCli || home };
  if (!selectedCli) {
    for (const command of ["health", "setup", "convert"]) {
      await writeFile(join(home, command), `import(${JSON.stringify(fixture)});\n`);
    }
    Object.assign(env, { SAMI_TEST_CLI: "1", SAMI_TEST_IMAGE: image });
  }
  let app;
  try {
    app = await electron.launch({ args: [`--user-data-dir=${join(temporary, "profile")}`, ui], env });
    const page = await app.firstWindow();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await expect(page.locator("html")).toHaveAttribute("data-sami-ready", "true");
    await expect(page.locator("#app-subtitle")).toContainText("Smart Automated Markdown Interpreter");
    const version = page.locator("#app-version");
    await expect(version).toHaveText(desktopVersion);
    await expect(page.locator("#convert-button")).toBeDisabled();
    await page.locator("#settings-button").click();
    await expect(page.locator("#settings-version")).toHaveText(desktopVersion);
    await expect(page.locator("#settings-version")).toBeVisible();
    await page.locator("#language-select").selectOption("es");
    await page.locator("#theme-select").selectOption("dark");
    await expect(page.locator("html")).toHaveAttribute("lang", "es");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.locator("#settings-done").click();
    await app.evaluate(({ dialog }, paths) => {
      dialog.showOpenDialog = async (_window, options) => ({
        canceled: false,
        filePaths: options.properties.includes("openFile") ? [paths.input]
          : options.title.includes("copiar") ? [paths.exportFolder]
            : options.title.includes("salida") ? [paths.output] : [paths.folder],
      });
    }, { input, folder, output, exportFolder });
    await page.locator("#browse-files").click();
    await page.locator("#add-folder").click();
    await page.evaluate(() => {
      const input = document.createElement("input");
      input.id = "test-drop-files";
      input.type = "file";
      input.multiple = true;
      input.hidden = true;
      document.body.append(input);
    });
    await page.locator("#test-drop-files").setInputFiles(dropped);
    await page.evaluate(() => {
      const dataTransfer = new DataTransfer();
      for (const file of document.getElementById("test-drop-files").files) dataTransfer.items.add(file);
      document.getElementById("drop-zone").dispatchEvent(new DragEvent("drop", { dataTransfer, bubbles: true }));
    });
    await expect(page.locator("#file-list")).toContainText("Informe ñ.pdf");
    await expect(page.locator("#file-list")).toContainText("PDF folder");
    await expect(page.locator("#file-list")).toContainText("Dropped 1.pdf");
    await expect(page.locator("#file-list")).toContainText("Dropped 2.pdf");
    await expect(page.locator("#run-view")).toBeHidden();
    await expect(page.locator("#convert-button")).toBeEnabled();
    await page.locator("#choose-output").click();
    await page.locator('label[for="flat-toggle"]').click();
    await expect(page.locator("#flat-toggle")).toBeChecked();
    if (selectedCli) await page.locator("#mode-select").selectOption("fast");
    await page.locator("#convert-button").click();
    if (!selectedCli) {
      await expect(page.locator("#run-view")).toBeVisible();
      await expect(version).toBeInViewport();
    }
    await expect(page.locator("#results-view")).toBeVisible();
    await expect(version).toBeInViewport();
    await expect(page.locator("#result-list")).toContainText("Informe ñ.pdf");
    await expect(page.locator("#result-list")).toContainText("Another.pdf");
    const result = page.locator("#result-list").getByText("Informe ñ.pdf", { exact: true });
    await result.click();
    if (!selectedCli) {
      await expect(page.locator("#markdown-preview")).toContainText("Conversion checked");
      await expect(page.locator("#markdown-preview .katex")).toBeVisible();
      await expect.poll(() => page.locator("#markdown-preview img").evaluate(img => img.naturalWidth)).toBeGreaterThan(0);
    }
    await page.locator("#preview-pdf-tab").click();
    await expect(page.locator("#pdf-preview")).toBeVisible();
    await expect.poll(() => page.locator("#pdf-canvas").evaluate(canvas => canvas.width)).toBeGreaterThan(300);
    if (process.env.SAMI_TEST_SCREENSHOT) await page.screenshot({ path: process.env.SAMI_TEST_SCREENSHOT });
    if (!selectedCli) {
      await page.locator("#export-result").click();
      await expect.poll(async () => {
        try {
          return await readFile(join(exportFolder, "Informe ñ", "Informe ñ.md"), "utf8");
        } catch {
          return "";
        }
      }).toContain("Conversion checked");
      await access(join(exportFolder, "Informe ñ", "Informe ñ_assets", "figure.png"));
      await page.locator("#new-batch-button").click();
      if (!(await page.locator("#file-list").textContent()).includes("Informe ñ.pdf")) {
        await page.locator("#browse-files").click();
      }
      await page.locator("#convert-button").click();
      await expect(page.locator("#run-view")).toBeVisible();
      await page.locator("#cancel-button").click();
      await expect(page.locator("#results-view")).toBeVisible();
      await expect(page.locator("#results-summary")).toContainText(/cancelad/i);
    }
    expect(errors).toEqual([]);
  } finally {
    if (app) await app.close();
    await rm(temporary, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  }
});
