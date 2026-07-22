import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium font-mono transition-colors",
  {
    variants: {
      variant: {
        default: "border-panel-line bg-panel-raised text-fog-dim",
        sentinel: "border-sentinel/30 bg-sentinel/10 text-sentinel",
        low: "border-threat-low/30 bg-threat-low/10 text-threat-low",
        medium: "border-threat-medium/30 bg-threat-medium/10 text-threat-medium",
        high: "border-threat-high/30 bg-threat-high/10 text-threat-high",
        critical: "border-threat-critical/40 bg-threat-critical/15 text-threat-critical",
      },
    },
    defaultVariants: { variant: "default" },
  }
);

export interface BadgeProps extends HTMLAttributes<HTMLDivElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant, className }))} {...props} />;
}
