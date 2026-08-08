import {useEffect, useMemo, useState} from 'react';
import {ChevronDown, ChevronUp, FileJson, Film, Files, Image as ImageIcon, Maximize2, Video, X} from 'lucide-react';
import {getJsonArtifact} from './api';
import MediaPreviewDialog from './components/chat/MediaPreviewDialog';
import {
  activeRenderCheckpoint,
  deriveStoryboardReadiness,
  extractStoryboardPreviews,
  formatStructuredValue,
  friendlyArtifactTitle,
  friendlyFieldLabel,
  isJsonArtifact,
  isJsonObject,
  isJsonPrimitive,
  isArtifactPathField,
  isStoryboardArtifact,
  relatedVisualArtifacts,
  structuredRecordTitle,
  type ReadinessStatus,
  type StoryboardPreview,
} from './artifactPresentation';
import type {Artifact, JsonValue, SessionSummary} from './types';

export function ArtifactsView({session, artifacts}: {session?: SessionSummary; artifacts: Artifact[]}) {
  const jsonArtifacts = useMemo(
    () => artifacts.filter(isJsonArtifact).sort((left, right) => left.path.localeCompare(right.path, undefined, {numeric: true})),
    [artifacts],
  );
  const [selectedPath, setSelectedPath] = useState('');
  const selected = jsonArtifacts.find((artifact) => artifact.path === selectedPath) || jsonArtifacts[0];
  const [document, setDocument] = useState<JsonValue>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [view, setView] = useState<'all' | 'documents' | 'visuals'>('all');
  const [previewArtifact, setPreviewArtifact] = useState<Artifact>();
  const mediaArtifacts = useMemo(
    () => artifacts
      .filter((artifact) => artifact.kind === 'image' || artifact.kind === 'video')
      .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt)),
    [artifacts],
  );
  const relatedMedia = useMemo(
    () => selected ? relatedVisualArtifacts(selected, mediaArtifacts) : [],
    [selected, mediaArtifacts],
  );

  useEffect(() => {
    setSelectedPath((current) => jsonArtifacts.some((artifact) => artifact.path === current) ? current : jsonArtifacts[0]?.path || '');
  }, [jsonArtifacts]);

  useEffect(() => {
    let cancelled = false;
    setDocument(undefined);
    setError('');
    if (!selected) return () => { cancelled = true; };
    setLoading(true);
    void getJsonArtifact(selected)
      .then((payload) => !cancelled && setDocument(payload))
      .catch((reason) => !cancelled && setError(reason instanceof Error ? reason.message : String(reason)))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [selected?.path, selected?.updatedAt]);

  return (
    <section className="artifacts-view">
      <header>
        <div><span>生成的文件</span><h1>{session ? projectTitle(session) : '产物'}</h1></div>
        <span className="artifact-file-count">{jsonArtifacts.length} 个文档 · {mediaArtifacts.length} 个视觉素材</span>
      </header>
      <div className="artifact-view-switcher" role="tablist" aria-label="产物类型">
        {(['all', 'documents', 'visuals'] as const).map((option) => (
          <button
            key={option}
            role="tab"
            aria-selected={view === option}
            className={view === option ? 'is-selected' : ''}
            onClick={() => setView(option)}
          >
            {option === 'all' ? '全部' : option === 'documents' ? '文档' : '视觉'}
          </button>
        ))}
      </div>
      {!session ? (
        <ArtifactsEmpty title="选择一个项目" detail="规划后项目文件将显示在此处" />
      ) : (
        <>
          {(view === 'all' || view === 'documents') && (
            <section className="artifact-content-section">
              {view === 'all' && <SectionHeading title="项目产物" detail="文档及相关视觉素材" />}
              {jsonArtifacts.length === 0 ? (
                <ArtifactsEmpty title="尚无结构化文件" detail="规划后 JSON 产物将显示在此处" />
              ) : (
                <div className="artifact-browser">
                  <nav className="artifact-document-list" aria-label="生成的 JSON 文件">
                    <div className="artifact-document-list-title"><span>文档</span><span>{jsonArtifacts.length}</span></div>
                    {jsonArtifacts.map((artifact) => (
                      <button
                        key={artifact.path}
                        className={artifact.path === selected?.path ? 'is-selected' : ''}
                        onClick={() => setSelectedPath(artifact.path)}
                      >
                        <FileJson size={16} />
                        <span><strong>{friendlyArtifactTitle(artifact)}</strong><small>{formatBytes(artifact.size)}</small></span>
                      </button>
                    ))}
                  </nav>
                  <article className={`artifact-document ${view === 'all' ? 'has-related-visuals' : ''}`}>
                    {selected && (
                      <header>
                        <div><span>结构化视图</span><h2>{friendlyArtifactTitle(selected)}</h2></div>
                        <small>{formatBytes(selected.size)}</small>
                      </header>
                    )}
                    <div className="artifact-document-layout">
                      <div className="artifact-structured-content">
                        {loading ? (
                          <div className="artifact-document-state">正在加载文档…</div>
                        ) : error ? (
                          <div className="artifact-document-state is-error">{error}</div>
                        ) : document !== undefined && selected ? (
                          <StructuredDocument value={document} artifact={selected} />
                        ) : null}
                      </div>
                      {view === 'all' && (
                        <RelatedVisuals artifacts={relatedMedia} onPreview={setPreviewArtifact} />
                      )}
                    </div>
                  </article>
                </div>
              )}
            </section>
          )}
          {view === 'visuals' && (
            <VisualArtifacts artifacts={mediaArtifacts} onPreview={setPreviewArtifact} />
          )}
        </>
      )}
      {previewArtifact && <MediaPreviewDialog media={{kind: previewArtifact.kind === 'video' ? 'video' : 'image', url: mediaUrl(previewArtifact), title: visualArtifactLabel(previewArtifact), detail: formatBytes(previewArtifact.size)}} onClose={() => setPreviewArtifact(undefined)} />}
    </section>
  );
}

