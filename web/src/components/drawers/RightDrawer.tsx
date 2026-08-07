import {X} from 'lucide-react';
import {ReactNode} from 'react';

export default function RightDrawer({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <aside
      aria-hidden={!open}
      className={`flex h-full w-[360px] shrink-0 flex-col border-l border-line bg-bg-raised transition-transform duration-200 ${
        open ? 'translate-x-0' : 'translate-x-full'
      }`}
      style={{marginRight: open ? 0 : '-360px'}}
    >
      <header className="flex items-center justify-between border-b border-line px-4 py-2.5">
        <h2 className="text-sm font-semibold text-ink-primary">{title}</h2>
        <button
          onClick={onClose}
          aria-label="关闭面板"
          className="flex h-7 w-7 items-center justify-center rounded-md text-ink-secondary transition-colors hover:bg-line hover:text-ink-primary"
        >
          <X size={16} />
        </button>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
    </aside>
  );
}