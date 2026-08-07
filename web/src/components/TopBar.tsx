import {PanelRightClose, PanelRightOpen} from 'lucide-react';
import {Tooltip} from 'antd';
import type {SessionSummary} from '../types';
import {sessionTitle} from '../lib/sessionGroups';
import {humanize} from '../events';
import type {ChatState} from '../types';

export type DrawerType = 'storyboard' | 'artifacts';

export default function TopBar({
  session,
  chat,
  agentReady,
  storyboardCount,
  activeDrawer,
  onToggleDrawer,
}: {
  session?: SessionSummary;
  chat: ChatState;
  agentReady: boolean;
  storyboardCount: number;
  activeDrawer: DrawerType | null;
  onToggleDrawer: (type: DrawerType) => void;
}) {
  const status = deriveAgentStatus(agentReady, chat);

  return (
    <header
      className="flex h-12 items-center gap-3 border-b border-line bg-bg-raised px-4"
      aria-label="顶栏"
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <h1 className="truncate text-sm font-semibold text-ink-primary">
            {session ? sessionTitle(session) : '未选择项目'}
          </h1>
          {session?.stage && (
            <span className="shrink-0 rounded-full border border-line px-2 py-0.5 text-xs text-ink-secondary">
              {humanize(session.stage)}
            </span>
          )}
        </div>
      </div>

      <AgentStatusPill status={status} />

      <div className="flex items-center gap-1">
        <Tooltip title="分镜面板">
          <button
            onClick={() => onToggleDrawer('storyboard')}
            aria-label="切换分镜面板"
            aria-pressed={activeDrawer === 'storyboard'}
            className={`relative flex h-8 w-8 items-center justify-center rounded-md transition-colors ${
              activeDrawer === 'storyboard'
                ? 'bg-accent/15 text-accent'
                : 'text-ink-secondary hover:bg-line hover:text-ink-primary'
            }`}
          >
            <PanelRightClose size={18} />
            {storyboardCount > 0 && (
              <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-accent px-1 text-[10px] font-semibold text-on-accent">
                {storyboardCount}
              </span>
            )}
          </button>
        </Tooltip>
        <Tooltip title="产物面板">
          <button
            onClick={() => onToggleDrawer('artifacts')}
            aria-label="切换产物面板"
            aria-pressed={activeDrawer === 'artifacts'}
            className={`flex h-8 w-8 items-center justify-center rounded-md transition-colors ${
              activeDrawer === 'artifacts'
                ? 'bg-accent/15 text-accent'
                : 'text-ink-secondary hover:bg-line hover:text-ink-primary'
            }`}
          >
            <PanelRightOpen size={18} />
          </button>
        </Tooltip>
      </div>
    </header>
  );
}

type AgentStatus = 'ready' | 'working' | 'error' | 'idle';

function deriveAgentStatus(agentReady: boolean, chat: ChatState): AgentStatus {
  if (!agentReady) return 'idle';
  const reversed = [...chat.messages].reverse();
  // 最近的错误来源：独立 error 消息，或 activity 状态为 error
  const lastErrorIndex = reversed.findIndex((m) => m.role === 'error' || (m.role === 'activity' && m.status === 'error'));
  const lastDoneIndex = reversed.findIndex((m) => m.role === 'assistant' || (m.role === 'activity' && m.status === 'done'));
  const errorIsNewest = lastErrorIndex >= 0 && (lastDoneIndex < 0 || lastErrorIndex < lastDoneIndex);
  if (chat.busy) return 'working';
  if (errorIsNewest) return 'error';
  return 'ready';
}

function AgentStatusPill({status}: {status: AgentStatus}) {
  const config = {
    ready: {label: '就绪', dot: 'bg-info', glow: false},
    working: {label: '工作中', dot: 'bg-accent', glow: true},
    error: {label: '错误', dot: 'bg-error', glow: false},
    idle: {label: '未启动', dot: 'bg-ink-faint', glow: false},
  }[status];

  return (
    <div
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition-all ${
        config.glow
          ? 'border-accent/40 bg-accent/10 text-accent'
          : 'border-line bg-bg-canvas text-ink-secondary'
      }`}
    >
      <span className="relative flex h-1.5 w-1.5">
        {config.glow && (
          <span
            className={`absolute inline-flex h-full w-full animate-ping rounded-full ${config.dot} opacity-70`}
          />
        )}
        <span className={`relative inline-flex h-1.5 w-1.5 rounded-full ${config.dot}`} />
      </span>
      <span>{config.label}</span>
    </div>
  );
}