function VisualArtifacts({artifacts, onPreview}: {artifacts: Artifact[]; onPreview: (artifact: Artifact) => void}) {
  return (
    <section className="artifact-visuals">
      {artifacts.length > 0 ? (
        <div className="render-grid">
          {artifacts.map((artifact) => (
            <article key={artifact.path} className="render-item">
              <button className="render-media" onClick={() => onPreview(artifact)} aria-label={`预览 ${artifact.name}`}>
                {artifact.kind === 'image'
                  ? <img src={mediaUrl(artifact)} alt={artifact.name} />
                  : <video src={mediaUrl(artifact)} muted playsInline preload="metadata" />}
                <i>{artifact.kind === 'video' ? <Video size={15} /> : <ImageIcon size={15} />}</i>
              </button>
              <span className="render-copy">
                <strong>{visualArtifactLabel(artifact)}</strong>
                <small>{formatBytes(artifact.size)}</small>
              </span>
            </article>
          ))}
        </div>
      ) : (
        <div className="renders-empty">
          <Film size={24} />
          <strong>暂无视觉产物</strong>
          <span>渲染过程中图片和视频将显示在此处</span>
        </div>
      )}
    </section>
  );
}

function RelatedVisuals({artifacts, onPreview}: {artifacts: Artifact[]; onPreview: (artifact: Artifact) => void}) {
  return (
    <aside className="artifact-related-visuals" aria-label="相关视觉素材">
      <header>
        <div><span>相关视觉素材</span><strong>{artifacts.length}</strong></div>
        <small>{artifacts.length > 0 ? '选择以预览' : '等待渲染'}</small>
      </header>
      {artifacts.length > 0 ? (
        <div className="related-visual-grid">
          {artifacts.map((artifact) => (
            <button key={artifact.path} onClick={() => onPreview(artifact)} aria-label={`预览 ${visualArtifactLabel(artifact)}`}>
              <span>
                {artifact.kind === 'image'
                  ? <img src={mediaUrl(artifact)} alt={visualArtifactLabel(artifact)} />
                  : <video src={mediaUrl(artifact)} muted playsInline preload="metadata" />}
                <i><Maximize2 size={14} /></i>
              </span>
              <strong>{visualArtifactLabel(artifact)}</strong>
              <small>{formatBytes(artifact.size)}</small>
            </button>
          ))}
        </div>
      ) : (
        <div className="related-visual-empty">
          <ImageIcon size={19} />
          <span>匹配的图片和视频片段将显示在此文档旁</span>
        </div>
      )}
    </aside>
  );
}

function SectionHeading({title, detail}: {title: string; detail: string}) {
  return <header className="artifact-section-heading"><h2>{title}</h2><span>{detail}</span></header>;
}

