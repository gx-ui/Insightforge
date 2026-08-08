import {describe, expect, it} from 'vitest';
import {groupChatBlocks, hasRunningActivity} from './chatBlocks';
import type {Message} from '../types';

function msg(overrides: Partial<Message> = {}): Message {
  return {
    id: 'm-1',
    role: 'assistant',
    text: 'hi',
    ...overrides,
  };
}

describe('chat block grouping', () => {
  it('groups consecutive non-activity messages into dialogue blocks', () => {
    const blocks = groupChatBlocks([
      msg({id: 'u1', role: 'user', text: 'hi'}),
      msg({id: 'a1', role: 'assistant', text: 'hello'}),
    ]);
    expect(blocks).toHaveLength(1);
    expect(blocks[0].type).toBe('dialogue');
    expect((blocks[0] as any).messages).toHaveLength(2);
  });

  it('folds consecutive activities into forge blocks', () => {
    const blocks = groupChatBlocks([
      msg({id: 't1', role: 'activity', tool: 'plan', status: 'running', text: '启动'}),
      msg({id: 't2', role: 'activity', tool: 'plan', status: 'done', text: '完成'}),
      msg({id: 't3', role: 'activity', tool: 'render', status: 'running', text: '渲染'}),
    ]);
    expect(blocks).toHaveLength(1);
    expect(blocks[0].type).toBe('forge');
    expect((blocks[0] as any).activities).toHaveLength(3);
  });

  it('alternates between dialogue and forge blocks', () => {
    const blocks = groupChatBlocks([
      msg({id: 'u', role: 'user', text: 'go'}),
      msg({id: 'a1', role: 'activity', tool: 'x', status: 'running', text: ''}),
      msg({id: 'a2', role: 'assistant', text: 'done'}),
    ]);
    expect(blocks.map((b) => b.type)).toEqual(['dialogue', 'forge', 'dialogue']);
  });

  it('returns empty array for no messages', () => {
    expect(groupChatBlocks([])).toEqual([]);
  });

  it('detects running activity in a forge block', () => {
    const blocks = groupChatBlocks([
      msg({id: 't1', role: 'activity', tool: 'x', status: 'done'}),
      msg({id: 't2', role: 'activity', tool: 'y', status: 'running'}),
    ]);
    expect(hasRunningActivity(blocks[0])).toBe(true);
  });

  it('returns false when no running activity', () => {
    const blocks = groupChatBlocks([
      msg({id: 't1', role: 'activity', tool: 'x', status: 'done'}),
    ]);
    expect(hasRunningActivity(blocks[0])).toBe(false);
  });

  it('keeps character products with their forge activity', () => {
    const blocks = groupChatBlocks([
      msg({id: 't1', role: 'activity', tool: 'render', status: 'running'}),
      msg({id: 'p1', role: 'product', text: 'Alice · 正面', product: {artifactId: 'alice-front', roleId: 'alice', roleVersion: 1, view: 'front', url: '/api/artifact', caption: 'Alice · 正面'}}),
    ]);
    expect(blocks).toHaveLength(1);
    expect(blocks[0]).toMatchObject({type: 'forge', activities: [expect.any(Object)], products: [expect.objectContaining({id: 'p1'})]});
  });
});
