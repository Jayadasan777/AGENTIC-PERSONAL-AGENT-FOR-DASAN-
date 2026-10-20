"use client";

import { useAuth } from "@/lib/auth-context";
import { usePathname } from "next/navigation";

const pageTitles: Record<string, string> = {
  "/chat": "AI Chat",
  "/memory": "Memories",
  "/documents": "Documents",
  "/automation": "Automation",
  "/approvals": "Approvals",
  "/activity": "Activity",
  "/settings": "Settings",
};

export function Header() {
  const pathname = usePathname();
  const { user } = useAuth();

  const title = Object.entries(pageTitles).find(([path]) =>
    pathname === path || pathname.startsWith(path + "/")
  )?.[1] ?? "AURA";

  return (
    <header
      className="h-14 flex items-center justify-between px-6 border-b border-[var(--aura-border)] bg-[var(--aura-bg-surface)] shrink-0"
      role="banner"
    >
      {/* Page Title */}
      <div>
        <h1 className="text-sm font-semibold text-[var(--aura-text-primary)]">{title}</h1>
      </div>

      {/* Right controls */}
      <div className="flex items-center gap-2">
        {/* Backend status indicator */}
        <span className="flex items-center gap-1.5 text-xs text-[var(--aura-text-muted)]">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--aura-success)] animate-aura-pulse" aria-hidden="true" />
          Live
        </span>

        {user && (
          <div className="h-7 w-7 rounded-full bg-gradient-to-br from-[var(--aura-accent)] to-[var(--aura-cyan)] flex items-center justify-center ml-2">
            <span className="text-white text-[11px] font-semibold">
              {(user.full_name ?? user.email)[0].toUpperCase()}
            </span>
          </div>
        )}
      </div>
    </header>
  );
}
