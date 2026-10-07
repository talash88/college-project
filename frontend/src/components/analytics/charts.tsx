'use client';

/** Minimal dependency-free SVG charts for admin analytics. */

export interface NamedValue {
  label: string;
  value: number;
}

const PALETTE = ['#334e68', '#486581', '#627d98', '#829ab1', '#9fb3c8', '#bcccdc'];

export function HorizontalBars({
  data,
  formatValue,
  ariaLabel,
}: {
  data: NamedValue[];
  formatValue?: (_v: number) => string;
  ariaLabel: string;
}) {
  const max = Math.max(1, ...data.map((d) => d.value));
  const fmt = formatValue ?? ((v: number) => String(v));
  if (data.length === 0) {
    return <p className="text-sm text-secondary-500">No data.</p>;
  }
  return (
    <div role="img" aria-label={ariaLabel} className="space-y-2">
      {data.map((d, i) => (
        <div key={d.label} className="grid grid-cols-[minmax(0,10rem)_1fr_auto] items-center gap-2 text-sm">
          <span className="truncate text-secondary-700" title={d.label}>
            {d.label}
          </span>
          <div className="h-4 rounded bg-secondary-100 overflow-hidden">
            <div
              className="h-4 rounded"
              style={{
                width: `${Math.max(2, (d.value / max) * 100)}%`,
                backgroundColor: PALETTE[i % PALETTE.length],
              }}
            />
          </div>
          <span className="font-medium text-secondary-900 tabular-nums">{fmt(d.value)}</span>
        </div>
      ))}
    </div>
  );
}

export interface TrendBucket {
  bucket: string;
  reported: number;
  resolved: number;
}

function shortDate(iso: string): string {
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

export function TrendChart({ buckets }: { buckets: TrendBucket[] }) {
  const W = 640;
  const H = 220;
  const PAD_L = 36;
  const PAD_B = 28;
  const PAD_T = 12;
  const max = Math.max(1, ...buckets.map((b) => Math.max(b.reported, b.resolved)));
  const shown = buckets.slice(-20);
  const n = Math.max(1, shown.length);
  const groupW = (W - PAD_L - 8) / n;
  const barW = Math.max(3, Math.min(22, (groupW - 6) / 2));
  const scale = (v: number) => (H - PAD_B - PAD_T) * (v / max);
  const ticks = [0, 0.5, 1].map((f) => Math.round(max * f));
  return (
    <div role="img" aria-label="Reported versus resolved over time" className="w-full overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full min-w-[420px]" style={{ height: 220 }}>
        {ticks.map((t) => {
          const y = H - PAD_B - scale(t);
          return (
            <g key={t}>
              <line x1={PAD_L} y1={y} x2={W - 4} y2={y} stroke="#e2e8f0" strokeWidth={1} />
              <text x={PAD_L - 6} y={y + 4} textAnchor="end" fontSize={10} fill="#64748b">
                {t}
              </text>
            </g>
          );
        })}
        {shown.map((b, i) => {
          const x = PAD_L + 4 + i * groupW;
          const hr = scale(b.reported);
          const vr = scale(b.resolved);
          return (
            <g key={b.bucket}>
              <rect
                x={x}
                y={H - PAD_B - hr}
                width={barW}
                height={hr}
                rx={2}
                fill="#334e68"
              >
                <title>{`${shortDate(b.bucket)} reported: ${b.reported}`}</title>
              </rect>
              <rect
                x={x + barW + 3}
                y={H - PAD_B - vr}
                width={barW}
                height={vr}
                rx={2}
                fill="#829ab1"
              >
                <title>{`${shortDate(b.bucket)} resolved: ${b.resolved}`}</title>
              </rect>
              {i % Math.ceil(n / 8) === 0 && (
                <text x={x} y={H - 8} fontSize={10} fill="#64748b">
                  {shortDate(b.bucket)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <div className="mt-1 flex gap-4 text-xs text-secondary-600">
        <span className="inline-flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded-sm" style={{ backgroundColor: '#334e68' }} />
          Reported
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded-sm" style={{ backgroundColor: '#829ab1' }} />
          Resolved
        </span>
      </div>
    </div>
  );
}

export function DonutStat({ label, value, total }: { label: string; value: number; total: number }) {
  const pct = total > 0 ? Math.min(100, (value / total) * 100) : 0;
  const R = 26;
  const C = 2 * Math.PI * R;
  return (
    <div className="flex items-center gap-3">
      <svg width={64} height={64} viewBox="0 0 64 64" role="img" aria-label={`${label}: ${value} of ${total}`}>
        <circle cx={32} cy={32} r={R} fill="none" stroke="#e2e8f0" strokeWidth={8} />
        <circle
          cx={32}
          cy={32}
          r={R}
          fill="none"
          stroke="#334e68"
          strokeWidth={8}
          strokeLinecap="round"
          strokeDasharray={`${(pct / 100) * C} ${C}`}
          transform="rotate(-90 32 32)"
        />
        <text x={32} y={36} textAnchor="middle" fontSize={13} fontWeight={700} fill="#0f172a">
          {Math.round(pct)}%
        </text>
      </svg>
      <div>
        <p className="text-sm font-medium text-secondary-900">{label}</p>
        <p className="text-xs text-secondary-500">
          {value} of {total}
        </p>
      </div>
    </div>
  );
}
