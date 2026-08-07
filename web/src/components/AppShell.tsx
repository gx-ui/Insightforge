import {ReactNode} from 'react';
import AppRail from './AppRail';
import ProjectPanel from './ProjectPanel';
import TopBar, {type DrawerType} from './TopBar';
import RightDrawer from './drawers/RightDrawer';
import type {SessionSummary, ChatState} from '../types';
import type {Theme} from '../theme';

export default function AppShell({
  theme,
  onToggleTheme,
  sessions,
  selectedSessionId,
  projectPanelOpen,
  onToggleProjectPanel,
  onNewProject,
  onSelectSession,
  onDeleteSession,
  activeView,
  onNavigate,
  chat,
  agentReady,
  storyboardCount,
  activeDrawer,
  onToggleDrawer,
  storyboardContent,
  artifactsContent,
  children,
}: {
  theme: Theme;
  onToggleTheme: () => void;
  sessions: SessionSummary[];
  selectedSessionId: string;
  projectPanelOpen: boolean;
  onToggleProjectPanel: () => void;
  onNewProject: () => void;
  onSelectSession: (id: string) => void;
  onDeleteSession: (session: SessionSummary) => void;
  activeView: 'workspace' | 'settings';
  onNavigate: (view: 'workspace' | 'artifacts' | 'settings') => void;
  chat: ChatState;
  agentReady: boolean;
  storyboardCount: number;
  activeDrawer: DrawerType | null;
  onToggleDrawer: (type: DrawerType) => void;
  storyboardContent?: ReactNode;
  artifactsContent?: ReactNode;
  children: ReactNode;
}) {
  const showTopBar = activeView === 'workspace';

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-bg-canvas font-body text-ink-primary">
      <AppRail
        theme={theme}
        activePanel={activeView === 'settings' ? 'settings' : activeDrawer === 'artifacts' ? 'artifacts' : 'workspace'}
        projectPanelOpen={projectPanelOpen}
        onToggleProjectPanel={onToggleProjectPanel}
        onNavigate={onNavigate}
        onToggleTheme={onToggleTheme}
      />
      <ProjectPanel
        open={projectPanelOpen}
        sessions={sessions}
        selectedSessionId={selectedSessionId}
        onSelect={onSelectSession}
        onNew={onNewProject}
        onDelete={onDeleteSession}
      />
      <main className="flex min-w-0 flex-1 flex-col">
        {showTopBar && (
          <TopBar
            session={sessions.find((s) => s.sessionId === selectedSessionId)}
            chat={chat}
            agentReady={agentReady}
            storyboardCount={storyboardCount}
            activeDrawer={activeDrawer}
            onToggleDrawer={onToggleDrawer}
          />
        )}
        <div className="flex min-h-0 flex-1">
          <div className="min-w-0 flex-1">{children}</div>
          {activeView === 'workspace' && (
            <RightDrawer
              open={activeDrawer === 'storyboard'}
              title={storyboardCount > 0 ? `分镜 · ${storyboardCount}` : '分镜'}
              onClose={() => onToggleDrawer('storyboard')}
            >
              {storyboardContent}
            </RightDrawer>
          )}
          {activeView === 'workspace' && activeDrawer === 'artifacts' && (
            <RightDrawer
              open
              title="产物"
              onClose={() => onToggleDrawer('artifacts')}
            >
              {artifactsContent}
            </RightDrawer>
          )}
        </div>
      </main>
    </div>
  );
}