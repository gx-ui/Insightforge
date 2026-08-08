import {createReadStream, existsSync} from 'node:fs';
import {readFile} from 'node:fs/promises';
import {createServer} from 'node:http';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {randomUUID} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {readAgentConfig, saveAgentConfig} from './config-store.mjs';
import {createEventJournal} from './server-events.mjs';
import {
  artifactContentType,
  createTraceWriter,
  deleteSession,
  listSessionArtifacts,
  readSessionHistory,
  readSessionState,
  resolveArtifactPath,
  saveSessionPreferences,
  storeWorkspaceUpload,
} from './server-lib.mjs';

const webRoot = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(webRoot, '..');
const isDev = process.argv.includes('--dev');
const host = process.env.INSIGHTFORGE_WEB_HOST || '127.0.0.1';
const port = Number(process.env.INSIGHTFORGE_WEB_PORT || 4173);
const configuredUploadLimit = Number(process.env.INSIGHTFORGE_WEB_UPLOAD_MAX_BYTES || 100 * 1024 * 1024);
const uploadMaxBytes = Number.isFinite(configuredUploadLimit) && configuredUploadLimit > 0
  ? configuredUploadLimit
  : 100 * 1024 * 1024;
const subscribers = new Set();
const eventJournal = createEventJournal();
const traceWriter = createTraceWriter(repoRoot);
let agentProcess = null;
let activeSessionId = '';
let activeRunId = '';

let vite = null;

