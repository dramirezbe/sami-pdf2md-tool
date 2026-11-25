import { EventEmitter } from 'node:events';
import { spawn as nodeSpawn } from 'node:child_process';
import { StringDecoder } from 'node:string_decoder';
import { homedir } from 'node:os';
import path from 'node:path';
import { readFile } from 'node:fs/promises';

export const CLI_VERSION = '0.3.2';
export const PROTOCOL_VERSION = 1;

const MODES = new Set(['fast', 'balanced', 'quality']);
const DEFAULT_STALL_MS = 30_000;
const DEFAULT_ACTIVITY_INTERVAL_MS = 1_000;
const DEFAULT_CANCEL_TIMEOUT_MS = 15_000;
const DEFAULT_KILL_TIMEOUT_MS = 2_000;
const MAX_DIAGNOSTIC_BYTES = 64 * 1024;
const MAX_MANAGEMENT_OUTPUT_BYTES = 1024 * 1024;
const MAX_PROTOCOL_LINE_BYTES = 2 * 1024 * 1024;
const MAX_STDERR_LINE_CHARS = 8 * 1024;

export class CliRunnerError extends Error {
  constructor(message, { code = 'CLI_RUNNER_ERROR', cause, ...details } = {}) {
    super(message, { cause });
    this.name = 'CliRunnerError';
    this.code = code;
    Object.assign(this, details);
  }
}

export class CliRunner extends EventEmitter {
  constructor({
    env = process.env,
    platform = process.platform,
    spawnProcess = nodeSpawn,
    cliVersion = CLI_VERSION,
    stallMs = DEFAULT_STALL_MS,
    activityIntervalMs = DEFAULT_ACTIVITY_INTERVAL_MS,
    cancelTimeoutMs = DEFAULT_CANCEL_TIMEOUT_MS,
    killTimeoutMs = DEFAULT_KILL_TIMEOUT_MS,
  } = {}) {
    super();
    this.env = { ...env };
    this.platform = platform;
    this.spawnProcess = spawnProcess;
    this.cliVersion = cliVersion;
    this.stallMs = stallMs;
    this.activityIntervalMs = activityIntervalMs;
    this.cancelTimeoutMs = cancelTimeoutMs;
    this.killTimeoutMs = killTimeoutMs;
    this.active = null;
    this.reserving = false;
    this.closing = false;
  }

  get home() {
    return path.resolve(this.env.SAMI_HOME || path.join(homedir(), '.sami'));
  }

  async installation() {
    const recordPath = path.join(this.home, 'installation.json');
    let record;
    try {
      record = JSON.parse(await readFile(recordPath, 'utf8'));
    } catch (cause) {
      throw new CliRunnerError(
        'SAMI is not registered. Install the CLI or run its installer again.',
        { code: 'INSTALLATION_RECORD_UNAVAILABLE', cause, recordPath },
      );
    }

    if (!record || typeof record !== 'object' || Array.isArray(record)) {
      throw new CliRunnerError('The SAMI installation record is invalid.', {
        code: 'INSTALLATION_RECORD_INVALID',
        recordPath,
      });
    }
    if (record.cli_version !== this.cliVersion) {
      throw new CliRunnerError(
        'The desktop app requires SAMI CLI ' + this.cliVersion + '. Installed version: ' + (record.cli_version || 'unknown') + '.',
        { code: 'CLI_VERSION_UNSUPPORTED', installedVersion: record.cli_version, requiredVersion: this.cliVersion },
      );
    }
    if (record.protocol_version !== PROTOCOL_VERSION
      || typeof record.installation_id !== 'string'
      || !record.installation_id.trim()) {
      throw new CliRunnerError('The SAMI installation record has an unsupported identity or protocol.', {
        code: 'INSTALLATION_RECORD_INCOMPATIBLE',
      });
    }
    if (!this._isAbsolute(record.executable)) {
      throw new CliRunnerError('The registered SAMI executable path must be absolute.', {
        code: 'CLI_PATH_INVALID',
      });
    }
    return { record, executable: record.executable, recordPath };
  }

