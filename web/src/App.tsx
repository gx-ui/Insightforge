import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {FolderPlus, Trash2} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import AppShell from './components/AppShell';
import ArtifactsDrawer from './components/drawers/ArtifactsDrawer';
import SettingsView from './components/settings/SettingsView';
import type {DrawerType} from './components/TopBar';
import ForgeTimeline from './components/chat/ForgeTimeline';
import Composer from './components/chat/Composer';
import PreferenceBar from './components/chat/PreferenceBar';
import {DEFAULT_PREFERENCES} from './components/chat/preferences';
import EmptyState from './components/chat/EmptyState';

import {groupChatBlocks} from './lib/chatBlocks';
import {sessionTitle} from './lib/sessionGroups';
import {deleteSession, getArtifacts, getHistory, getSessions, sendMessage, startAgent, stopAgent, subscribeToEvents, updatePreferences, uploadWorkspaceFile} from './api';
import {StoryboardPanel} from './ArtifactViews';
import {applyAgentEvent, appendLocalUser, composeAgentPrompt, createChatState} from './events';
import {matchingSlashCommands, shouldShowSlashCommands} from './slashCommands';
import type {Theme} from './theme';
import type {AgentEvent, Artifact, ChatState, Message, PreferenceSnapshot, SessionSummary, WorkspaceUpload} from './types';

const CONTEXT_TARGET = 160_000;

type WorkspaceView = 'workspace' | 'settings';

