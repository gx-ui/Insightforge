import {describe, expect, it} from 'vitest';
import {createEventJournal} from './server-events.mjs';

describe('event journal', () => {
  it('assigns monotonic ids and replays only newer events', () => {
    const journal = createEventJournal({limit: 3});
    const first = journal.publish({type: 'status'}, {runId: 'turn-1', sessionId: 'session-1'});
    const second = journal.publish({type: 'token', delta: 'A'}, {runId: 'turn-1', sessionId: 'session-1'});

    expect(first).toMatchObject({event_id: 'evt-1', run_id: 'turn-1', session_id: 'session-1'});
    expect(second.event_id).toBe('evt-2');
    expect(journal.replayAfter(first.event_id)).toEqual([second]);
  });

  it('reports unavailable replay when the requested id was evicted', () => {
    const journal = createEventJournal({limit: 1});
    const first = journal.publish({type: 'status'}, {runId: 'turn-1'});
    journal.publish({type: 'done'}, {runId: 'turn-1'});

    expect(journal.replayAfter(first.event_id)).toEqual(null);
  });

  it('keeps a minimal snapshot for an active run without replaying history', () => {
    const journal = createEventJournal();
    journal.publish({type: 'run_started', stage: 'narrative'}, {runId: 'turn-1', sessionId: 'session-1'});
    journal.publish({type: 'tool_progress', stage: 'portraits', label: '正在生成角色图'}, {runId: 'turn-1', sessionId: 'session-1'});

    expect(journal.activeSnapshots()).toEqual([
      expect.objectContaining({
        type: 'run_started',
        run_id: 'turn-1',
        session_id: 'session-1',
        stage: 'portraits',
        label: '正在生成角色图',
      }),
    ]);
  });
});