  async health() {
    this._reserveOperation();
    try {
    const installation = await this.installation();
    this.emit('state', { phase: 'checking-health' });
    const result = await this._runManagement(installation, ['health', '--json'], 'Checking SAMI readiness');
    const health = this._parseManagementJson(result.stdout, 'health');
    if (health.protocol_version !== PROTOCOL_VERSION
      || health.cli_version !== this.cliVersion
      || health.installation_id !== installation.record.installation_id) {
      throw new CliRunnerError('The installed CLI returned an incompatible health response.', {
        code: 'CLI_HEALTH_INCOMPATIBLE',
        health,
      });
    }
    if (!health.modes || typeof health.modes !== 'object') {
      throw new CliRunnerError('The installed CLI returned an invalid health response.', {
        code: 'CLI_HEALTH_INVALID',
      });
    }
    const modes = Object.fromEntries([...MODES].map((mode) => {
      const status = health.modes[mode] || {};
      return [mode, { ...status, ready: status.ready === true, available: status.available === true }];
    }));
    const normalized = {
      ...health,
      modes,
      executable: installation.executable,
      canConvert: Object.values(modes).some((mode) => mode.ready),
    };
    this.emit('state', { phase: normalized.status, health: normalized });
    return normalized;
    } finally { this.reserving = false; }
  }

  async setup() {
    this._reserveOperation();
    try {
    const installation = await this.installation();
    this.emit('state', { phase: 'preparing', message: 'Preparing SAMI' });
    const result = await this._runManagement(installation, ['setup', '--json'], 'Preparing SAMI');
    const setup = this._parseManagementJson(result.stdout, 'setup');
    if (setup.status !== 'repair_required' && (setup.protocol_version !== PROTOCOL_VERSION
      || setup.cli_version !== this.cliVersion
      || setup.installation_id !== installation.record.installation_id)) {
      throw new CliRunnerError('SAMI setup returned an incompatible response.', {
        code: 'CLI_SETUP_INCOMPATIBLE',
        setup,
      });
    }
    this.emit('state', { phase: setup.status, setup });
    return setup;
    } finally { this.reserving = false; }
  }

  async start({ inputs, mode = 'balanced', recursive = false, flat = false, output } = {}) {
    if (this.closing) {
      throw new CliRunnerError('The SAMI window is closing.', { code: 'RUNNER_CLOSING' });
    }
    if (this.active || this.reserving) {
      throw new CliRunnerError('A SAMI operation is already running.', { code: 'OPERATION_IN_PROGRESS' });
    }
    if (!Array.isArray(inputs) || inputs.length === 0
      || inputs.some((input) => typeof input !== 'string' || !input.trim())) {
      throw new CliRunnerError('Choose at least one PDF or folder.', { code: 'INPUTS_REQUIRED' });
    }
    if (!MODES.has(mode)) {
      throw new CliRunnerError('Unsupported conversion mode: ' + mode, { code: 'MODE_UNSUPPORTED' });
    }

    this.reserving = true;
    let installation;
    try { installation = await this.installation(); }
    catch (error) { this.reserving = false; throw error; }
    const args = ['convert', ...inputs, '--mode', mode, '--json', '--control-stdin'];
    if (recursive) args.push('--recursive');
    if (flat) args.push('--flat');
    if (output) args.push('--output', output);
    let operation;
    try {
      operation = this._spawn(installation, args, {
        phase: 'starting',
        label: 'Starting conversion',
        controlStdin: true,
      });
    } finally { this.reserving = false; }
    this.emit('state', { phase: 'starting', mode, inputs: [...inputs] });
    return { completion: operation.completion, child: operation.child };
  }