export default function App({theme, onToggleTheme}: {theme: Theme; onToggleTheme: () => void}) {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState('');
  const [chat, setChat] = useState<ChatState>(() => createChatState());
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [workspaceView, setWorkspaceView] = useState<WorkspaceView>('workspace');
  const [agentReady, setAgentReady] = useState(false);
  // PRD 2.5：≥1280px 完整三栏；<1280px 项目面板默认收起（rail 始终可见）
  const [projectPanelOpen, setProjectPanelOpen] = useState(() => window.matchMedia('(min-width: 1280px)').matches);
  const [activeDrawer, setActiveDrawer] = useState<DrawerType | null>(null);
  const [storyboardCount, setStoryboardCount] = useState(0);
  const [draft, setDraft] = useState('');
  const [workspaceUploads, setWorkspaceUploads] = useState<WorkspaceUpload[]>([]);
  const [uploadingFiles, setUploadingFiles] = useState(false);
  const [preferences, setPreferences] = useState<PreferenceSnapshot>(DEFAULT_PREFERENCES);
  const [prefVersion, setPrefVersion] = useState(0);
  // 版本唯一事实源：同步预留下一个版本，避免快速连续编辑因 React state 异步更新产生重复版本被 Agent 丢弃
  const prefVersionRef = useRef(0);
  const applyPrefVersion = useCallback((value: number) => {
    prefVersionRef.current = value;
    setPrefVersion(value);
  }, []);
  const [loadError, setLoadError] = useState('');
  const [newProjectOpen, setNewProjectOpen] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [newProjectError, setNewProjectError] = useState('');
  const [creatingProject, setCreatingProject] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<SessionSummary>();
  const [deleting, setDeleting] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const selectedSession = sessions.find((session) => session.sessionId === selectedSessionId);
  const slashMatches = useMemo(() => matchingSlashCommands(draft), [draft]);
  const showSlashCommands = shouldShowSlashCommands(draft, chat.busy);
  const runningRender = useMemo(
    () => [...chat.messages].reverse().find((message) => message.role === 'activity'
      && message.status === 'running'
      && (message.tool || '').toLowerCase().includes('render_video')),
    [chat.messages],
  );

  const refreshSessions = useCallback(async () => {
    const state = await getSessions();
    setSessions(state.sessions);
    return state;
  }, []);

  const refreshArtifacts = useCallback(async (sessionId: string) => {
    if (!sessionId) {
      setArtifacts([]);
      return;
    }
    const payload = await getArtifacts(sessionId);
    setArtifacts(payload.artifacts);
  }, []);

  useEffect(() => subscribeToEvents((event) => {
    if (event.type === 'sessions_changed') {
      setSessions(event.sessions || []);
      if (event.activeSessionId) setSelectedSessionId(event.activeSessionId);
      return;
    }
    if (event.type === 'bridge_status') {
      if (event.status === 'ready' || event.status === 'starting') setAgentReady(true);
      if (event.status === 'stopped' || event.status === 'error') setAgentReady(false);
    }
    if (event.type === 'session') {
      const sessionId = event.session?.active_session_id || event.session?.session?.session_id || '';
      if (sessionId) {
        setSelectedSessionId(sessionId);
        void refreshSessions();
        void refreshArtifacts(sessionId);
      }
    }
    if (event.type === 'preference_state') {
      const v = Number(event.version) || 0;
      if (v >= prefVersionRef.current && event.preferences) {
        setPreferences(event.preferences);
        applyPrefVersion(v);
      }
      return;
    }
    setChat((current) => applyAgentEvent(current, event));
  }, () => undefined), [refreshArtifacts, refreshSessions, applyPrefVersion]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const state = await refreshSessions();
        if (cancelled || !state.activeSessionId) return;
        setSelectedSessionId(state.activeSessionId);
        const [history] = await Promise.all([
          getHistory(state.activeSessionId),
          refreshArtifacts(state.activeSessionId),
          startAgent({sessionId: state.activeSessionId}),
        ]);
        if (!cancelled) {
          setChat(createChatState(history.messages));
          setAgentReady(true);
        }
      } catch (error) {
        if (!cancelled) setLoadError(error instanceof Error ? error.message : String(error));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshArtifacts, refreshSessions]);

  useEffect(() => {
    if (!runningRender || !selectedSessionId) return;
    void refreshArtifacts(selectedSessionId);
    const interval = window.setInterval(() => void refreshArtifacts(selectedSessionId), 2_000);
    return () => {
      window.clearInterval(interval);
      void refreshArtifacts(selectedSessionId);
    };
  }, [refreshArtifacts, runningRender, selectedSessionId]);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;
    element.scrollTo({top: element.scrollHeight, behavior: chat.busy ? 'smooth' : 'auto'});
  }, [chat.messages, chat.busy]);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = '0px';
    textarea.style.height = `${Math.min(168, Math.max(28, textarea.scrollHeight))}px`;
  }, [draft]);

  useEffect(() => {
    setWorkspaceUploads([]);
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, [selectedSessionId]);

  // PRD 2.5：跨 1280px 断点时项目面板跟随"默认"开合；用户手动切换在无断点变化前保持
  useEffect(() => {
    const media = window.matchMedia('(min-width: 1280px)');
    const apply = () => setProjectPanelOpen(media.matches);
    apply();
    media.addEventListener('change', apply);
    return () => media.removeEventListener('change', apply);
  }, []);

  async function openSession(sessionId: string) {
    if (!sessionId || sessionId === selectedSessionId) {
      
      return;
    }
    setLoadError('');
    setSelectedSessionId(sessionId);
    // 切换会话时重置偏好版本，避免上一会话的高版本挡住新会话的 preference_state
    setPreferences(DEFAULT_PREFERENCES);
    applyPrefVersion(0);
    setChat(createChatState());
    try {
      const [history] = await Promise.all([
        getHistory(sessionId),
        refreshArtifacts(sessionId),
        startAgent({sessionId}),
      ]);
      setChat(createChatState(history.messages));
      setAgentReady(true);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : String(error));
    }
  }

  function openNewProjectDialog() {
    setNewProjectName('');
    setNewProjectError('');
    setNewProjectOpen(true);
  }

  async function newProject() {
    const projectName = newProjectName.trim();
    if (!projectName || creatingProject) return;
    setCreatingProject(true);
    setNewProjectError('');
    setLoadError('');
    
    try {
      await startAgent({newSession: true, projectName});
      setAgentReady(true);
      await new Promise((resolve) => window.setTimeout(resolve, 450));
      const state = await refreshSessions();
      setSelectedSessionId(state.activeSessionId);
      // 新建会话：重置偏好版本，让新会话的 preference_state 总是被采纳
      setPreferences(DEFAULT_PREFERENCES);
      applyPrefVersion(0);
      setChat(createChatState());
      setArtifacts([]);
      setWorkspaceView('workspace');
      setNewProjectOpen(false);
      setNewProjectName('');
      textareaRef.current?.focus();
    } catch (error) {
      setNewProjectError(error instanceof Error ? error.message : String(error));
    } finally {
      setCreatingProject(false);
    }
  }

