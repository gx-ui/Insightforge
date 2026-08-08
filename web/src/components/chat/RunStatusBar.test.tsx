import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it} from 'vitest';
import RunStatusBar from './RunStatusBar';

describe('RunStatusBar', () => {
  it('shows the current stage and elapsed time', () => {
    const html = renderToStaticMarkup(
      <RunStatusBar run={{runId: 'turn-1', status: 'running', stage: {group: 'characters', stage: 'portraits', label: '正在生成角色图'}, startedAt: Date.now() - 3_000}} />,
    );
    expect(html).toContain('正在生成角色图');
    expect(html).toContain('已运行');
  });
});
