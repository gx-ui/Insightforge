import {useMemo, useState} from 'react';
import {Dropdown, Input, MenuProps, Modal} from 'antd';
import {MoreHorizontal, Plus, Search, Trash2} from 'lucide-react';
import {filterSessions, groupSessionsByTime, relativeTime, sessionTitle} from '../lib/sessionGroups';
import {humanize} from '../events';
import type {SessionSummary} from '../types';

export default function ProjectPanel({
  open,
  sessions,
  selectedSessionId,
  onSelect,
  onNew,
  onDelete,
}: {
  open: boolean;
  sessions: SessionSummary[];
  selectedSessionId: string;
  onSelect: (sessionId: string) => void;
  onNew: () => void;
  onDelete: (session: SessionSummary) => void;
}) {
  const [query, setQuery] = useState('');

  const filtered = useMemo(() => filterSessions(sessions, query), [sessions, query]);
  const groups = useMemo(() => groupSessionsByTime(filtered), [filtered]);

  if (!open) return null;

  return (
    <aside
      className="flex h-full w-[260px] shrink-0 flex-col border-r border-line bg-bg-raised"
      aria-label="项目面板"
    >
      <div className="flex items-center gap-2 px-3 pb-2 pt-3">
        <Input
          size="small"
          prefix={<Search size={14} className="text-ink-faint" />}
          placeholder="搜索项目"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          allowClear
          variant="borderless"
          className="h-8 rounded-lg bg-bg-canvas"
        />
        <button
          onClick={onNew}
          aria-label="新建项目"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent text-on-accent transition-transform hover:scale-[1.03] active:scale-95"
        >
          <Plus size={18} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-2">
        <Group label="今天" items={groups.today} selectedSessionId={selectedSessionId} onSelect={onSelect} onDelete={onDelete} />
        <Group label="本周" items={groups.thisWeek} selectedSessionId={selectedSessionId} onSelect={onSelect} onDelete={onDelete} />
        <Group label="更早" items={groups.earlier} selectedSessionId={selectedSessionId} onSelect={onSelect} onDelete={onDelete} />
        {filtered.length === 0 && (
          <div className="py-8 text-center text-sm text-ink-faint">暂无匹配的项目</div>
        )}
      </div>

      <div className="flex items-center gap-2 border-t border-line px-3 py-2.5">
        <div className="flex h-7 w-7 items-center justify-center rounded-full bg-accent/15 text-xs font-semibold text-accent">
          V
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-medium text-ink-primary">本地工作区</div>
          <div className="truncate text-xs text-ink-faint">InsightForge</div>
        </div>
      </div>
    </aside>
  );
}

function Group({
  label,
  items,
  selectedSessionId,
  onSelect,
  onDelete,
}: {
  label: string;
  items: SessionSummary[];
  selectedSessionId: string;
  onSelect: (sessionId: string) => void;
  onDelete: (session: SessionSummary) => void;
}) {
  if (items.length === 0) return null;
  return (
    <div className="mt-3">
      <div className="px-2 pb-1 text-xs font-medium text-ink-faint">{label}</div>
      <div className="space-y-0.5">
        {items.map((session) => (
          <SessionItem
            key={session.sessionId}
            session={session}
            selected={session.sessionId === selectedSessionId}
            onSelect={() => onSelect(session.sessionId)}
            onDelete={() => onDelete(session)}
          />
        ))}
      </div>
    </div>
  );
}

function SessionItem({
  session,
  selected,
  onSelect,
  onDelete,
}: {
  session: SessionSummary;
  selected: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  const menuItems: MenuProps['items'] = [
    {key: 'delete', icon: <Trash2 size={14} />, label: '删除项目', danger: true, onClick: onDelete},
  ];

  return (
    <div
      className={`group flex items-center gap-1.5 rounded-lg px-1.5 py-1.5 transition-colors ${
        selected ? 'bg-accent/12' : 'hover:bg-line'
      }`}
    >
      <button
        onClick={onSelect}
        className="min-w-0 flex-1 text-left"
        aria-current={selected ? 'page' : undefined}
      >
        <div className="truncate text-sm text-ink-primary">{sessionTitle(session)}</div>
        <div className="mt-0.5 flex items-center gap-1.5 text-xs text-ink-faint">
          <StagePill stage={session.stage} />
          <span>{relativeTime(session.updatedAt)}</span>
        </div>
      </button>
      <Dropdown menu={{items: menuItems}} trigger={['click']} placement="bottomRight">
        <button
          aria-label="更多操作"
          className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-ink-faint opacity-0 transition-opacity hover:bg-line hover:text-ink-primary group-hover:opacity-100 ${
            selected ? 'opacity-100' : ''
          }`}
        >
          <MoreHorizontal size={15} />
        </button>
      </Dropdown>
    </div>
  );
}

function StagePill({stage}: {stage: string}) {
  const color = stageColor(stage);
  return (
    <span className="inline-flex items-center gap-1">
      <i className={`h-1.5 w-1.5 rounded-full ${color}`} />
      <span>{humanize(stage || 'created')}</span>
    </span>
  );
}

function stageColor(stage: string): string {
  const s = stage.toLowerCase();
  if (s.includes('render')) return 'bg-[' + '#3ED6A4]';
  if (s.includes('planning') || s.includes('plan')) return 'bg-accent';
  if (s.includes('error')) return 'bg-error';
  if (s.includes('done') || s.includes('rendered')) return 'bg-info';
  return 'bg-ink-faint';
}