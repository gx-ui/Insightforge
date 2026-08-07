import {Sparkles} from 'lucide-react';

const EXAMPLES = [
  {icon: '🎬', title: '做一个科幻短片', hint: '赛博朋克城市 + 追逐场景'},
  {icon: '📖', title: '写一个成长故事', hint: '从平凡到不凡的旅程'},
  {icon: '🎨', title: '生成产品宣传视频', hint: '极简风格 + 轻快节奏'},
];

export default function EmptyState({onPickExample}: {onPickExample: (text: string) => void}) {
  return (
    <section className="flex h-full flex-col items-center justify-center px-6 text-center">
      <div className="relative mb-6">
        <div className="forge-empty-band absolute inset-0 -m-8 rounded-full blur-2xl" aria-hidden="true" />
        <div className="relative flex h-16 w-16 items-center justify-center rounded-2xl border border-accent/30 bg-accent/10 text-accent">
          <Sparkles size={32} />
        </div>
      </div>
      <h1 className="font-display text-[39px] leading-tight text-ink-primary">我们该创作什么？</h1>
      <p className="mt-2 max-w-md text-sm text-ink-secondary">
        描述你的创意，InsightForge 会规划故事、生成分镜、渲染视频，一步步锻造出属于你的作品。
      </p>
      <div className="mt-8 grid w-full max-w-xl gap-3 sm:grid-cols-3">
        {EXAMPLES.map((example) => (
          <button
            key={example.title}
            onClick={() => onPickExample(`${example.title}：${example.hint}`)}
            className="group flex flex-col items-start gap-1.5 rounded-xl border border-line bg-bg-raised p-4 text-left transition-all hover:-translate-y-0.5 hover:border-accent/40 hover:bg-bg-raised/80"
          >
            <span className="text-2xl">{example.icon}</span>
            <span className="text-sm font-medium text-ink-primary">{example.title}</span>
            <span className="text-xs text-ink-faint">{example.hint}</span>
          </button>
        ))}
      </div>
    </section>
  );
}