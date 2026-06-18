// Small, reusable visual building blocks for rendering evaluation results on
// the tiles. All pure CSS/SVG - no charting library needed.

// Map a low/medium/high level (case-insensitive, substring match) to a colour.
export function levelColor(level: string): "green" | "amber" | "red" | "slate" {
  const l = level.toLowerCase();
  if (l.includes("low")) return "green";
  if (l.includes("medium") || l.includes("mod")) return "amber";
  if (l.includes("high")) return "red";
  return "slate";
}

const COLOR_CLASS: Record<string, string> = {
  green: "bg-brand-green/20 text-brand-green-dark",
  amber: "bg-amber-100 text-amber-700",
  red: "bg-red-100 text-red-700",
  slate: "bg-slate-100 text-slate-600",
  blue: "bg-brand-blue/10 text-brand-blue",
};

export function Badge({
  children,
  color = "slate",
}: {
  children: React.ReactNode;
  color?: keyof typeof COLOR_CLASS;
}) {
  return <span className={`chip ${COLOR_CLASS[color]}`}>{children}</span>;
}

export function Chips({ items }: { items: string[] }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((t, i) => (
        <span key={i} className="chip bg-slate-100 text-slate-600">
          {t}
        </span>
      ))}
    </div>
  );
}

// A circular gauge showing a score out of 10.
export function ScoreRing({ value, label }: { value: number; label: string }) {
  const pct = Math.max(0, Math.min(1, value / 10));
  const r = 26;
  const c = 2 * Math.PI * r;
  const color = value >= 7 ? "#84cc16" : value >= 4 ? "#f59e0b" : "#ef4444";
  return (
    <div className="flex items-center gap-3">
      <svg width="64" height="64" viewBox="0 0 64 64">
        <circle cx="32" cy="32" r={r} fill="none" stroke="#e2e8f0" strokeWidth="8" />
        <circle
          cx="32"
          cy="32"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - pct)}
          transform="rotate(-90 32 32)"
        />
        <text x="32" y="37" textAnchor="middle" className="fill-ink text-base font-extrabold">
          {value}
        </text>
      </svg>
      <span className="text-sm font-semibold text-muted">{label}</span>
    </div>
  );
}

// A labelled horizontal bar (value out of 10).
export function Bar({ label, value }: { label: string; value: number }) {
  const pct = Math.max(0, Math.min(100, (value / 10) * 100));
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs font-semibold">
        <span className="truncate pr-2">{label}</span>
        <span className="text-muted">{value}/10</span>
      </div>
      <div className="h-2 w-full rounded-full bg-slate-100">
        <div className="h-2 rounded-full bg-brand-blue" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

// A big number + caption, for stat callouts (e.g. TAM/SAM/SOM).
export function Stat({ value, caption }: { value: string; caption: string }) {
  return (
    <div className="rounded-xl bg-surface px-3 py-2 text-center">
      <div className="text-lg font-black text-brand-blue">{value}</div>
      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">
        {caption}
      </div>
    </div>
  );
}
