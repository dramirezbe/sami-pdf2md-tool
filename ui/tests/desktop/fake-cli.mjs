import { copyFile, mkdir, readdir, stat, writeFile } from "node:fs/promises";
import { basename, dirname, extname, join } from "node:path";
import { createInterface } from "node:readline";
import { randomUUID } from "node:crypto";
import { setTimeout as wait } from "node:timers/promises";

const command = basename(process.argv[1] || "");
if (!process.versions.electron && process.env.SAMI_TEST_CLI === "1" &&
    ["health", "setup", "convert"].includes(command)) {
  if (command === "convert") await convert();
  else health();
  process.exit(process.exitCode || 0);
}

function health() {
  const mode = { ready: true, available: true, device: "cpu" };
  console.log(JSON.stringify({
    protocol_version: 1, cli_version: "0.3.1", installation_id: "demo-ui-test",
    status: "ready", selected_device: "cpu", warnings: [], repair_reasons: [],
    paths: { executable: process.execPath, sami_home: process.env.SAMI_HOME },
    modes: { fast: mode, balanced: mode, quality: mode },
  }));
}

async function convert() {
  const args = process.argv.slice(2);
  const mode = args[args.indexOf("--mode") + 1];
  const root = args.includes("--output") ? args[args.indexOf("--output") + 1] : null;
  const run = randomUUID();
  let seq = 0;
  const emit = (event, data, jobId) => {
    console.log(JSON.stringify({
      protocol_version: 1, run_id: run, seq: ++seq, event, data,
      ...(jobId ? { job_id: jobId, attempt: 1 } : {}),
    }));
  };
  const chosen = args.slice(0, args.indexOf("--mode"));
  const inputs = [];
  let cancelled = false;
  const control = createInterface({ input: process.stdin });
  control.on("line", line => {
    const message = JSON.parse(line);
    if (message.protocol_version === 1 && message.run_id === run && message.command === "cancel") cancelled = true;
  });
  for (const path of chosen) {
    if ((await stat(path)).isDirectory()) {
      for (const name of await readdir(path)) if (extname(name).toLowerCase() === ".pdf") inputs.push(join(path, name));
    } else inputs.push(path);
  }
  emit("run_started", { mode, default_mode: "balanced", version: "0.3.1", requested_device: "auto" });
  emit("inputs_resolved", { count: inputs.length, inputs, issues: [] });
  let finished = 0;
  for (const [index, input] of inputs.entries()) {
    const job = randomUUID();
    const result = {
      job_id: job, input_path: input, mode, engine: "marker", device: "cpu",
      status: "cancelled", output_paths: [], warnings: [], errors: [], duration_seconds: 0.5, attempts: 1,
    };
    if (!cancelled) {
      emit("job_started", { input, index: index + 1, total: inputs.length, engine: "marker", device: "cpu" }, job);
      emit("job_progress", { stage: "Reading PDF pages...", completed: null, total: null }, job);
      for (let elapsed = 0; elapsed < 650 && !cancelled; elapsed += 25) await wait(25);
    }
    if (!cancelled) {
      const name = basename(input, extname(input));
      const folder = root || dirname(input);
      const output = args.includes("--flat") ? folder : join(folder, name);
      const markdown = join(output, `${name}.md`);
      const figureFolder = args.includes("--flat") ? `${name}_assets` : "assets";
      const image = join(output, figureFolder, "figure.png");
      await mkdir(dirname(image), { recursive: true });
      await copyFile(process.env.SAMI_TEST_IMAGE, image);
      await writeFile(markdown, `# Conversion checked\n\nThe sum is $x^2$.\n\n![Figure](${encodeURI(figureFolder)}/figure.png)\n`);
      result.status = "succeeded";
      result.output_paths = [markdown, image];
      finished += 1;
    }
    emit("job_finished", { result }, job);
  }
  const code = cancelled ? 130 : 0;
  emit("run_finished", {
    totals: { succeeded: finished, partial: 0, failed: 0, cancelled: inputs.length - finished },
    duration_seconds: 1.5, input_issue_count: 0, exit_code: code,
  });
  process.exitCode = code;
  control.close();
}
