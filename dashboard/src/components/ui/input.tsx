import { forwardRef, type InputHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      ref={ref}
      className={cn(
        "flex h-10 w-full rounded-md border border-panel-line bg-panel-raised px-3 py-2 text-sm text-fog placeholder:text-fog-faint",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sentinel/50 focus-visible:border-sentinel/50",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      {...props}
    />
  )
);
Input.displayName = "Input";