export function StoryboardPanel({open, artifacts, activeRenderStage, onClose, onCountChange, embedded = false}: {
  open: boolean;
  artifacts: Artifact[];
  activeRenderStage?: string;
  onClose: () => void;
  onCountChange: (count: number) => void;
  embedded?: boolean;
}) {
  const storyboardArtifacts = useMemo(
    () => artifacts.filter(isStoryboardArtifact).sort((left, right) => left.path.localeCompare(right.path, undefined, {numeric: true})),
    [artifacts],
  );
  const [previews, setPreviews] = useState<StoryboardPreview[]>([]);
  const [index, setIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    setError('');
    setIndex(0);
    if (storyboardArtifacts.length === 0) {
      setLoading(false);
      setPreviews([]);
      onCountChange(0);
      return () => { cancelled = true; };
    }
    setLoading(true);
    void Promise.allSettled(storyboardArtifacts.map(async (artifact) => ({
      artifact,
      document: await getJsonArtifact(artifact),
    }))).then((results) => {
      if (cancelled) return;
      const loaded = results.flatMap((result) => result.status === 'fulfilled'
        ? extractStoryboardPreviews(result.value.document, result.value.artifact.path)
        : []);
      setPreviews(loaded);
      onCountChange(loaded.length);
      if (loaded.length === 0 && results.some((result) => result.status === 'rejected')) {
        setError('分镜描述无法加载');
      }
    }).finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [storyboardArtifacts, onCountChange]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'ArrowUp') setIndex((current) => Math.max(0, current - 1));
      if (event.key === 'ArrowDown') setIndex((current) => Math.min(previews.length - 1, current + 1));
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open, previews.length]);

  const current = previews[index];
  const readiness = useMemo(
    () => deriveStoryboardReadiness(artifacts, previews.length),
    [artifacts, previews.length],
  );
  const activeCheckpoint = activeRenderStage ? activeRenderCheckpoint(activeRenderStage) : undefined;
  return (
    <aside className={`storyboard-panel ${open ? 'is-open' : ''}`}>
      {!embedded && (
        <header>
          <div><strong>分镜</strong><span>{previews.length > 0 ? `${index + 1} / ${previews.length}` : '预览'}</span></div>
          <button className="icon-button" onClick={onClose} aria-label="关闭分镜预览"><X size={18} /></button>
        </header>
      )}
      <section className="render-readiness" aria-label="渲染就绪状态">
        <div className="render-readiness-summary">
          <strong>{readiness.readyToRender ? '就绪可渲染' : '规划未完成'}</strong>
        </div>
        <div className="render-checkpoints">
          <ReadinessCheckpoint
            label="分镜"
            detail={readiness.storyboards.count === 1 ? '1 个镜头' : `${readiness.storyboards.count} 个镜头`}
            status={readiness.storyboards.status}
          />
          <ReadinessCheckpoint
            label="镜头描述"
            detail={`${readiness.shotDescriptions.count}/${readiness.shotDescriptions.expected || 0}`}
            status={readiness.shotDescriptions.status}
          />
          <ReadinessCheckpoint
            label="镜头规划"
            detail={`${readiness.cameraPlans.count}/${readiness.cameraPlans.expected || 0}`}
            status={readiness.cameraPlans.status}
          />
        </div>
        <div className="render-stage-heading">
          <span>渲染</span>
          <small>{activeRenderStage ? '生成中' : readiness.render.finalVideo.status === 'ready' ? '完成' : readiness.render.started ? '部分完成' : '未开始'}</small>
        </div>
        <div className="render-checkpoints">
          <ReadinessCheckpoint
            label="关键帧"
            detail={`${readiness.render.frames.count}/${readiness.render.frames.expected || 0}`}
            status={readiness.render.frames.status}
            generating={activeCheckpoint === 'frames'}
          />
          <ReadinessCheckpoint
            label="视频片段"
            detail={`${readiness.render.clips.count}/${readiness.render.clips.expected || 0}`}
            status={readiness.render.clips.status}
            generating={activeCheckpoint === 'clips'}
          />
          <ReadinessCheckpoint
            label="最终视频"
            detail={readiness.render.finalVideo.status === 'ready' ? '就绪' : '等待中'}
            status={readiness.render.finalVideo.status}
            generating={activeCheckpoint === 'finalVideo'}
          />
        </div>
      </section>
      <div className="storyboard-description" aria-live="polite">
        {loading ? <span>正在加载分镜…</span> : error ? <span className="is-error">{error}</span> : current ? <p>{current.description}</p> : <span>暂无分镜描述</span>}
      </div>
      <footer>
        <button onClick={() => setIndex((currentIndex) => Math.max(0, currentIndex - 1))} disabled={index === 0 || previews.length === 0} aria-label="上一个分镜">
          <ChevronUp size={17} /><span>上一个</span>
        </button>
        <button onClick={() => setIndex((currentIndex) => Math.min(previews.length - 1, currentIndex + 1))} disabled={index >= previews.length - 1 || previews.length === 0} aria-label="下一个分镜">
          <ChevronDown size={17} /><span>下一个</span>
        </button>
      </footer>
    </aside>
  );
}

function ReadinessCheckpoint({label, detail, status, generating = false}: {label: string; detail: string; status: ReadinessStatus; generating?: boolean}) {
  return (
    <div className="render-checkpoint">
      <StatusLight status={status} generating={generating} />
      <span>{label}</span>
      <small>{detail}</small>
    </div>
  );
}

