import { BookOpen } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { api } from "@/lib/api-client";
import type { Playbook } from "@/types";

export function PlaybooksDialog({ incidentId }: { incidentId: string }) {
  const [playbooks, setPlaybooks] = useState<Playbook[] | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function handleOpenChange(open: boolean) {
    if (!open || playbooks !== null) return;
    setIsLoading(true);
    try {
      const result = await api.get<Playbook[]>(`/playbooks/${incidentId}`);
      setPlaybooks(result);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <Dialog onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <BookOpen className="h-4 w-4" />
          View retrieved playbooks
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[80vh] max-w-2xl overflow-y-auto scrollbar-thin">
        <DialogHeader>
          <DialogTitle>Guided Response Playbooks</DialogTitle>
          <DialogDescription>Retrieved via RAG based on this incident's title and MITRE mapping.</DialogDescription>
        </DialogHeader>

        {isLoading && <p className="text-sm text-fog-dim">Retrieving playbooks...</p>}
        {playbooks && playbooks.length === 0 && (
          <p className="text-sm text-fog-dim">No matching playbook found for this incident.</p>
        )}
        <div className="space-y-4">
          {playbooks?.map((playbook) => (
            <div key={playbook.id} className="rounded-md border border-panel-line bg-panel-raised/50 p-4">
              <p className="font-display text-sm font-semibold text-fog">{playbook.title}</p>
              <pre className="mt-2 whitespace-pre-wrap font-mono text-xs leading-relaxed text-fog-dim">
                {playbook.content}
              </pre>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
