import {describe, expect, it} from 'vitest';
import {filterSessions, groupSessionsByTime, relativeTime, sessionTitle} from './sessionGroups';
import type {SessionSummary} from '../types';

function makeSession(overrides: Partial<SessionSummary> = {}): SessionSummary {
  return {
    sessionId: 's-1',
    projectName: '',
    workingDir: '',
    stage: 'created',
    summary: '',
    idea: '',
    updatedAt: new Date().toISOString(),
    createdAt: new Date().toISOString(),
    compactionTurns: 0,
    ...overrides,
  };
}

describe('session grouping by time', () => {
  it('groups sessions into today / this week / earlier', () => {
    const now = new Date('2026-08-07T10:00:00Z').getTime();
    const today = makeSession({updatedAt: '2026-08-07T08:00:00Z', sessionId: 'today'});
    const thisWeek = makeSession({updatedAt: '2026-08-03T08:00:00Z', sessionId: 'week'});
    const earlier = makeSession({updatedAt: '2026-07-20T08:00:00Z', sessionId: 'earlier'});
    const groups = groupSessionsByTime([today, thisWeek, earlier], now);
    expect(groups.today.map((s) => s.sessionId)).toEqual(['today']);
    expect(groups.thisWeek.map((s) => s.sessionId)).toEqual(['week']);
    expect(groups.earlier.map((s) => s.sessionId)).toEqual(['earlier']);
  });

  it('handles invalid timestamps by putting them in the earliest bucket', () => {
    const bad = makeSession({updatedAt: 'not-a-date', sessionId: 'bad'});
    const groups = groupSessionsByTime([bad], Date.now());
    expect(groups.earlier).toHaveLength(1);
  });
});

describe('session search filter', () => {
  it('matches project name case-insensitively', () => {
    const list = [
      makeSession({projectName: '科幻短片', sessionId: 'a'}),
      makeSession({projectName: '美食vlog', sessionId: 'b'}),
    ];
    expect(filterSessions(list, '科幻').map((s) => s.sessionId)).toEqual(['a']);
    expect(filterSessions(list, '')).toHaveLength(2);
  });

  it('matches stage', () => {
    const list = [makeSession({stage: 'rendering', sessionId: 'r'}), makeSession({stage: 'created', sessionId: 'c'})];
    expect(filterSessions(list, 'render').map((s) => s.sessionId)).toEqual(['r']);
  });

  it('returns empty for no match', () => {
    expect(filterSessions([makeSession()], 'nope')).toEqual([]);
  });
});

describe('session helpers', () => {
  it('sessionTitle falls back through projectName / idea / summary / id', () => {
    expect(sessionTitle(makeSession({projectName: '我的项目'}))).toBe('我的项目');
    expect(sessionTitle(makeSession({projectName: '', idea: '一个想法'}))).toBe('一个想法');
    expect(sessionTitle(undefined)).toBe('新视频');
  });

  it('relativeTime returns human friendly labels', () => {
    const base = Date.now();
    expect(relativeTime(new Date(base - 30_000).toISOString())).toMatch(/刚刚|分钟前/);
    expect(relativeTime(new Date(base - 3 * 3600_000).toISOString())).toContain('小时前');
    expect(relativeTime(new Date(base - 3 * 86_400_000).toISOString())).toContain('天前');
    expect(relativeTime('bad')).toBe('最近');
  });
});