const server = createServer(async (request, response) => {
  const url = new URL(request.url || '/', `http://${request.headers.host || `${host}:${port}`}`);
  try {
    if (url.pathname === '/api/events' && request.method === 'GET') {
      return openEventStream(request, response);
    }
    if (url.pathname === '/api/sessions' && request.method === 'GET') {
      return sendJson(response, 200, await readSessionState(repoRoot));
    }
    if (url.pathname === '/api/config' && request.method === 'GET') {
      return sendJson(response, 200, await readAgentConfig(repoRoot));
    }
    if (url.pathname === '/api/config' && request.method === 'PUT') {
      const config = await saveAgentConfig(repoRoot, await readJsonBody(request));
      stopAgent('config');
      return sendJson(response, 200, config);
    }
    if (url.pathname === '/api/sessions' && request.method === 'DELETE') {
      const sessionId = url.searchParams.get('session') || '';
      const current = await readSessionState(repoRoot);
      if (!current.sessions.some((session) => session.sessionId === sessionId)) {
        return sendJson(response, 404, {error: 'Project not found'});
      }
      if (sessionId === activeSessionId) stopAgent('delete');
      const state = await deleteSession(repoRoot, sessionId);
      activeSessionId = state.activeSessionId;
      broadcast({type: 'sessions_changed', ...state});
      return sendJson(response, 200, state);
    }
    if (url.pathname === '/api/history' && request.method === 'GET') {
      return sendJson(response, 200, {messages: await readSessionHistory(repoRoot, url.searchParams.get('session') || '')});
    }
    if (url.pathname === '/api/artifacts' && request.method === 'GET') {
      return sendJson(response, 200, {artifacts: await listSessionArtifacts(repoRoot, url.searchParams.get('session') || '')});
    }
    if (url.pathname === '/api/artifact' && request.method === 'GET') {
      return streamArtifact(response, url.searchParams.get('session') || '', url.searchParams.get('path') || '');
    }
    if (url.pathname === '/api/uploads' && request.method === 'POST') {
      const sessionId = url.searchParams.get('session') || '';
      const fileName = url.searchParams.get('name') || '';
      const current = await readSessionState(repoRoot);
      if (!current.sessions.some((session) => session.sessionId === sessionId)) {
        return sendJson(response, 404, {error: 'Project not found'});
      }
      const declaredSize = Number(request.headers['content-length'] || 0);
      if (declaredSize > uploadMaxBytes) {
        return sendJson(response, 413, {error: `File exceeds the ${formatByteLimit(uploadMaxBytes)} upload limit`});
      }
      const data = await readBinaryBody(request, uploadMaxBytes);
      const file = await storeWorkspaceUpload(repoRoot, sessionId, fileName, data);
      return sendJson(response, 201, {file});
    }
    if (url.pathname === '/api/agent/start' && request.method === 'POST') {
      const body = await readJsonBody(request);
      const sessionId = typeof body.sessionId === 'string' ? body.sessionId : '';
      const projectName = typeof body.projectName === 'string' ? body.projectName.trim() : '';
      if (projectName.length > 64) {
        return sendJson(response, 400, {error: 'Project name must be 64 characters or fewer'});
      }
      await startAgent({newSession: body.newSession === true, sessionId, projectName});
      return sendJson(response, 200, {ok: true});
    }
    if (url.pathname === '/api/messages' && request.method === 'POST') {
      const body = await readJsonBody(request);
      const text = String(body.text || '').trim();
      if (!text) return sendJson(response, 400, {error: 'Message text is required'});
      if (!agentProcess?.stdin.writable) return sendJson(response, 409, {error: 'Agent is not running'});
      const runId = randomUUID();
      activeRunId = runId;
      broadcast({type: 'run_started', run_id: runId, stage_group: 'narrative', stage: 'narrative', label: '正在理解你的创作需求'});
      broadcast({type: 'status', run_id: runId, stage_group: 'narrative', stage: 'narrative', label: '正在理解你的创作需求', message: '正在理解你的创作需求'});
      agentProcess.stdin.write(`${JSON.stringify({type: 'user_message', run_id: runId, text})}\n`);
      return sendJson(response, 202, {ok: true, runId});
    }
    if (url.pathname === '/api/agent/stop' && request.method === 'POST') {
      stopAgent('user');
      return sendJson(response, 200, {ok: true});
    }
    if (url.pathname === '/api/preferences' && request.method === 'POST') {
      const body = await readJsonBody(request);
      if (!body.preferences || typeof body.preferences !== 'object') {
        return sendJson(response, 400, {error: 'preferences object is required'});
      }
      if (!agentProcess?.stdin.writable) {
        return sendJson(response, 409, {error: 'Agent is not running'});
      }
      const version = (Number(body.version) || 0) + 1;   // 只有 server 递增；客户端发递增前的版本
      const event = JSON.stringify({
        type: 'preference_updated',
        scope: 'session',
        version,
        preferences: body.preferences,
      });
      try {
        await saveSessionPreferences(repoRoot, version, body.preferences);
      } catch (error) {
        console.warn('preferences not persisted:', error?.message);
      }
      agentProcess.stdin.write(`${event}\n`);
      return sendJson(response, 202, {ok: true, version});
    }
    if (url.pathname === '/api/health' && request.method === 'GET') {
      return sendJson(response, 200, {ok: true, agentRunning: Boolean(agentProcess), activeSessionId, activeRunId});
    }
    if (url.pathname === '/assets/insightforge.png' && request.method === 'GET') {
      response.writeHead(200, {'Content-Type': 'image/png', 'Cache-Control': 'public, max-age=3600'});
      createReadStream(path.join(repoRoot, 'assets', 'insightforge.png')).pipe(response);
      return;
    }
    if (vite) {
      vite.middlewares(request, response, () => sendJson(response, 404, {error: 'Not found'}));
      return;
    }
    return serveProductionApp(response, url.pathname);
  } catch (error) {
    const status = Number(error?.statusCode) || 500;
    sendJson(response, status, {error: error instanceof Error ? error.message : String(error)});
  }
});

if (isDev) {
  vite = await (await import('vite')).createServer({
    root: webRoot,
    server: {middlewareMode: true, hmr: {server}},
    appType: 'spa',
  });
}

server.listen(port, host, () => {
  console.log(`InsightForge Web 服务: http://${host}:${port}`);
});

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