  async cancel() {
    const operation = this.active;
    if (!operation) return { cancelled: false, reason: 'idle' };
    if (operation.cancelRequested) return { cancelled: true, runId: operation.runId };
    operation.cancelRequested = true;
    operation.cancelTimer = setTimeout(() => this._forceClose(operation), this.cancelTimeoutMs);
    this._setPhase(operation, 'cancelling', { runId: operation.runId });
    this._sendCancel(operation);
    return { cancelled: true, runId: operation.runId };
  }

  async shutdown() {
    this.closing = true;
    while (this.reserving) await new Promise((resolve) => setImmediate(resolve));
    if (!this.active) return;
    await this.cancel();
    const operation = this.active;
    if (!operation) return;
    await Promise.race([
      operation.completion,
      new Promise((resolve) => setTimeout(resolve, this.cancelTimeoutMs + this.killTimeoutMs + 100)),
    ]).catch(() => {});
    if (this.active === operation) await this._forceClose(operation);
  }

  _spawn(installation, args, { phase, label, controlStdin }) {
    let child;
    try {
      child = this.spawnProcess(installation.executable, args, {
        cwd: this.home,
        env: this.env,
        shell: false,
        windowsHide: true,
        detached: this.platform !== 'win32',
        stdio: ['pipe', 'pipe', 'pipe'],
      });
    } catch (cause) {
      throw new CliRunnerError('Could not start the installed SAMI CLI.', {
        code: 'CLI_SPAWN_FAILED',
        cause,
        executable: installation.executable,
      });
    }

    let resolveCompletion;
    let rejectCompletion;
    const completion = new Promise((resolve, reject) => {
      resolveCompletion = resolve;
      rejectCompletion = reject;
    });
    const operation = {
      child,
      installation,
      controlStdin,
      management: !controlStdin,
      phase,
      label,
      started: false,
      runId: null,
      lastSequence: 0,
      startedAt: Date.now(),
      lastActivityAt: Date.now(),
      stage: label,
      cancelRequested: false,
      cancelSent: false,
      cancelTimer: null,
      interval: null,
      stdoutDecoder: new StringDecoder('utf8'),
      stderrDecoder: new StringDecoder('utf8'),
      stdoutBuffer: '',
      stderrBuffer: '',
      stderrTail: '',
      stdout: '',
      runFinished: null,
      exitCode: null,
      completion,
      resolveCompletion,
      rejectCompletion,
    };
    this.active = operation;
    child.stdout.on('data', (chunk) => this._readStdout(operation, chunk));
    child.stderr.on('data', (chunk) => this._readStderr(operation, chunk));
    child.once('error', (error) => this._failOperation(operation,
      this._failure(operation, 'CLI_SPAWN_FAILED', 'SAMI stopped unexpectedly.', error)));
    child.once('close', (code, signal) => this._finishOperation(operation, code, signal));
    operation.interval = setInterval(() => this._emitActivity(operation), this.activityIntervalMs);
    operation.interval.unref?.();
    this._setPhase(operation, phase, { label });
    return { completion, child };
  }

  _readStdout(operation, chunk) {
    if (this.active !== operation) return;
    const decoded = operation.stdoutDecoder.write(chunk);
    operation.lastActivityAt = Date.now();
    if (operation.management) {
      if (Buffer.byteLength(operation.stdout, 'utf8') + Buffer.byteLength(decoded, 'utf8') > MAX_MANAGEMENT_OUTPUT_BYTES) {
        this._failOperation(operation, this._failure(
          operation,
          'CLI_MANAGEMENT_OUTPUT_TOO_LARGE',
          'SAMI returned more diagnostic data than this app can process.',
        ));
        return;
      }
      operation.stdout += decoded;
      return;
    }
    operation.stdoutBuffer += decoded;
    if (operation.stdoutBuffer.split('\n').some((line) => Buffer.byteLength(line, 'utf8') > MAX_PROTOCOL_LINE_BYTES)) {
      this._failOperation(operation, this._failure(
        operation,
        'CLI_PROTOCOL_LINE_TOO_LARGE',
        'SAMI returned an oversized progress message.',
      ));
      return;
    }
    const lines = operation.stdoutBuffer.split('\n');
    operation.stdoutBuffer = lines.pop();
    for (const raw of lines) this._consumeEventLine(operation, raw.replace(/\r$/, ''));
  }

