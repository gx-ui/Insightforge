import type {AgentEvent, CharacterApproval, CharacterApprovalRole, CharacterProduct, ChatState, Message, RunState, StageInfo} from './types';

export function createChatState(messages: Message[] = [], sessionId = ''): ChatState {
  return {
    messages,
    busy: false,
    turnId: '',
    promptTokens: 0,
    run: {runId: '', status: 'idle'},
    seenEventIds: [],
    tokenBuffers: {},
    sessionId,
  };
}

export function appendLocalUser(state: ChatState, text: string): ChatState {
  return {
    ...state,
    busy: true,
    messages: [...state.messages, {id: `local-user-${Date.now()}`, role: 'user', text}],
  };
}

export function composeAgentPrompt(text: string, workspaceUploads: string[] = []) {
  const message = text.replace(/\s+/g, ' ').trim();
  const paths = workspaceUploads.map((path) => path.trim()).filter(Boolean);
  if (paths.length === 0) return message;
  return `${message} <workspace_uploads>${JSON.stringify(paths)}</workspace_uploads>`;
}

export function applyAgentEvent(state: ChatState, event: AgentEvent): ChatState {
  if (event.session_id && state.sessionId && event.session_id !== state.sessionId) return state;
  if (event.event_id && state.seenEventIds.includes(event.event_id)) return state;
  const next = event.event_id
    ? {...state, seenEventIds: [...state.seenEventIds, event.event_id].slice(-10_000), run: {...state.run, lastEventId: event.event_id}}
    : state;
  const turnId = event.run_id || event.turn_id || next.run.runId || next.turnId || `turn-${Date.now()}`;
  const stage = stageFromEvent(event);
  switch (event.type) {
    case 'run_started':
      return {
        ...next,
        busy: true,
        turnId,
        run: {runId: turnId, status: 'running', stage, startedAt: event.timestamp || Date.now(), lastEventId: event.event_id},
      };
    case 'turn':
      return {...next, busy: true, turnId, run: next.run.runId ? next.run : {runId: turnId, status: 'running', startedAt: event.timestamp || Date.now()}};
    case 'prompt_trace': {
      const tokens = event.prompt_trace?.totals?.total_tokens
        ?? event.prompt_trace?.totals?.total_estimated_tokens
        ?? event.prompt_trace?.total_estimated_tokens
        ?? next.promptTokens;
      return {...next, promptTokens: Math.max(0, Math.round(tokens))};
    }
    case 'token':
      return appendAssistantDelta(next, turnId, event.delta || '', event.sequence);
    case 'stream_start':
    case 'stream_end':
      return {...next, run: {...next.run, runId: turnId, status: 'running', stage: stage || next.run.stage}};
    case 'status':
      return {...next, busy: true, run: {...next.run, runId: turnId, status: 'running', stage: stage || next.run.stage}};
    case 'tool_start': {
      const name = event.tool?.name || event.tool?.requested_name || 'tool';
      return upsertActivity(next, {
        id: activityId(turnId, event.tool?.id, name),
        role: 'activity',
        runId: turnId,
        tool: name,
        status: 'running',
        stage: 'starting',
        text: '启动中',
      });
    }
    case 'tool_progress': {
      const name = event.tool?.name || event.tool?.requested_name || 'tool';
      const updated = upsertLatestToolActivity(next, turnId, name, {
        role: 'activity',
        runId: turnId,
        tool: name,
        status: 'running',
        stage: event.stage || event.progress?.stage || 'running',
        rawStage: event.raw_stage || event.progress?.stage,
        text: event.label || event.progress?.message || '正在处理你的创作任务',
      });
      return {...updated, busy: true, run: {...updated.run, runId: turnId, status: 'running', stage: stage || updated.run.stage}};
    }
    case 'tool_result': {
      const name = event.tool_result?.name || 'tool';
      const ok = event.tool_result?.ok !== false;
      return upsertLatestToolActivity(next, turnId, name, {
        role: 'activity',
        runId: turnId,
        tool: name,
        status: ok ? 'done' : 'error',
        stage: ok ? 'completed' : 'failed',
        text: ok ? '已完成' : cleanError(event.tool_result?.content || '工具失败'),
      });
    }
    case 'terminal':
      if (event.stream !== 'stderr') return next;
      return {
        ...next,
        messages: [...next.messages, {
          id: `terminal-${Date.now()}`,
          role: 'activity',
          runId: turnId,
          status: 'error',
          tool: 'runtime',
          text: cleanError(event.line || '运行时错误'),
        }],
      };
    case 'error':
      return {
        ...next,
        busy: false,
        run: finishRun(next.run, turnId, 'failed', stage),
        messages: [...interruptActivities(next.messages, turnId, event.message || '运行失败'), {id: `error-${turnId}-${Date.now()}`, role: 'error', runId: turnId, text: event.message || '未知的 agent 错误'}],
      };
    case 'done': {
      const messages = reconcileAssistant(next.messages, turnId, event.assistant || '');
      if (next.approval?.runId === turnId && next.approval.roles.some((role) => !role.approved)) {
        return {...next, messages, busy: true, run: finishRun(next.run, turnId, 'waiting_user', approvalStage(next.approval))};
      }
      return {...next, messages, busy: false, run: finishRun(next.run, turnId, 'completed', stage)};
    }
    case 'product': {
      const product = characterProductFromEvent(event);
      if (!product || next.messages.some((message) => message.product?.artifactId === product.artifactId)) return next;
      return {...next, messages: [...next.messages, {id: `product-${product.artifactId}`, role: 'product', runId: turnId, text: product.caption, product}]};
    }
    case 'approval_required': {
      const approval = approvalFromEvent(event, turnId);
      if (!approval) return next;
      return {
        ...next,
        busy: true,
        approval,
        messages: addApprovalProducts(next.messages, turnId, approval),
        run: {...next.run, runId: turnId, status: 'waiting_user', stage: approvalStage(approval)},
      };
    }
    case 'approval_resolved': {
      if (!next.approval || next.approval.runId !== turnId) return next;
      const roleId = event.approval?.role_id;
      const roleVersion = Number(event.approval?.role_version);
      if (!roleId || !Number.isInteger(roleVersion) || event.approval?.action !== 'confirm') return next;
      const approval = {
        ...next.approval,
        roles: next.approval.roles.map((role) => role.roleId === roleId && role.roleVersion === roleVersion ? {...role, approved: true} : role),
      };
      const resuming = event.approval?.ready_to_resume === true;
      return {
        ...next,
        busy: true,
        approval,
        run: {...next.run, runId: turnId, status: resuming ? 'running' : 'waiting_user', stage: resuming ? {group: 'render', stage: 'rendering', label: '角色已确认，继续渲染'} : approvalStage(approval)},
      };
    }
    case 'run_stopped':
      return {...next, busy: false, run: finishRun(next.run, turnId, 'stopped', stage), messages: interruptActivities(next.messages, turnId, event.message || '生成已停止')};
    case 'sse_replay_unavailable':
      return {...next, run: {...next.run, status: 'reconnecting'}};
    case 'bridge_status':
      if (event.status !== 'error' && event.status !== 'stopped') return next;
      return {
        ...next,
        busy: false,
        run: {...next.run, status: event.status === 'error' ? 'failed' : 'stopped'},
        messages: next.messages.map((message) => message.role === 'activity' && message.status === 'running'
          ? {...message, status: 'error', stage: 'interrupted', text: event.message || '生成已停止'}
          : message),
      };
    default:
      return next;
  }
}

