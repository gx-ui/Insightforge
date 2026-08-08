export type SessionSummary = {
  sessionId: string;
  projectName: string;
  workingDir: string;
  stage: string;
  summary: string;
  idea: string;
  updatedAt: string;
  createdAt: string;
  compactionTurns: number;
};

export type ConfigSection = {
  model_provider?: string;
  model: string;
  base_url: string;
  api_key: string;
  has_api_key: boolean;
};

export type AgentConfig = {
  sections: Record<'llm' | 'image' | 'video' | 'embedding' | 'reranker', ConfigSection>;
};

export type Artifact = {
  path: string;
  name: string;
  kind: 'image' | 'video' | 'document';
  size: number;
  updatedAt: string;
  url: string;
};

export type WorkspaceUpload = {
  name: string;
  path: string;
  size: number;
};

export type JsonPrimitive = string | number | boolean | null;

export type JsonValue = JsonPrimitive | JsonValue[] | {[key: string]: JsonValue};

export type Message = {
  id: string;
  role: 'user' | 'assistant' | 'activity' | 'product' | 'error';
  text: string;
  createdAt?: string;
  tool?: string;
  status?: 'running' | 'done' | 'error';
  stage?: string;
  rawStage?: string;
  runId?: string;
  product?: CharacterProduct;
};

export type StageInfo = {
  group: string;
  stage: string;
  label: string;
};

export type RunState = {
  runId: string;
  status: 'idle' | 'running' | 'waiting_user' | 'completed' | 'failed' | 'stopped' | 'reconnecting';
  stage?: StageInfo;
  startedAt?: number;
  lastEventId?: string;
};

export type CharacterProduct = {
  artifactId: string;
  roleId: string;
  roleVersion: number;
  view: string;
  url: string;
  caption: string;
};

export type CharacterApprovalRole = {
  roleId: string;
  roleVersion: number;
  displayName: string;
  description: string;
  approved: boolean;
  products: CharacterProduct[];
};

export type CharacterApproval = {
  runId: string;
  sessionId: string;
  roles: CharacterApprovalRole[];
};

export type AgentEvent = {
  type?: string;
  turn_id?: string;
  run_id?: string;
  event_id?: string;
  session_id?: string | null;
  timestamp?: number;
  sequence?: number;
  tokens?: number;
  mode?: 'stream' | 'buffered';
  delta?: string;
  message?: string;
  phase?: string;
  status?: string;
  stream?: string;
  line?: string;
  assistant?: string;
  activeSessionId?: string;
  sessions?: SessionSummary[];
  tool?: {id?: string; name?: string; requested_name?: string};
  progress?: {stage?: string; message?: string; metadata?: Record<string, unknown>};
  stage_group?: string;
  stage?: string;
  label?: string;
  raw_stage?: string;
  product?: {
    kind?: string;
    artifact_id?: string;
    role_id?: string;
    role_version?: number;
    view?: string;
    url?: string;
    caption?: string;
  };
  approval?: {
    run_id?: string;
    session_id?: string;
    role_id?: string;
    role_version?: number;
    action?: 'edit' | 'regenerate' | 'confirm';
    changed?: boolean;
    ready_to_resume?: boolean;
    roles?: Array<{
      role_id?: string;
      role_version?: number;
      display_name?: string;
      description?: string;
      approved?: boolean;
      products?: Array<{
        artifact_id?: string;
        role_id?: string;
        role_version?: number;
        view?: string;
        url?: string;
        caption?: string;
      }>;
    }>;
  };
  tool_result?: {name?: string; ok?: boolean; content?: string; metadata?: Record<string, unknown>};
  session?: {
    active_session_id?: string;
    session?: {
      session_id?: string;
      working_dir?: string;
      stage?: string;
      summary?: string;
    } | null;
  };
  prompt_trace?: {
    total_estimated_tokens?: number;
    totals?: {total_tokens?: number; total_estimated_tokens?: number};
  };
  version?: number;
  scope?: string;
  preferences?: PreferenceSnapshot;
};


export type ImagePreferences = {
  aspect_ratio: string;
  model: string;
  quality: string;
};

export type VideoPreferences = {
  aspect_ratio: string;
  model: string;
  resolution: string;
};

export type PreferenceSnapshot = {
  image: ImagePreferences;
  video: VideoPreferences;
};
export type ChatState = {
  messages: Message[];
  busy: boolean;
  turnId: string;
  promptTokens: number;
  run: RunState;
  seenEventIds: string[];
  tokenBuffers: Record<string, Record<number, string>>;
  sessionId?: string;
  approval?: CharacterApproval;
};
