import {
  Brain,
  Braces,
  FilePenLine,
  FileText,
  Film,
  Folder,
  Image as ImageIcon,
  ListChecks,
  Search,
  Terminal,
  Clock3,
  Wrench,
  LucideIcon,
} from 'lucide-react';

export function activityToolKind(tool?: string): string {
  const name = (tool || '').toLowerCase();
  if (name.includes('narrative_planning') || name.includes('novel_planning')) return 'planning';
  if (name.includes('render_video')) return 'render';
  if (name === 'view_image' || name.includes('image')) return 'image';
  if (name.startsWith('memory_')) return 'memory';
  if (name.startsWith('todo_')) return 'todo';
  if (name === 'run_shell') return 'shell';
  if (name === 'sleep') return 'time';
  return 'file';
}

export function ActivityToolIcon({tool, size = 14}: {tool?: string; size?: number}) {
  const name = (tool || '').toLowerCase();
  const props = {size, strokeWidth: 1.8};
  let Icon: LucideIcon = Wrench;
  if (name.includes('narrative_planning') || name.includes('novel_planning')) Icon = FilePenLine;
  else if (name.includes('render_video')) Icon = Film;
  else if (name === 'view_image' || name.includes('image')) Icon = ImageIcon;
  else if (name === 'read_json' || name === 'write_json') Icon = Braces;
  else if (name === 'read_file' || name === 'write_file') Icon = FileText;
  else if (name === 'list_files' || name === 'glob_files') Icon = Folder;
  else if (name === 'search_text') Icon = Search;
  else if (name.startsWith('memory_')) Icon = Brain;
  else if (name.startsWith('todo_')) Icon = ListChecks;
  else if (name === 'run_shell') Icon = Terminal;
  else if (name === 'sleep') Icon = Clock3;
  return <Icon {...props} />;
}