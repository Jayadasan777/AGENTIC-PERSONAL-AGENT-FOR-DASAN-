import * as React from "react";
import { cn } from "@/lib/utils";

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: "default" | "accent" | "success" | "warning" | "error" | "info" | "muted";
  dot?: boolean;
}

export function Badge({ variant = "default", dot, children, className, ...props }: BadgeProps) {
  const variantClasses: Record<string, string> = {
    default: "bg-[var(--aura-bg-elevated)] text-[var(--aura-text-secondary)] border-[var(--aura-border)]",
    accent: "bg-[var(--aura-accent-subtle)] text-[var(--aura-accent-bright)] border-[var(--aura-border-accent)]",
    success: "bg-[var(--aura-success-subtle)] text-[var(--aura-success)] border-[rgba(34,197,94,0.2)]",
    warning: "bg-[var(--aura-warning-subtle)] text-[var(--aura-warning)] border-[rgba(245,158,11,0.2)]",
    error: "bg-[var(--aura-error-subtle)] text-[var(--aura-error)] border-[rgba(239,68,68,0.2)]",
    info: "bg-[var(--aura-info-subtle)] text-[var(--aura-info)] border-[rgba(59,130,246,0.2)]",
    muted: "bg-transparent text-[var(--aura-text-muted)] border-[var(--aura-border)]",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium border",
        variantClasses[variant],
        className
      )}
      {...props}
    >
      {dot && (
        <span
          className="h-1.5 w-1.5 rounded-full"
          style={{ backgroundColor: "currentColor" }}
          aria-hidden="true"
        />
      )}
      {children}
    </span>
  );
}

// Status badge mapping for common AURA states
export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { variant: BadgeProps["variant"]; label: string }> = {
    // Task statuses
    pending: { variant: "info", label: "Pending" },
    running: { variant: "accent", label: "Running" },
    completed: { variant: "success", label: "Completed" },
    failed: { variant: "error", label: "Failed" },
    cancelled: { variant: "muted", label: "Cancelled" },
    paused: { variant: "warning", label: "Paused" },
    awaiting_approval: { variant: "warning", label: "Awaiting Approval" },
    // Document statuses
    indexed: { variant: "success", label: "Indexed" },
    processing: { variant: "accent", label: "Processing" },
    error: { variant: "error", label: "Error" },
    // Schedule statuses
    active: { variant: "success", label: "Active" },
    deleted: { variant: "muted", label: "Deleted" },
    // Kill switch
    engaged: { variant: "error", label: "ENGAGED" },
    disengaged: { variant: "success", label: "Safe" },
  };

  const config = map[status.toLowerCase()] ?? { variant: "muted" as const, label: status };
  return <Badge variant={config.variant} dot>{config.label}</Badge>;
}