function appendAssistantDelta(state: ChatState, turnId: string, delta: string, sequence?: number): ChatState {
  if (!delta) return state;
  const id = `assistant-${turnId}`;
  const tokenBuffers = Number.isFinite(sequence)
    ? {...state.tokenBuffers, [turnId]: {...state.tokenBuffers[turnId], [Number(sequence)]: delta}}
    : state.tokenBuffers;
  const text = Number.isFinite(sequence)
    ? Object.entries(tokenBuffers[turnId]).sort(([left], [right]) => Number(left) - Number(right)).map(([, value]) => value).join('')
    : undefined;
  const index = state.messages.findIndex((message) => message.id === id);
  if (index < 0) {
    return {...state, tokenBuffers, messages: [...state.messages, {id, role: 'assistant', runId: turnId, text: text ?? delta}]};
  }
  const messages = [...state.messages];
  messages[index] = {...messages[index], text: text ?? `${messages[index].text}${delta}`};
  return {...state, tokenBuffers, messages};
}

function upsertActivity(state: ChatState, message: Message): ChatState {
  const index = state.messages.findIndex((item) => item.id === message.id);
  if (index < 0) return {...state, messages: [...state.messages, message]};
  const messages = [...state.messages];
  messages[index] = {...messages[index], ...message};
  return {...state, messages};
}