function StatusLight({status, generating = false}: {status: ReadinessStatus; generating?: boolean}) {
  return <i className={`status-light is-${status} ${generating ? 'is-generating' : ''}`} aria-label={generating ? `${status}, generating` : status} />;
}

function StructuredDocument({value, artifact}: {value: JsonValue; artifact: Artifact}) {
  if (Array.isArray(value)) {
    if (value.length === 0) return <div className="structured-empty">此文档为空</div>;
    if (value.every(isJsonPrimitive)) return <StructuredField label="内容" value={formatStructuredValue(value)} />;
    return (
      <div className="structured-records">
        {value.map((record, index) => (
          <StructuredRecord key={index} title={structuredRecordTitle(record, index, artifact)} value={record} depth={0} />
        ))}
      </div>
    );
  }
  if (isJsonObject(value)) return <StructuredRecord title="概览" value={value} depth={0} />;
  return <StructuredField label="内容" value={formatStructuredValue(value)} />;
}

function StructuredRecord({title, value, depth}: {title: string; value: JsonValue; depth: number}) {
  if (!isJsonObject(value)) return <StructuredField label={title} value={formatStructuredValue(value)} />;
  const entries = Object.entries(value).filter(([key]) => !isArtifactPathField(key));
  const fields = entries.filter(([, entryValue]) => isJsonPrimitive(entryValue) || isPrimitiveArray(entryValue));
  const nested = entries.filter(([, entryValue]) => !isJsonPrimitive(entryValue) && !isPrimitiveArray(entryValue));
  return (
    <section className={`structured-record depth-${Math.min(depth, 3)}`}>
      <header><h3>{title}</h3></header>
      {fields.length > 0 && (
        <div className="structured-fields">
          {fields.map(([key, entryValue]) => (
            <StructuredField key={key} label={friendlyFieldLabel(key)} value={formatStructuredValue(entryValue, key)} />
          ))}
        </div>
      )}
      {nested.map(([key, entryValue]) => (
        <StructuredNested key={key} label={friendlyFieldLabel(key)} value={entryValue} depth={depth + 1} />
      ))}
    </section>
  );
}

function StructuredNested({label, value, depth}: {label: string; value: JsonValue; depth: number}) {
  if (depth > 5) return <StructuredField label={label} value="其他结构化详情" />;
  if (Array.isArray(value)) {
    if (value.length === 0) return <StructuredField label={label} value="无" />;
    return (
      <section className="structured-nested">
        <h4>{label}</h4>
        {value.map((item, index) => <StructuredRecord key={index} title={`${label} ${index + 1}`} value={item} depth={depth} />)}
      </section>
    );
  }
  return <StructuredRecord title={label} value={value} depth={depth} />;
}

function StructuredField({label, value}: {label: string; value: string}) {
  return (
    <div className={`structured-field ${value.length > 100 ? 'is-long' : ''}`}>
      <span>{label}</span>
      <p>{value}</p>
    </div>
  );
}

function ArtifactsEmpty({title, detail}: {title: string; detail: string}) {
  return (
    <div className="artifacts-empty">
      <Files size={24} />
      <strong>{title}</strong>
      <span>{detail}</span>
    </div>
  );
}

function isPrimitiveArray(value: JsonValue): value is Array<string | number | boolean | null> {
  return Array.isArray(value) && value.every(isJsonPrimitive);
}

function projectTitle(session: SessionSummary): string {
  return session.projectName || session.idea || session.summary || '未命名视频';
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function mediaUrl(artifact: Artifact): string {
  const separator = artifact.url.includes('?') ? '&' : '?';
  return `${artifact.url}${separator}updated=${encodeURIComponent(artifact.updatedAt)}`;
}

function visualArtifactLabel(artifact: Artifact): string {
  const scene = artifact.path.match(/(?:^|\/)scene_(\d+)(?:\/|$)/i)?.[1];
  const shot = artifact.path.match(/(?:^|\/)shots\/(\d+)(?:\/|$)/i)?.[1];
  const portrait = artifact.path.match(/(?:^|\/)character_portraits\/([^/]+)\/([^/]+)$/i);
  const base = artifact.name
    .replace(/\.[^.]+$/, '')
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (character) => character.toUpperCase());
  if (portrait) return `${portrait[1]} · ${base}`;
  const context = [];
  if (scene !== undefined) context.push(`Scene ${Number(scene) + 1}`);
  if (shot !== undefined) context.push(`Shot ${Number(shot) + 1}`);
  return context.length > 0 ? `${context.join(' · ')} · ${base}` : base;
}