  _consumeEventLine(operation, line) {
    if (!line.trim()) return;
    let event;
    try {
      event = JSON.parse(line);
    } catch (cause) {
      this._failOperation(operation, this._failure(
        operation, 'CLI_PROTOCOL_INVALID_JSON', 'SAMI sent an invalid progress message.', cause,
      ));
      return;
    }
    if (!event || typeof event !== 'object' || Array.isArray(event)
      || event.protocol_version !== PROTOCOL_VERSION
      || !Number.isInteger(event.seq)
      || typeof event.event !== 'string'
      || typeof event.run_id !== 'string'
      || !event.data || typeof event.data !== 'object' || Array.isArray(event.data)) {
      this._failOperation(operation, this._failure(
        operation, 'CLI_PROTOCOL_INVALID_EVENT', 'SAMI sent a progress message this app cannot read.',
      ));
      return;
    }
    if (operation.lastSequence && event.seq <= operation.lastSequence) {
      this._failOperation(operation, this._failure(
        operation, 'CLI_PROTOCOL_SEQUENCE_INVALID', 'SAMI sent progress messages out of order.',
      ));
      return;
    }
    if (operation.runId && event.run_id !== operation.runId) {
      this._failOperation(operation, this._failure(
        operation, 'CLI_PROTOCOL_RUN_ID_MISMATCH', 'SAMI sent a message for a different conversion.',
      ));
      return;
    }

    operation.lastSequence = event.seq;
    operation.lastActivityAt = Date.now();
    if (!operation.started) {
      operation.started = true;
      operation.runId = event.run_id;
      if (operation.cancelRequested) this._sendCancel(operation);
    }
    if (event.event === 'run_started') {
      operation.runId = event.run_id;
      this._setPhase(operation, 'running', { runId: operation.runId });
    } else if (event.event === 'inputs_resolved') {
      operation.stage = 'Processing selected inputs';
      if (!operation.cancelRequested) this._setPhase(operation, 'resolving_inputs', { inputCount: event.data.count });
    } else if (event.event === 'job_progress') {
      operation.stage = event.data.stage || 'Converting document';
    } else if (event.event === 'job_retrying') {
      operation.stage = 'Retrying on CPU';
      if (!operation.cancelRequested) this._setPhase(operation, 'retrying', { jobId: event.job_id, attempt: event.attempt });
    } else if (event.event === 'run_finished') {
      operation.runFinished = event;
      this._setPhase(operation, 'finishing', { runId: operation.runId });
    }
    this.emit('event', event);
    if (event.event === 'warning') {
      this.emit('diagnostic', {
        message: event.data.message || event.data.reason || 'SAMI reported a warning.',
        stream: 'jsonl',
        level: 'warning',
        event,
      });
    }
  }

  _readStderr(operation, chunk) {
    if (this.active !== operation) return;
    this._appendStderr(operation, operation.stderrDecoder.write(chunk));
  }

  _appendStderr(operation, text) {
    if (!text) return;
    operation.lastActivityAt = Date.now();
    operation.stderrBuffer += text;
    const lines = operation.stderrBuffer.split(/[\r\n]+/);
    operation.stderrBuffer = lines.pop();
    for (const line of lines) this._emitDiagnostic(line.slice(0, MAX_STDERR_LINE_CHARS));
    if (operation.stderrBuffer.length > MAX_STDERR_LINE_CHARS) {
      this._emitDiagnostic(operation.stderrBuffer.slice(0, MAX_STDERR_LINE_CHARS) + ' [truncated]');
      operation.stderrBuffer = '';
    }
    operation.stderrTail = (operation.stderrTail + text).slice(-MAX_DIAGNOSTIC_BYTES);
    const latest = lines.at(-1)?.trim();
    if (operation.management && latest) {
      operation.stage = latest.slice(0, 300);
      if (/prepar|download|model|loading/i.test(latest)) this._setPhase(operation, 'preparing', { label: operation.stage });
    }
  }

