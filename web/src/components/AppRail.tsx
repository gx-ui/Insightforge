import {FolderOpen, Image, Settings, Sun, Moon, Wand2} from 'lucide-react';
import {Tooltip} from 'antd';
import type {Theme} from '../theme';

type ActivePanel = 'workspace' | 'artifacts' | 'settings';

export default function AppRail({
  theme,
  activePanel,
  projectPanelOpen,
  onToggleProjectPanel,
  onNavigate,
  onToggleTheme,
}: {
  theme: Theme;
  activePanel: ActivePanel;
  projectPanelOpen: boolean;
  onToggleProjectPanel: () => void;
  onNavigate: (panel: ActivePanel) => void;
  onToggleTheme: () => void;
}) {
  const items: Array<{key: ActivePanel | 'projects'; icon: typeof FolderOpen; label: string}> = [
    {key: 'projects', icon: FolderOpen, label: projectPanelOpen ? '收起项目面板' : '展开项目面板'},
    {key: 'workspace', icon: Wand2, label: '工作区'},
    {key: 'artifacts', icon: Image, label: '产物'},
    {key: 'settings', icon: Settings, label: '设置'},
  ];

  return (
    <nav
      aria-label="主导航"
      className="flex h-full w-[60px] shrink-0 flex-col items-center gap-1 border-r border-line bg-bg-raised py-3"
    >
      <div className="mb-2 flex h-10 w-10 items-center justify-center">
        <span className="font-display text-xl font-bold text-accent">F</span>
      </div>
      {items.map((item) => {
        const Icon = item.icon;
        const isActive =
          item.key === 'projects' ? projectPanelOpen : activePanel === item.key;
        const onClick = () => {
          if (item.key === 'projects') {
            onToggleProjectPanel();
          } else {
            onNavigate(item.key as ActivePanel);
          }
        };
        return (
          <Tooltip key={item.key} title={item.label} placement="right">
            <button
              onClick={onClick}
              aria-label={item.label}
              aria-pressed={isActive}
              className={`flex h-10 w-10 items-center justify-center rounded-lg transition-colors ${
                isActive
                  ? 'bg-accent/15 text-accent'
                  : 'text-ink-secondary hover:bg-line hover:text-ink-primary'
              }`}
            >
              <Icon size={20} />
            </button>
          </Tooltip>
        );
      })}
      <div className="mt-auto">
        <Tooltip title={theme === 'dark' ? '浅色主题' : '深色主题'} placement="right">
          <button
            onClick={onToggleTheme}
            aria-label="切换主题"
            className="flex h-10 w-10 items-center justify-center rounded-lg text-ink-secondary transition-colors hover:bg-line hover:text-ink-primary"
          >
            {theme === 'dark' ? <Sun size={20} /> : <Moon size={20} />}
          </button>
        </Tooltip>
      </div>
    </nav>
  );
}