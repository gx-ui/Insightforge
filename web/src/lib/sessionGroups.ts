import type {SessionSummary} from '../types';

export function groupSessionsByTime(sessions: SessionSummary[], now: number = Date.now()): {
  today: SessionSummary[];
  thisWeek: SessionSummary[];
  earlier: SessionSummary[];
} {
  const today: SessionSummary[] = [];
  const thisWeek: SessionSummary[] = [];
  const earlier: SessionSummary[] = [];
  const dayMs = 24 * 60 * 60 * 1000;
  const todayStart = new Date(now);
  todayStart.setHours(0, 0, 0, 0);
  const todayBoundary = todayStart.getTime();
  const weekBoundary = todayBoundary - 6 * dayMs;

  for (const session of sessions) {
    const ts = Date.parse(session.updatedAt);
    const t = Number.isFinite(ts) ? ts : 0;
    if (t >= todayBoundary) {
      today.push(session);
    } else if (t >= weekBoundary) {
      thisWeek.push(session);
    } else {
      earlier.push(session);
    }
  }

  return {today, thisWeek, earlier};
}

export function filterSessions(sessions: SessionSummary[], query: string): SessionSummary[] {
  const q = query.trim().toLowerCase();
  if (!q) return sessions;
  return sessions.filter((session) => {
    const name = (session.projectName || session.idea || session.summary || '').toLowerCase();
    const stage = (session.stage || '').toLowerCase();
    return name.includes(q) || stage.includes(q);
  });
}

export function sessionTitle(session?: SessionSummary): string {
  if (!session) return '新视频';
  if (session.projectName) return session.projectName;
  const source = session.idea || session.summary;
  if (source) return source.length > 38 ? `${source.slice(0, 38).trim()}…` : source;
  return session.sessionId.replace(/^\d{8}-\d{6}-?/, '') || '未命名视频';
}

export function relativeTime(value: string): string {
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return '最近';
  const delta = Math.max(0, Date.now() - timestamp);
  const minutes = Math.floor(delta / 60_000);
  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} 天前`;
  const weeks = Math.floor(days / 7);
  if (weeks < 5) return `${weeks} 周前`;
  const months = Math.floor(days / 30);
  return `${months} 个月前`;
}