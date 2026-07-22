import { Sparkles } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDateTime } from "@/lib/utils";
import type { AIResponseEntry } from "@/types";

export function AIExplanation({ responses }: { responses: AIResponseEntry[] }) {
  const latest = responses[responses.length - 1];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-sentinel" />
          AI Explanation
        </CardTitle>
      </CardHeader>
      <CardContent>
        {!latest && <p className="text-sm text-fog-dim">Generating explanation...</p>}
        {latest && (
          <div className="space-y-4">
            <div>
              <p className="text-xs uppercase tracking-wide text-fog-faint">What happened</p>
              <p className="mt-1.5 text-sm leading-relaxed text-fog">{latest.summary}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-fog-faint">Recommended actions</p>
              <ol className="mt-1.5 list-decimal space-y-1.5 pl-4 text-sm leading-relaxed text-fog">
                {latest.recommendation
                  .split(/\s*\d+[.)]\s*|\s*\|\s*/)
                  .map((step) => step.trim())
                  .filter(Boolean)
                  .map((step, index) => (
                    <li key={index}>{step}</li>
                  ))}
              </ol>
            </div>
            <p className="font-mono text-[11px] text-fog-faint">Generated {formatDateTime(latest.generated_at)}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
