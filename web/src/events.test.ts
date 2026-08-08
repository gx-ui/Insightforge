import {describe, expect, it} from 'vitest';
import {applyAgentEvent, appendLocalUser, composeAgentPrompt, createChatState, humanize} from './events';

describe('agent event mapping', () => {
  it('streams assistant text into one message', () => {
    let state = appendLocalUser(createChatState(), 'Make a short film');
    state = applyAgentEvent(state, {type: 'turn', turn_id: 'turn-1'});
    state = applyAgentEvent(state, {type: 'token', turn_id: 'turn-1', delta: 'Planning'});
    state = applyAgentEvent(state, {type: 'token', turn_id: 'turn-1', delta: ' ready'});
    state = applyAgentEvent(state, {type: 'done', turn_id: 'turn-1'});
    expect(state.messages.at(-1)).toMatchObject({role: 'assistant', text: 'Planning ready'});
    expect(state.busy).toBe(false);
  });

  it('updates a running tool instead of appending every progress event', () => {
    let state = createChatState();
    state = applyAgentEvent(state, {type: 'tool_start', turn_id: 'turn-1', tool: {id: 'tool-1', name: 'insightforge_render_video'}});
    state = applyAgentEvent(state, {type: 'tool_progress', turn_id: 'turn-1', tool: {name: 'insightforge_render_video'}, progress: {stage: 'generate_frames', message: 'Generating frames'}});
    state = applyAgentEvent(state, {type: 'tool_result', turn_id: 'turn-1', tool_result: {name: 'insightforge_render_video', ok: true}});
    expect(state.messages).toHaveLength(1);
    expect(state.messages[0]).toMatchObject({tool: 'insightforge_render_video', status: 'done', text: '已完成'});
  });

  it('keeps each composer submission on one stdin line', () => {
    expect(composeAgentPrompt('first line\nsecond line')).toBe('first line second line');
    expect(composeAgentPrompt('Use these references', ['uploads/script.txt', 'uploads/look.png']))
      .toBe('Use these references <workspace_uploads>["uploads/script.txt","uploads/look.png"]</workspace_uploads>');
    expect(humanize('insightforge_narrative_planning')).toBe('InsightForge Narrative Planning');
  });

  it('ends running tools when the agent process stops', () => {
    let state = applyAgentEvent(createChatState(), {
      type: 'tool_start',
      turn_id: 'turn-1',
      tool: {id: 'tool-1', name: 'insightforge_render_video'},
    });
    state = applyAgentEvent(state, {
      type: 'bridge_status',
      status: 'stopped',
      message: 'Configuration updated',
    });
    expect(state.busy).toBe(false);
    expect(state.messages[0]).toMatchObject({
      tool: 'insightforge_render_video',
      status: 'error',
      stage: 'interrupted',
      text: 'Configuration updated',
    });
  });

  it('drops duplicate ids and restores text ordering', () => {
    let state = createChatState();
    state = applyAgentEvent(state, {type: 'run_started', event_id: 'evt-0', run_id: 'turn-1'});
    state = applyAgentEvent(state, {type: 'token', event_id: 'evt-2', turn_id: 'turn-1', sequence: 2, delta: '好'});
    state = applyAgentEvent(state, {type: 'token', event_id: 'evt-1', turn_id: 'turn-1', sequence: 1, delta: '你'});
    state = applyAgentEvent(state, {type: 'token', event_id: 'evt-2', turn_id: 'turn-1', sequence: 2, delta: '好'});
    expect(state.messages.at(-1)).toMatchObject({text: '你好'});
  });

  it('marks all running activities interrupted when a run stops', () => {
    let state = applyAgentEvent(createChatState(), {
      type: 'tool_start',
      turn_id: 'turn-1',
      tool: {id: 'tool-1', name: 'insightforge_render_video'},
    });
    state = applyAgentEvent(state, {
      type: 'tool_start',
      turn_id: 'turn-1',
      tool: {id: 'tool-2', name: 'image_generator'},
    });
    state = applyAgentEvent(state, {type: 'run_stopped', run_id: 'turn-1', message: '生成已停止'});
    expect(state.messages.filter((message) => message.role === 'activity')).toEqual([
      expect.objectContaining({status: 'error', stage: 'interrupted'}),
      expect.objectContaining({status: 'error', stage: 'interrupted'}),
    ]);
  });

  it('waits for every character approval after the first render turn finishes', () => {
    let state = applyAgentEvent(createChatState([], 's1'), {
      type: 'approval_required',
      run_id: 'turn-1',
      approval: {
        run_id: 'turn-1',
        session_id: 's1',
        roles: [{
          role_id: 'alice',
          role_version: 1,
          display_name: 'Alice',
          approved: false,
          products: [{artifact_id: 'character:alice:v1:front', role_id: 'alice', role_version: 1, view: 'front', url: '/portrait.png', caption: 'Alice · 正面'}],
        }],
      },
    });
    state = applyAgentEvent(state, {type: 'done', run_id: 'turn-1'});

    expect(state.run).toMatchObject({status: 'waiting_user', stage: {label: '等待确认 1 个角色'}});
    expect(state.busy).toBe(true);
    expect(state.messages.at(-1)?.product).toMatchObject({artifactId: 'character:alice:v1:front'});
  });

  it('replaces an initial portrait URL with its immutable version URL', () => {
    let state = applyAgentEvent(createChatState(), {type: 'product', run_id: 'turn-1', product: {kind: 'character_image', artifact_id: 'character:alice:v1:front', role_id: 'alice', role_version: 1, view: 'front', url: '/raw.png'}});
    state = applyAgentEvent(state, {type: 'product', run_id: 'turn-1', product: {kind: 'character_image', artifact_id: 'character:alice:v1:front', role_id: 'alice', role_version: 1, view: 'front', url: '/versioned.png'}});
    expect(state.messages).toHaveLength(1);
    expect(state.messages[0].product?.url).toBe('/versioned.png');
  });
});
