import { cn } from "@/lib/utils";

interface SecurityScoreGaugeProps {
  score: number; // 0-100
}

/**
 * The dashboard's signature element: a radar/sonar-style dial.
 * SentinelAI is, conceptually, an always-watching sentinel — this gauge
 * renders the security score as concentric radar rings with a slow
 * rotating sweep, rather than a generic donut/progress chart.
 */
export function SecurityScoreGauge({ score }: SecurityScoreGaugeProps) {
  const clamped = Math.max(0, Math.min(100, score));
  const circumference = 2 * Math.PI * 70;
  const offset = circumference * (1 - clamped / 100);

  const tone =
    clamped >= 80 ? "text-sentinel" : clamped >= 50 ? "text-threat-medium" : "text-threat-critical";
  const ringColor =
    clamped >= 80 ? "#2DD4BF" : clamped >= 50 ? "#F5A623" : "#EF4444";

  return (
    <div className="relative flex h-56 w-56 items-center justify-center">
      {/* ambient radar rings */}
      <div className="absolute inset-0 rounded-full border border-panel-line" />
      <div className="absolute inset-6 rounded-full border border-panel-line" />
      <div className="absolute inset-12 rounded-full border border-panel-line" />

      {/* rotating sweep */}
      <div className="absolute inset-0 animate-radar-sweep [animation-duration:6s]">
        <div
          className="absolute left-1/2 top-1/2 h-1/2 w-px origin-top"
          style={{
            background: `linear-gradient(to bottom, ${ringColor}80, transparent)`,
          }}
        />
      </div>

      <svg viewBox="0 0 160 160" className="absolute inset-0 -rotate-90">
        <circle cx="80" cy="80" r="70" fill="none" stroke="#182642" strokeWidth="6" />
        <circle
          cx="80"
          cy="80"
          r="70"
          fill="none"
          stroke={ringColor}
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-all duration-700 ease-out"
        />
      </svg>

      <div className="relative flex flex-col items-center">
        <span className={cn("font-display text-5xl font-bold tabular-nums", tone)}>{Math.round(clamped)}</span>
        <span className="mt-1 text-xs uppercase tracking-widest text-fog-faint">Security Score</span>
      </div>
    </div>
  );
}