async function startAgent({newSession, sessionId, projectName = ''}) {
  if (newSession && sessionId) throw new Error('请选择新建或已有会话');
  stopAgent('switch');
  const {command, args} = agentCommand();
  const sessionArgs = newSession
    ? ['--new-session', ...(projectName ? ['--new-session-name', projectName] : [])]
    : sessionId
      ? ['--session', sessionId]
      : [];
  activeSessionId = sessionId;
  const child = spawn(command, [...args, 'main_agent.py', '--jsonl', '--stdin-repl', ...sessionArgs], {
    cwd: repoRoot,
    env: {...process.env, PYTHONIOENCODING: 'utf-8'},
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  agentProcess = child;
  let childStdoutBuffer = '';
  broadcast({type: 'bridge_status', status: 'starting', message: newSession ? 'Creating workspace' : 'Opening workspace'});
  child.stdout.setEncoding('utf8');
  child.stdout.on('data', (chunk) => {
    if (agentProcess !== child) return;
    childStdoutBuffer += String(chunk);
    const lines = childStdoutBuffer.split(/\r?\n/);
    childStdoutBuffer = lines.pop() || '';
    for (const line of lines) consumeAgentLine(line);
  });
  child.stderr.setEncoding('utf8');
  child.stderr.on('data', (chunk) => {
    if (agentProcess !== child) return;
    for (const line of String(chunk).split(/\r?\n/)) {
      if (line.trim()) broadcast({type: 'terminal', stream: 'stderr', line});
    }
  });
  child.on('error', (error) => {
    if (agentProcess !== child) return;
    broadcast({type: 'error', message: `Agent process error: ${error.message}`});
  });
  child.on('exit', (code, signal) => {
    if (agentProcess !== child) return;
    agentProcess = null;
    broadcast({
      type: 'bridge_status',
      status: code === 0 || signal === 'SIGTERM' ? 'stopped' : 'error',
      message: signal ? `Agent stopped by ${signal}` : `Agent exited with code ${code ?? 0}`,
    });
  });
  setTimeout(async () => {
    if (agentProcess !== child) return;
    const state = await readSessionState(repoRoot);
    activeSessionId = state.activeSessionId || sessionId || activeSessionId;
    broadcast({type: 'sessions_changed', ...state, activeSessionId});
    broadcast({type: 'bridge_status', status: 'ready', message: 'Agent ready'});
  }, 350);
}

function consumeAgentLine(line) {
  if (!line.trim()) return;
  try {
    const event = JSON.parse(line);
    if (event.type === 'session') activeSessionId = event.session?.active_session_id || activeSessionId;
    broadcast(event);
    if (event.type === 'session') {
      readSessionState(repoRoot).then((state) => broadcast({type: 'sessions_changed', ...state}));
    }
  } catch {
    broadcast({type: 'terminal', stream: 'stdout', line});
  }
}

function openEventStream(request, response) {
  response.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache, no-transform',
    Connection: 'keep-alive',
    'X-Accel-Buffering': 'no',
  });
  const lastEventId = request.headers['last-event-id'];
  const replay = typeof lastEventId === 'string' && lastEventId ? eventJournal.replayAfter(lastEventId) : undefined;
  if (replay === null) {
    const unavailable = eventJournal.publish({type: 'sse_replay_unavailable'}, {sessionId: activeSessionId});
    writeSse(response, unavailable);
    void traceWriter.record(unavailable).catch((error) => console.warn('trace write failed:', error?.message));
  } else if (replay) {
    for (const event of replay) writeSse(response, event);
  } else {
    for (const snapshot of eventJournal.activeSnapshots()) writeSse(response, snapshot);
  }
  writeSse(response, {type: 'bridge_status', status: agentProcess ? 'ready' : 'idle', message: agentProcess ? 'Agent connected' : 'Agent idle'});
  subscribers.add(response);
  const heartbeat = setInterval(() => response.write(': keepalive\n\n'), 15_000);
  request.on('close', () => {
    clearInterval(heartbeat);
    subscribers.delete(response);
  });
}

