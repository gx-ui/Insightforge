import {useEffect, useState} from 'react';
import {CirclePause, CircleStop, Loader2, RotateCw} from 'lucide-react';
import type {RunState} from '../../types';

export default function RunStatusBar({run, onStop}: {run: RunState; onStop?: () => void}) {
  const [now, setNow] = useState(Date.now());
  const active = run.status === 'running' || run.status === 'reconnecting' || run.status === 'waiting_user';

  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, [active]);

  if (!run.runId || run.status === 'idle') return null;
  const elapsed = Math.max(0, Math.floor((now - (run.startedAt || now)) / 1_000));
  const statusLabel = run.status === 'reconnecting'
    ? '连接正在恢复'
    : run.status === 'completed'
      ? '本轮已完成'
      : run.status === 'waiting_user'
        ? run.stage?.label || '等待确认角色图'
      : run.status === 'failed'
        ? '本轮未完成'
        : run.status === 'stopped'
          ? '本轮已停止'
          : run.stage?.label || '正在理解你的创作需求';

  return (
    <section className={`run-status-bar is-${run.status}`} aria-live="polite">
      <span className="run-status-icon" aria-hidden="true">
        {run.status === 'running' ? <Loader2 size={15} /> : run.status === 'reconnecting' ? <RotateCw size={15} /> : run.status === 'waiting_user' ? <CirclePause size={15} /> : <CircleStop size={15} />}
      </span>
      <div><small>导演运行</small><strong>{statusLabel}</strong></div>
      {active && <div className="run-status-actions"><time>已运行 {elapsed} 秒</time>{onStop && <button type="button" onClick={onStop}>停止</button>}</div>}
    </section>
  );
}
