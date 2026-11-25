#!/usr/bin/env node

const { spawn } = require('node:child_process');
const { createInterface } = require('node:readline');

const args = process.argv.slice(2);
const command = args[0];
const version = process.env.FAKE_CLI_VERSION || '0.3.2';
const identity = process.env.FAKE_INSTALLATION_ID || 'fake-install-id';

if (command === 'health' || command === 'setup') {
  const value = {
    protocol_version: 1,
    cli_version: version,
    installation_id: identity,
    status: 'ready',
    modes: {
      fast: { ready: true, available: true, device: 'cpu' },
      balanced: { ready: true, available: true, device: 'cuda' },
      quality: { ready: false, available: true, device: 'cpu' },
    },
  };
  process.stdout.write(JSON.stringify(value));
  process.exitCode = command === 'setup' && process.env.FAKE_SETUP_CODE
    ? Number(process.env.FAKE_SETUP_CODE)
    : 0;
} else if (command === 'convert') {
  const runId = 'fake-run-' + process.pid;
  let seq = 0;
  const send = (event, data, jobId, attempt) => {
    const record = { protocol_version: 1, event, seq: ++seq, run_id: runId, data };
    if (jobId) record.job_id = jobId;
    if (attempt) record.attempt = attempt;
    const line = Buffer.from(JSON.stringify(record) + '\n');
    if (process.env.FAKE_FRAGMENT === '1') {
      for (const byte of line) process.stdout.write(Buffer.from([byte]));
    } else process.stdout.write(line);
  };
  const control = createInterface({ input: process.stdin });
  const terminal = (code) => {
    control.close();
    process.stdin.destroy();
    process.exitCode = code;
  };
  if (process.env.FAKE_MODE === 'validation-error') {
    send('run_finished', { exit_code: 2, totals: {}, error: 'invalid option' });
    terminal(2);
  } else if (process.env.FAKE_MODE === 'crash') {
    process.stderr.write('worker died: café\n');
    terminal(17);
  } else if (process.env.FAKE_MODE === 'hang') {
    spawn(process.execPath, ['-e', 'setInterval(() => {}, 1000)'], {
      stdio: 'ignore',
    });
    setInterval(() => {}, 1000);
  } else {
    const paths = args.slice(1, args.indexOf('--mode') === -1 ? undefined : args.indexOf('--mode'));
    send('run_started', { mode: args[args.indexOf('--mode') + 1], version });
    send('inputs_resolved', { count: paths.length, inputs: paths, issues: [], args });
    send('job_started', { input: paths[0] }, 'job-1', 1);
    send('job_progress', { stage: 'Layout detection' }, 'job-1', 1);
    process.stderr.write('Preparación para José.pdf\n');
    if (process.env.FAKE_MODE === 'cancel') {
      control.on('line', (line) => {
        const request = JSON.parse(line);
        if (request.protocol_version === 1 && request.command === 'cancel' && request.run_id === runId) {
          send('job_finished', { result: { status: 'cancelled' } }, 'job-1', 1);
          send('run_finished', { exit_code: 130, totals: { cancelled: 1 } });
          terminal(130);
        }
      });
    } else {
      send('warning', { code: 'GPU_FALLBACK_CPU', message: 'Using CPU' }, 'job-1', 2);
      send('job_retrying', { device: 'cpu' }, 'job-1', 2);
      send('job_finished', { result: { status: 'partial', warnings: [] } }, 'job-1', 2);
      send('run_finished', { exit_code: 1, totals: { partial: 1 } });
      terminal(1);
    }
  }
} else {
  process.stderr.write('unexpected command: ' + command + '\n');
  process.exitCode = 2;
}