function broadcast(event) {
  const published = eventJournal.publish(event, {
    sessionId: activeSessionId || undefined,
    runId: event.run_id ?? event.turn_id ?? undefined,
  });
  void traceWriter.record(published).catch((error) => console.warn('trace write failed:', error?.message));
  for (const subscriber of subscribers) writeSse(subscriber, published);
  if (published.run_id && ['done', 'error', 'run_stopped'].includes(published.type)) {
    eventJournal.clearRun(published.run_id);
    if (activeRunId === published.run_id) activeRunId = '';
  }
  return published;
}

function writeSse(response, event) {
  const id = event.event_id ? `id: ${event.event_id}\n` : '';
  response.write(`${id}data: ${JSON.stringify(event)}\n\n`);
}

function stopAgent(reason) {
  if (!agentProcess) return;
  const child = agentProcess;
  agentProcess = null;
  child.kill('SIGTERM');
  const message = reason === 'switch'
    ? 'Switching workspace'
    : reason === 'config'
      ? 'Configuration updated'
      : 'Generation stopped';
  if (activeRunId) broadcast({type: 'run_stopped', run_id: activeRunId, message});
  broadcast({type: 'bridge_status', status: 'stopped', message});
}

function agentCommand() {
  if (process.env.INSIGHTFORGE_AGENT_COMMAND) {
    return {command: process.env.INSIGHTFORGE_AGENT_COMMAND, args: splitArgs(process.env.INSIGHTFORGE_AGENT_ARGS || '')};
  }
  const configuredPython = process.env.INSIGHTFORGE_PYTHON_CMD;
  if (configuredPython) return {command: configuredPython, args: []};
  const bundledUv = process.env.INSIGHTFORGE_UV_CMD || path.join(process.env.HOME || '', '.local', 'bin', 'uv');
  if (bundledUv && existsSync(bundledUv)) return {command: bundledUv, args: ['run', 'python']};
  const venvPython = path.join(repoRoot, '.venv', 'bin', 'python3');
  if (existsSync(venvPython)) return {command: venvPython, args: []};
  return {command: 'uv', args: ['run', 'python']};
}

function splitArgs(value) {
  return value.split(/\s+/).map((part) => part.trim()).filter(Boolean);
}

async function readJsonBody(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  if (!chunks.length) return {};
  const text = Buffer.concat(chunks).toString('utf8');
  if (text.length > 1_000_000) throw new Error('请求体过大');
  return JSON.parse(text);
}

async function readBinaryBody(request, maxBytes) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > maxBytes) {
      const error = new Error(`File exceeds the ${formatByteLimit(maxBytes)} upload limit`);
      error.statusCode = 413;
      throw error;
    }
    chunks.push(chunk);
  }
  return Buffer.concat(chunks, size);
}

function formatByteLimit(bytes) {
  return `${Math.max(1, Math.round(bytes / (1024 * 1024)))} MB`;
}

function sendJson(response, status, payload) {
  if (response.writableEnded) return;
  response.writeHead(status, {'Content-Type': 'application/json; charset=utf-8'});
  response.end(JSON.stringify(payload));
}

async function streamArtifact(response, sessionId, relativePath) {
  const filePath = resolveArtifactPath(repoRoot, sessionId, relativePath);
  if (!existsSync(filePath)) return sendJson(response, 404, {error: 'Artifact not found'});
  response.writeHead(200, {
    'Content-Type': artifactContentType(filePath),
    'Cache-Control': 'private, max-age=60',
  });
  createReadStream(filePath).pipe(response);
}

async function serveProductionApp(response, pathname) {
  const requested = pathname === '/' ? 'index.html' : pathname.replace(/^\/+/, '');
  const candidate = path.resolve(webRoot, 'dist', requested);
  const distRoot = path.resolve(webRoot, 'dist');
  const safeCandidate = candidate.startsWith(`${distRoot}${path.sep}`) ? candidate : path.join(distRoot, 'index.html');
  const filePath = existsSync(safeCandidate) ? safeCandidate : path.join(distRoot, 'index.html');
  const body = await readFile(filePath);
  response.writeHead(200, {'Content-Type': artifactContentType(filePath)});
  response.end(body);
}

function shutdown() {
  stopAgent('shutdown');
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(0), 1_000).unref();
}