  _emitDiagnostic(message) {
    const trimmed = message.trim();
    if (!trimmed) return;
    const level = /\b(error|failed|warning)\b/i.test(trimmed) ? 'warning' : 'info';
    this.emit('diagnostic', { message: trimmed, stream: 'stderr', level });
  }

  _emitActivity(operation) {
    if (this.active !== operation) return;
    const now = Date.now();
    const silenceMs = Math.max(0, now - operation.lastActivityAt);
    const waiting = silenceMs >= this.stallMs;
    this.emit('activity', {
      phase: operation.phase,
      stage: operation.stage,
      elapsedMs: Math.max(0, now - operation.startedAt),
      silenceMs,
      waiting,
      ...(waiting ? { lastUpdateAt: operation.lastActivityAt } : {}),
    });
  }

  _sendCancel(operation) {
    if (!operation.controlStdin || !operation.runId || operation.cancelSent) return;
    if (!operation.child.stdin || operation.child.stdin.destroyed) return;
    operation.cancelSent = true;
    try { operation.child.stdin.write(JSON.stringify({
      protocol_version: PROTOCOL_VERSION,
      command: 'cancel',
      run_id: operation.runId,
    }) + '\n'); } catch (error) {
      this._emitDiagnostic('Could not send the cancellation request: ' + error.message);
    }
  }

  async _forceClose(operation) {
    if (this.active !== operation || operation.forced) return;
    operation.forced = true;
    clearTimeout(operation.cancelTimer);
    this._setPhase(operation, 'stopping', { runId: operation.runId, reason: 'cancel-timeout' });
    await this._terminateOwnedTree(operation);
  }

  async _terminateOwnedTree(operation) {
    const pid = operation.child.pid;
    if (!pid) return;
    if (this.platform === 'win32') {
      await new Promise((resolve) => {
        let killer;
        try {
          killer = this.spawnProcess('taskkill.exe', ['/PID', String(pid), '/T', '/F'], {
            shell: false, windowsHide: true, stdio: 'ignore',
          });
        } catch {
          operation.child.kill();
          resolve();
          return;
        }
        let complete = false;
        let timer;
        const finish = () => {
          if (complete) return;
          complete = true;
          clearTimeout(timer);
          if (operation.child.exitCode === null) operation.child.kill();
          resolve();
        };
        timer = setTimeout(finish, this.killTimeoutMs);
        timer.unref?.();
        killer.once('error', finish);
        killer.once('close', finish);
      });
      return;
    }
    try {
      process.kill(-pid, 'SIGTERM');
    } catch {
      operation.child.kill('SIGTERM');
    }
    await new Promise((resolve) => {
      const timer = setTimeout(() => {
        try {
          // The group can outlive its direct child; always signal the owned group.
          process.kill(-pid, 'SIGKILL');
        } catch {
          if (operation.child.exitCode === null) operation.child.kill('SIGKILL');
        }
        resolve();
      }, this.killTimeoutMs);
      timer.unref?.();
    });
  }

