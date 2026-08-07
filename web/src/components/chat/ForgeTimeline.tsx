import {useEffect, useState} from 'react';
import {ChevronDown, ChevronUp, Loader2} from 'lucide-react';
import {humanize} from '../../events';
import {activityToolKind, ActivityToolIcon} from './activityMeta';
import type {Message} from '../../types';

export default function ForgeTimeline({activities}: {activities: Message[]}) {
  const hasRunning = activities.some((a) => a.status === 'running');
  const [expanded, setExpanded] = useState(hasRunning);

  // 运行中步骤始终展开（M3 AC：正在工作应当可见）；用户手动折叠在无运行中时不被打断
  useEffect(() => {
    if (hasRunning) setExpanded(true);
  }, [hasRunning]);

  const running = activities.filter((a) => a.status === 'running');
  const done = activities.filter((a) => a.status === 'done');
  const errored = activities.filter((a) => a.status === 'error');

  return (
    <div className="forge-timeline mx-auto w-full max-w-3xl my-4">
      <button
        className="flex w-full items-center justify-between rounded-xl border border-line bg-bg-raised px-4 py-2.5 text-left transition-colors hover:border-line-strong"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        <div className="flex items-center gap-2">
          <span className={`relative flex h-2 w-2 ${hasRunning ? '' : 'opacity-60'}`}>
            {hasRunning && (
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-75" />
            )}
            <span className={`relative inline-flex h-2 w-2 rounded-full ${hasRunning ? 'bg-accent' : done.length > 0 ? 'bg-info' : errored.length > 0 ? 'bg-error' : 'bg-ink-faint'}`} />
          </span>
          <span className="text-sm font-medium text-ink-primary">
            {hasRunning ? '锻造进行中' : done.length > 0 ? `已完成 ${done.length} 个步骤` : '锻造过程'}
          </span>
          {running.length > 0 && (
            <span className="text-xs text-accent">
              {humanize(running[running.length - 1].tool || 'tool')}
            </span>
          )}
        </div>
        <span className="text-ink-faint">
          {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </span>
      </button>

      {expanded && (
        <div className="mt-1 space-y-1 rounded-xl border border-line bg-bg-raised/60 p-2">
          {activities.map((activity) => (
            <ActivityRow key={activity.id} activity={activity} />
          ))}
        </div>
      )}
    </div>
  );
}

function ActivityRow({activity}: {activity: Message}) {
  const kind = activityToolKind(activity.tool);
  const statusColor = activity.status === 'running'
    ? 'text-accent'
    : activity.status === 'error'
      ? 'text-error'
      : 'text-ink-secondary';
  const stage = activity.stage ? humanize(activity.stage) : '';
  const detail = stage.toLowerCase() === activity.text.toLowerCase()
    ? activity.text
    : [stage, activity.text].filter(Boolean).join(' · ');

  return (
    <div className="flex items-start gap-2.5 rounded-lg px-2 py-1.5 hover:bg-line/50">
      <div className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md ${statusColor}`}>
        {activity.status === 'running' ? (
          <Loader2 size={14} className="animate-spin" />
        ) : (
          <ActivityToolIcon tool={activity.tool} size={14} />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className={`text-sm font-medium ${statusColor}`}>
          {humanize(activity.tool || '工作流')}
        </div>
        <div className="truncate text-xs text-ink-faint">{detail}</div>
      </div>
    </div>
  );
}