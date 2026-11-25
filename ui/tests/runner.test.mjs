import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

import { CliRunner, CLI_VERSION } from '../src/cli-runner.js';

const fixture = fileURLToPath(new URL('./fixtures/fake-sami-cli.cjs', import.meta.url));

async function installation(t, { version = CLI_VERSION, protocol = 1, identity = 'fake-install-id' } = {}) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'sami-ui-runner-'));
  let runner;
  t.after(async () => {
    await runner?.shutdown();
    await rm(root, { recursive: true, force: true, maxRetries: 12, retryDelay: 100 });
  });
  const home = path.join(root, 'sami home');
  await mkdir(home, { recursive: true });
  const executable = process.execPath;
  await writeFile(path.join(home, 'installation.json'), JSON.stringify({
    schema_version: 1,
    installation_id: identity,
    cli_version: version,
    protocol_version: protocol,
    executable,
  }));
  runner = new CliRunner({
    env: {
      ...process.env,
      SAMI_HOME: home,
      FAKE_CLI_VERSION: version,
      FAKE_INSTALLATION_ID: identity,
    },
    stallMs: 40,
    activityIntervalMs: 10,
    cancelTimeoutMs: 120,
    killTimeoutMs: 80,
    spawnProcess: (program, args, options) => program.toLowerCase().endsWith('taskkill.exe')
      ? spawn(program, args, options)
      : spawn(process.execPath, [fixture, ...args], options),
  });
  return { root, home, executable, runner };
}

test('health checks the absolute launcher identity, exact version, protocol, and mode readiness', async (t) => {
  const { runner, executable } = await installation(t);
  const health = await runner.health();
  assert.equal(health.executable, executable);
  assert.equal(health.installation_id, 'fake-install-id');
  assert.equal(health.canConvert, true);
  assert.equal(health.modes.fast.ready, true);
  assert.equal(health.modes.quality.ready, false);
});

test('rejects a mismatched CLI version or protocol in the installation record', async (t) => {
  const first = await installation(t, { version: '0.2.3' });
  await assert.rejects(first.runner.health(), { code: 'CLI_VERSION_UNSUPPORTED' });

  const second = await installation(t, { protocol: 2 });
  await assert.rejects(second.runner.health(), { code: 'INSTALLATION_RECORD_INCOMPATIBLE' });
});

test('setup invokes the installed executable and returns a verified health profile', async (t) => {
  const { runner } = await installation(t);
  const setup = await runner.setup();
  assert.equal(setup.status, 'ready');
  assert.equal(setup.modes.balanced.ready, true);
});

test('spawns a single batch with argument boundaries, streams events, and preserves result envelopes', async (t) => {
  const { runner } = await installation(t);
  runner.env.FAKE_FRAGMENT = '1';
  const events = [];
  const diagnostics = [];
  const states = [];
  runner.on('event', (event) => events.push(event));
  runner.on('diagnostic', (diagnostic) => diagnostics.push(diagnostic));
  runner.on('state', (state) => states.push(state));
  const operation = await runner.start({
    inputs: ['C:\\PDFs\\radio env ñ.pdf', 'C:\\PDFs\\second.pdf'],
    mode: 'balanced',
    recursive: true,
    flat: true,
    output: 'C:\\PDFs\\output folder',
  });
  const result = await operation.completion;
  assert.equal(result.runId, 'fake-run-' + operation.child.pid);
  assert.equal(result.event.data.exit_code, 1);
  assert.deepEqual(events.map((event) => event.seq), [1, 2, 3, 4, 5, 6, 7, 8]);
  assert.deepEqual(events[1].data.inputs, ['C:\\PDFs\\radio env ñ.pdf', 'C:\\PDFs\\second.pdf']);
  assert.equal(events[1].data.args.includes('C:\\PDFs\\output folder'), true);
  assert.equal(events[5].event, 'job_retrying');
  assert.equal(diagnostics.some((item) => item.message.includes('José')), true);
  assert.equal(states.some((state) => state.phase === 'retrying'), true);
});

test('treats a terminal event as authoritative when validation fails before run_started', async (t) => {
  const { runner } = await installation(t);
  runner.env.FAKE_MODE = 'validation-error';
  const events = [];
  runner.on('event', (event) => events.push(event));
  const operation = await runner.start({ inputs: ['paper.pdf'] });
  const result = await operation.completion;
  assert.equal(result.runId.startsWith('fake-run-'), true);
  assert.equal(result.event.event, 'run_finished');
  assert.equal(result.exitCode, 2);
  assert.deepEqual(events.map((event) => event.event), ['run_finished']);
});

test('cancellation sends a protocol v1 command with the active run ID', async (t) => {
  const { runner } = await installation(t);
  runner.env.FAKE_MODE = 'cancel';
  const operation = await runner.start({ inputs: ['paper.pdf'] });
  const cancellation = await runner.cancel();
  const result = await operation.completion;
  assert.equal(cancellation.cancelled, true);
  assert.equal(cancellation.runId, null);
  assert.equal(result.exitCode, 130);
  assert.equal(result.event.event, 'run_finished');
  assert.equal(result.event.data.totals.cancelled, 1);
});

test('stall activity reports elapsed time and missing updates while the CLI is active', async (t) => {
  const { runner } = await installation(t);
  runner.env.FAKE_MODE = 'cancel';
  runner.cancelTimeoutMs = 1_000;
  const activity = [];
  runner.on('activity', (entry) => activity.push(entry));
  const operation = await runner.start({ inputs: ['paper.pdf'] });
  await new Promise((resolve) => setTimeout(resolve, 100));
  assert.equal(activity.some((entry) => entry.elapsedMs > 0), true);
  assert.equal(activity.some((entry) => entry.waiting), true);
  await runner.cancel();
  await operation.completion;
});

test('cancellation timeout terminates the owned CLI and reports a missing terminal event', async (t) => {
  const { runner } = await installation(t);
  runner.env.FAKE_MODE = 'hang';
  const states = [];
  runner.on('state', (state) => states.push(state));
  const operation = await runner.start({ inputs: ['paper.pdf'] });
  await runner.cancel();
  await assert.rejects(operation.completion, (error) => {
    assert.ok(['CLI_CRASHED', 'CLI_TERMINAL_EVENT_MISSING'].includes(error.code));
    return true;
  });
  assert.equal(states.some((state) => state.phase === 'stopping'), true);
});

test('a CLI crash rejects the operation and retains useful stderr', async (t) => {
  const { runner } = await installation(t);
  runner.env.FAKE_MODE = 'crash';
  await assert.rejects((async () => {
    const operation = await runner.start({ inputs: ['paper.pdf'] });
    await operation.completion;
  })(), (error) => {
    assert.equal(error.code, 'CLI_CRASHED');
    assert.match(error.stderr, /café/);
    return true;
  });
});