  _finishOperation(operation, code, signal) {
    const stdoutRemainder = operation.stdoutDecoder.end();
    if (operation.management) operation.stdout += stdoutRemainder;
    operation.stdoutBuffer += stdoutRemainder;
    if (operation.stdoutBuffer.trim()) {
      this._consumeEventLine(operation, operation.stdoutBuffer.replace(/\r$/, ''));
      operation.stdoutBuffer = '';
    }
    const stderrRemainder = operation.stderrDecoder.end();
    operation.stderrBuffer += stderrRemainder;
    if (operation.stderrBuffer.trim()) this._emitDiagnostic(operation.stderrBuffer);
    operation.exitCode = code;
    if (operation.interval) clearInterval(operation.interval);
    if (operation.cancelTimer) clearTimeout(operation.cancelTimer);
    if (this.active !== operation) return;

    const result = {
      runId: operation.runId,
      exitCode: code,
      signal,
      event: operation.runFinished,
      stdout: operation.stdout,
      stderr: operation.stderrTail,
    };
    if (operation.management) {
      this._setPhase(operation, code === 0 ? 'succeeded' : 'failed', result);
      if (operation.failure) {
        operation.rejectCompletion(operation.failure);
      } else if (code === 0 || operation.stdout.trim()) {
        operation.resolveCompletion(result);
      } else {
        operation.rejectCompletion(this._failure(
          operation,
          'CLI_MANAGEMENT_FAILED',
          'SAMI could not complete ' + operation.label.toLowerCase() + '.',
          undefined,
          result,
        ));
      }
      this.active = null;
      return;
    }
    if (operation.failure) {
      this._setPhase(operation, 'failed', { error: operation.failure });
      operation.rejectCompletion(operation.failure);
    } else if (operation.runFinished) {
      const phase = code === 130 ? 'cancelled' : code === 0 ? 'succeeded' : 'failed';
      this._setPhase(operation, phase, result);
      operation.resolveCompletion(result);
    } else {
      const failure = this._failure(
        operation,
        code === 0 ? 'CLI_TERMINAL_EVENT_MISSING' : 'CLI_CRASHED',
        code === 0
          ? 'SAMI exited before reporting that the batch finished.'
          : 'SAMI stopped before reporting that the batch finished.',
        undefined,
        result,
      );
      this._setPhase(operation, operation.cancelRequested ? 'cancelled' : 'failed', { error: failure });
      operation.rejectCompletion(failure);
    }
    this.active = null;
  }

  _failOperation(operation, failure) {
    if (this.active !== operation || operation.failed) return;
    operation.failed = true;
    operation.failure = failure;
    this.emit('diagnostic', { message: failure.message, stream: 'runner', level: 'error', code: failure.code });
    void this._forceClose(operation);
  }

  _failure(operation, code, message, cause, details = {}) {
    return new CliRunnerError(message, {
      code,
      cause,
      runId: operation.runId,
      executable: operation.installation.executable,
      stderr: operation.stderrTail,
      ...details,
    });
  }

  _setPhase(operation, phase, details = {}) {
    if (operation.cancelRequested && !['cancelling', 'stopping', 'cancelled', 'failed'].includes(phase)) {
      phase = 'cancelling';
      details = { ...details, runId: operation.runId };
    }
    operation.phase = phase;
    operation.lastActivityAt = Date.now();
    this.emit('state', { phase, pid: operation.child.pid, ...details });
  }

  _parseManagementJson(stdout, command) {
    try {
      const value = JSON.parse(stdout.trim());
      if (!value || typeof value !== 'object' || Array.isArray(value)) throw new TypeError('expected a JSON object');
      return value;
    } catch (cause) {
      throw new CliRunnerError('The SAMI ' + command + ' command returned invalid JSON.', {
        code: 'CLI_' + command.toUpperCase() + '_INVALID_JSON',
        cause,
      });
    }
  }

  _runManagement(installation, args, label) {
    const operation = this._spawn(installation, args, {
      phase: args[0] === 'setup' ? 'preparing' : 'checking-health', label, controlStdin: false,
    });
    return operation.completion;
  }

  _reserveOperation() {
    if (this.closing) throw new CliRunnerError('The SAMI window is closing.', { code: 'RUNNER_CLOSING' });
    if (this.active || this.reserving) {
      throw new CliRunnerError('A SAMI operation is already running.', { code: 'OPERATION_IN_PROGRESS' });
    }
    this.reserving = true;
  }

  _isAbsolute(value) {
    if (typeof value !== 'string' || !value.trim()) return false;
    return this.platform === 'win32' ? path.win32.isAbsolute(value) : path.posix.isAbsolute(value);
  }
}
