import {ArrowUp, CircleStop, FileText, Plus, X} from 'lucide-react';
import type {WorkspaceUpload} from '../../types';
import type {SlashCommandMatch} from '../../slashCommands';

export default function Composer({
  draft,
  onDraftChange,
  onSubmit,
  onStop,
  busy,
  disabled,
  uploadingFiles,
  workspaceUploads,
  onRemoveUpload,
  onFileClick,
  fileInputRef,
  textareaRef,
  onFilesSelected,
  contextPercent,
  showSlashCommands,
  slashMatches,
  onSlashSelect,
  loadError,
  onDismissError,
}: {
  draft: string;
  onDraftChange: (value: string) => void;
  onSubmit: () => void;
  onStop: () => void;
  busy: boolean;
  disabled: boolean;
  uploadingFiles: boolean;
  workspaceUploads: WorkspaceUpload[];
  onRemoveUpload: (path: string) => void;
  onFileClick: () => void;
  fileInputRef: React.RefObject<HTMLInputElement>;
  textareaRef: React.RefObject<HTMLTextAreaElement>;
  onFilesSelected: (files: FileList | null) => void;
  contextPercent: number;
  showSlashCommands: boolean;
  slashMatches: SlashCommandMatch[];
  onSlashSelect: (command: string) => void;
  loadError: string;
  onDismissError: () => void;
}) {
  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Tab' && slashMatches[0]) {
      event.preventDefault();
      onSlashSelect(slashMatches[0].name);
      return;
    }
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      onSubmit();
    }
  };

  return (
    <div className="composer-zone">
      {loadError && (
        <div className="inline-error" role="alert">
          <span>{loadError}</span>
          <button onClick={onDismissError} aria-label="关闭错误"><X size={15} /></button>
        </div>
      )}
      {showSlashCommands && (
        <SlashCommandMenu matches={slashMatches} contextPercent={contextPercent} onSelect={onSlashSelect} />
      )}
      <div className={`composer ${busy ? 'is-busy' : ''} relative overflow-hidden rounded-[12px] border bg-bg-raised`}>
        {busy && (
          <div className="forge-band-composer pointer-events-none" aria-hidden="true" />
        )}
        <textarea
          ref={textareaRef}
          value={draft}
          onChange={(e) => onDraftChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="描述你想要创作的内容"
          aria-label="向 InsightForge 发送消息"
          disabled={busy}
          rows={1}
          className="relative z-10 w-full resize-none bg-transparent px-4 pb-2 pt-3 text-[15px] leading-[1.7] text-ink-primary outline-none placeholder:text-ink-faint disabled:opacity-50"
        />

        {(workspaceUploads.length > 0 || uploadingFiles) && (
          <div className="relative z-10 flex flex-wrap gap-2 px-3 pb-2" aria-live="polite">
            {workspaceUploads.map((file) => (
              <span
                key={file.path}
                className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-bg-canvas px-2 py-1 text-xs text-ink-secondary"
                title={file.path}
              >
                <FileText size={13} className="text-ink-faint" />
                <span className="max-w-[160px] truncate">{file.name}</span>
                <span className="text-ink-faint">{formatBytes(file.size)}</span>
                <button
                  type="button"
                  onClick={() => onRemoveUpload(file.path)}
                  className="text-ink-faint transition-colors hover:text-ink-primary"
                  aria-label={`移除 ${file.name}`}
                >
                  <X size={12} />
                </button>
              </span>
            ))}
            {uploadingFiles && (
              <span className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-bg-canvas px-2 py-1 text-xs text-accent">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
                上传中…
              </span>
            )}
          </div>
        )}

        <div className="relative z-10 flex items-center gap-2 px-3 pb-3">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            onChange={(e) => onFilesSelected(e.currentTarget.files)}
            className="hidden"
            tabIndex={-1}
          />
          <button
            type="button"
            onClick={onFileClick}
            disabled={disabled || uploadingFiles || busy}
            aria-label="上传文件到工作区"
            aria-busy={uploadingFiles}
            title={disabled ? '请先创建或选择一个项目' : '上传文件到工作区'}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-ink-secondary transition-colors hover:bg-line hover:text-ink-primary disabled:opacity-40"
          >
            <Plus size={20} />
          </button>
          <div className="flex-1" />
          <div className="flex items-center gap-2 text-[11px] text-ink-faint">
            <ContextRing percent={contextPercent} />
            <span>{contextPercent}%</span>
          </div>
          {busy ? (
            <button
              onClick={onStop}
              aria-label="停止生成"
              className="flex h-9 w-9 items-center justify-center rounded-full bg-error text-on-accent shadow-lg shadow-error/20 transition-transform hover:scale-105 active:scale-95"
            >
              <CircleStop size={18} />
            </button>
          ) : (
            <button
              onClick={onSubmit}
              disabled={!draft.trim() || uploadingFiles}
              aria-label="发送消息"
              className="flex h-9 w-9 items-center justify-center rounded-full bg-accent text-on-accent shadow-lg shadow-accent/20 transition-all hover:scale-105 active:scale-95 disabled:opacity-30 disabled:shadow-none"
            >
              <ArrowUp size={19} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function ContextRing({percent}: {percent: number}) {
  const radius = 7;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - percent / 100);
  return (
    <svg width={18} height={18} viewBox="0 0 18 18">
      <circle cx={9} cy={9} r={radius} fill="none" stroke="currentColor" strokeOpacity={0.2} strokeWidth={2} />
      <circle
        cx={9}
        cy={9}
        r={radius}
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        strokeLinecap="round"
        className="text-accent transition-[stroke-dashoffset] duration-300"
        style={{transform: 'rotate(-90deg)', transformOrigin: 'center'}}
      />
    </svg>
  );
}

function SlashCommandMenu({matches, contextPercent, onSelect}: {matches: SlashCommandMatch[]; contextPercent: number; onSelect: (command: string) => void}) {
  return (
    <div className="slash-command-menu" role="listbox" aria-label="斜杠命令">
      {matches.length > 0 ? matches.map((command) => (
        <button key={command.name} role="option" aria-selected="false" onMouseDown={(e) => e.preventDefault()} onClick={() => onSelect(command.name)}>
          <code><span><b>{command.matchedPrefix}</b><span>{command.unmatchedSuffix}</span></span>{command.name === '/compact' && <em>{contextPercent}%</em>}</code>
          <small>{command.description}</small>
        </button>
      )) : <span className="slash-command-empty">无匹配命令</span>}
    </div>
  );
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}