async function handleUpdatePrefs(prefs: PreferenceSnapshot) {
    const base = prefVersionRef.current;   // 递增前的已知版本（server 端会 +1）
    const next = base + 1;
    applyPrefVersion(next);                // 同步预留，保证连续编辑严格递增
    setPreferences(prefs);                 // 乐观更新 UI
    try {
      const result = await updatePreferences(prefs, base);
      if (result.version !== next) applyPrefVersion(result.version);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : String(error));
    }
  }
  async function submit() {
    const text = draft.trim();
    if (!text || chat.busy || uploadingFiles) return;
    setLoadError('');
    setDraft('');
    setChat((current) => appendLocalUser(current, text));
    try {
      if (!agentReady) {
        await startAgent(selectedSessionId ? {sessionId: selectedSessionId} : {newSession: true});
        setAgentReady(true);
      }
      const outbound = composeAgentPrompt(text, workspaceUploads.map((file) => file.path));
      await sendMessage(outbound);
      setWorkspaceUploads([]);
    } catch (error) {
      const event: AgentEvent = {type: 'error', message: error instanceof Error ? error.message : String(error)};
      setChat((current) => applyAgentEvent(current, event));
    }
  }

  async function uploadFiles(files: FileList | null) {
    const sessionId = selectedSessionId;
    if (!files?.length) return;
    if (!sessionId) {
      setLoadError('请先创建或选择一个项目后再上传文件');
      return;
    }
    setUploadingFiles(true);
    setLoadError('');
    let uploadedAny = false;
    try {
      for (const file of Array.from(files)) {
        const result = await uploadWorkspaceFile(sessionId, file);
        uploadedAny = true;
        setWorkspaceUploads((current) => [
          ...current.filter((item) => item.path !== result.file.path),
          result.file,
        ]);
      }
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : String(error));
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = '';
      if (uploadedAny) await refreshArtifacts(sessionId);
      setUploadingFiles(false);
      textareaRef.current?.focus();
    }
  }

  async function stop() {
    await stopAgent();
    setAgentReady(false);
    setChat((current) => ({...current, busy: false}));
  }

  async function confirmDelete() {
    if (!pendingDelete || deleting) return;
    const sessionId = pendingDelete.sessionId;
    const deletingSelected = sessionId === selectedSessionId;
    setDeleting(true);
    setLoadError('');
    try {
      const state = await deleteSession(sessionId);
      setSessions(state.sessions);
      setPendingDelete(undefined);
      if (deletingSelected) {
        setSelectedSessionId('');
        setChat(createChatState());
        setArtifacts([]);
        setAgentReady(false);
        if (state.activeSessionId) await openSession(state.activeSessionId);
      }
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : String(error));
    } finally {
      setDeleting(false);
    }
  }

  const contextPercent = Math.min(100, Math.round((chat.promptTokens / CONTEXT_TARGET) * 100));
  const hasConversation = chat.messages.length > 0;

  const handleToggleDrawer = (type: DrawerType) => {
    setActiveDrawer((current) => (current === type ? null : type));
  };

  const handleNavigate = (view: 'workspace' | 'artifacts' | 'settings') => {
    if (view === 'artifacts') {
      // 从设置页进入产物时先切回工作区，保证抽屉可见
      if (workspaceView !== 'workspace') setWorkspaceView('workspace');
      setActiveDrawer((current) => (current === 'artifacts' ? null : 'artifacts'));
      return;
    }
    if (workspaceView !== view) {
      setWorkspaceView(view as 'workspace' | 'settings');
      // 进入设置页时收起右侧抽屉，避免返回时意外弹出
      if (view === 'settings') setActiveDrawer(null);
    }
  };

  return (
    <AppShell
      theme={theme}
      onToggleTheme={onToggleTheme}
      sessions={sessions}
      selectedSessionId={selectedSessionId}
      projectPanelOpen={projectPanelOpen}
      onToggleProjectPanel={() => setProjectPanelOpen((v) => !v)}
      onNewProject={openNewProjectDialog}
      onSelectSession={(id) => void openSession(id)}
      onDeleteSession={setPendingDelete}
      activeView={workspaceView === 'settings' ? 'settings' : 'workspace'}
      onNavigate={handleNavigate}
      chat={chat}
      agentReady={agentReady}
      storyboardCount={storyboardCount}
      activeDrawer={activeDrawer}
      onToggleDrawer={handleToggleDrawer}
      storyboardContent={
        <StoryboardPanel
          open={activeDrawer === 'storyboard'}
          artifacts={artifacts}
          activeRenderStage={runningRender?.stage}
          onClose={() => handleToggleDrawer('storyboard')}
          onCountChange={setStoryboardCount}
          embedded
        />
      }
      artifactsContent={<ArtifactsDrawer session={selectedSession} artifacts={artifacts} />}
    >
      {workspaceView === 'workspace' ? (
        <div className="flex h-full flex-col">
          <div className="flex-1 overflow-y-auto" ref={scrollRef}>
            <div className="mx-auto w-full max-w-3xl px-6 py-6">
              {!hasConversation ? (
                <EmptyState onPickExample={(text) => { setDraft(text); textareaRef.current?.focus(); }} />
              ) : (
                <div className="space-y-2">
                  {groupChatBlocks(chat.messages).map((block, i) =>
                    block.type === 'dialogue' ? (
                      <div key={i} className="space-y-3">
                        {block.messages.map((message) => (
                          <MessageRow key={message.id} message={message} />
                        ))}
                      </div>
                    ) : (
                      <ForgeTimeline key={i} activities={block.activities} />
                    )
                  )}
                  {chat.busy && !chat.messages.some(m => m.role === 'activity' && m.status === 'running') && (
                    <div className="text-center text-sm text-ink-faint">思考中…</div>
                  )}
                </div>
              )}
            </div>
          </div>
          <Composer
            draft={draft}
            onDraftChange={setDraft}
            onSubmit={() => void submit()}
            onStop={() => void stop()}
            busy={chat.busy}
            disabled={!selectedSessionId}
            uploadingFiles={uploadingFiles}
            workspaceUploads={workspaceUploads}
            onRemoveUpload={(path) => setWorkspaceUploads(curr => curr.filter(item => item.path !== path))}
            onFileClick={() => fileInputRef.current?.click()}
            fileInputRef={fileInputRef}
            textareaRef={textareaRef}
            onFilesSelected={(files) => void uploadFiles(files)}
            contextPercent={contextPercent}
            showSlashCommands={showSlashCommands}
            slashMatches={slashMatches}
            onSlashSelect={(cmd) => { setDraft(cmd); textareaRef.current?.focus(); }}
            loadError={loadError}
            onDismissError={() => setLoadError('')}
            prefsBar={
              selectedSessionId ? (
                <PreferenceBar
                  prefs={preferences}
                  version={prefVersion}
                  onUpdate={(prefs) => void handleUpdatePrefs(prefs)}
                />
              ) : undefined
            }
          />
        </div>      ) : (
        <div style={{height: '100%', overflow: 'auto'}}>
          <SettingsView />
        </div>
      )}

      <DeleteProjectDialog
        session={pendingDelete}
        deleting={deleting}
        onCancel={() => !deleting && setPendingDelete(undefined)}
        onConfirm={() => void confirmDelete()}
      />
      <NewProjectDialog
        open={newProjectOpen}
        name={newProjectName}
        error={newProjectError}
        creating={creatingProject}
        onNameChange={(value) => {
          setNewProjectName(value);
          setNewProjectError('');
        }}
        onCancel={() => {
          if (creatingProject) return;
          setNewProjectOpen(false);
          setNewProjectError('');
        }}
        onConfirm={() => void newProject()}
      />
    </AppShell>
  );
}