function upsertLatestToolActivity(state: ChatState, turnId: string, tool: string, update: Omit<Message, 'id'>): ChatState {
  const messages = [...state.messages];
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].role === 'activity' && messages[index].runId === turnId && messages[index].tool === tool && messages[index].status === 'running') {
      messages[index] = {...messages[index], ...update};
      return {...state, messages};
    }
  }
  return {...state, messages: [...messages, {id: `activity-${turnId}-${tool}-${Date.now()}`, ...update}]};
}

function activityId(turnId: string, toolId: string | undefined, name: string) {
  return `activity-${turnId}-${toolId || name}-${Date.now()}`;
}

function stageFromEvent(event: AgentEvent): StageInfo | undefined {
  if (!event.stage && !event.label) return undefined;
  return {group: event.stage_group || 'generic', stage: event.stage || event.raw_stage || 'running', label: event.label || '正在处理你的创作任务'};
}

function finishRun(run: RunState, turnId: string, status: RunState['status'], stage?: StageInfo): RunState {
  return {...run, runId: turnId, status, stage: stage || run.stage};
}

function interruptActivities(messages: Message[], turnId: string, text: string): Message[] {
  return messages.map((message) => message.role === 'activity' && message.runId === turnId && message.status === 'running'
    ? {...message, status: 'error', stage: 'interrupted', text}
    : message);
}

function reconcileAssistant(messages: Message[], turnId: string, text: string): Message[] {
  if (!text) return messages;
  const id = `assistant-${turnId}`;
  const index = messages.findIndex((message) => message.id === id);
  if (index < 0) return [...messages, {id, role: 'assistant', runId: turnId, text}];
  const next = [...messages];
  next[index] = {...next[index], text};
  return next;
}

function characterProductFromEvent(event: AgentEvent): CharacterProduct | null {
  const product = event.product;
  if (product?.kind !== 'character_image' || !product.artifact_id || !product.role_id || !product.url) return null;
  return {
    artifactId: product.artifact_id,
    roleId: product.role_id,
    roleVersion: Number(product.role_version) || 1,
    view: product.view || 'default',
    url: product.url,
    caption: product.caption || product.role_id,
  };
}

function approvalFromEvent(event: AgentEvent, fallbackRunId: string): CharacterApproval | null {
  const approval = event.approval;
  const roles = approval?.roles;
  if (!approval || !Array.isArray(roles)) return null;
  const normalizedRoles: CharacterApprovalRole[] = roles.map((role) => ({
    roleId: role.role_id || '',
    roleVersion: Number(role.role_version) || 1,
    displayName: role.display_name || role.role_id || '未命名角色',
    description: role.description || '',
    approved: role.approved === true,
    products: (role.products || []).flatMap((product) => product.artifact_id && product.role_id && product.url ? [{
      artifactId: product.artifact_id,
      roleId: product.role_id,
      roleVersion: Number(product.role_version) || 1,
      view: product.view || 'default',
      url: product.url,
      caption: product.caption || product.role_id,
    }] : []),
  })).filter((role) => role.roleId);
  return {runId: approval.run_id || fallbackRunId, sessionId: approval.session_id || event.session_id || '', roles: normalizedRoles};
}

function addApprovalProducts(messages: Message[], runId: string, approval: CharacterApproval): Message[] {
  const known = new Set(messages.map((message) => message.product?.artifactId).filter(Boolean));
  return [
    ...messages,
    ...approval.roles.flatMap((role) => role.products.filter((product) => !known.has(product.artifactId)).map((product) => ({
      id: `product-${product.artifactId}`,
      role: 'product' as const,
      runId,
      text: product.caption,
      product,
    }))),
  ];
}

function approvalStage(approval: CharacterApproval): StageInfo {
  const pending = approval.roles.filter((role) => !role.approved).length;
  return {group: 'portraits', stage: 'approval', label: pending ? `等待确认 ${pending} 个角色` : '角色已确认，准备继续渲染'};
}

export function humanize(value: string) {
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
    .replace(/\bInsightforge\b/g, 'InsightForge')
    .replace(/\bWorkflow\b/g, '工作流');
}

function cleanError(value: string) {
  return value.replace(/\s+/g, ' ').trim();
}
