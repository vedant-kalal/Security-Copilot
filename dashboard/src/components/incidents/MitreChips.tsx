import { describeMitreTechnique } from "@/lib/mitre";

export function MitreChips({ techniques }: { techniques: string[] }) {
  if (techniques.length === 0) return <span className="text-xs text-fog-faint">No techniques mapped</span>;

  return (
    <div className="flex flex-wrap gap-1.5">
      {techniques.map((id) => (
        <span
          key={id}
          title={describeMitreTechnique(id)}
          className="rounded border border-panel-line bg-panel-raised px-1.5 py-0.5 font-mono text-[11px] text-fog-dim"
        >
          {id}
        </span>
      ))}
    </div>
  );
}