function MessageRow({message}: {message: Message}) {
  return (
    <article className={`message-row role-${message.role}`}>
      <div className="message-body">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={{a: (props) => <a {...props} target="_blank" rel="noreferrer" />}}>
          {message.text}
        </ReactMarkdown>
      </div>
    </article>
  );
}

function DeleteProjectDialog({session, deleting, onCancel, onConfirm}: {
  session?: SessionSummary;
  deleting: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  useEffect(() => {
    if (!session) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !deleting) onCancel();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [deleting, onCancel, session]);

  if (!session) return null;
  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onCancel()}>
      <section className="delete-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-project-title">
        <span className="dialog-icon"><Trash2 size={18} /></span>
        <div className="dialog-copy">
          <h2 id="delete-project-title">删除项目?</h2>
          <p><strong>{sessionTitle(session)}</strong> 及其生成的文件将被永久删除。</p>
        </div>
        <div className="dialog-actions">
          <button onClick={onCancel} disabled={deleting} autoFocus>取消</button>
          <button className="danger" onClick={onConfirm} disabled={deleting}>{deleting ? '删除中…' : '删除'}</button>
        </div>
      </section>
    </div>
  );
}

function NewProjectDialog({open, name, error, creating, onNameChange, onCancel, onConfirm}: {
  open: boolean;
  name: string;
  error: string;
  creating: boolean;
  onNameChange: (value: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !creating) onCancel();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [creating, onCancel, open]);

  if (!open) return null;
  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onCancel()}>
      <form className="project-dialog" role="dialog" aria-modal="true" aria-labelledby="new-project-title" onSubmit={(event) => {
        event.preventDefault();
        onConfirm();
      }}>
        <span className="dialog-icon is-create"><FolderPlus size={18} /></span>
        <div className="dialog-copy">
          <h2 id="new-project-title">创建新项目</h2>
          <p>请先为工作区命名后再创建。</p>
        </div>
        <label className="project-name-field">
          <span>项目名称</span>
          <input
            value={name}
            onChange={(event) => onNameChange(event.target.value)}
            placeholder="未命名视频"
            maxLength={64}
            autoFocus
            disabled={creating}
          />
          {error && <small role="alert">{error}</small>}
        </label>
        <div className="dialog-actions">
          <button type="button" onClick={onCancel} disabled={creating}>取消</button>
          <button type="submit" className="primary" disabled={creating || !name.trim()}>{creating ? '创建中…' : '创建'}</button>
        </div>
      </form>
    </div>
  );
}

