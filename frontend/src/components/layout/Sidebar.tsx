"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth-context";

interface NavItem {
  href: string;
  label: string;
  icon: React.ReactNode;
  badge?: string;
}

// SVG icons as inline components (avoids lucide import until it installs)
const Icon = {
  Bot: () => (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="11" width="18" height="10" rx="2" /><path d="M12 11V7"/><circle cx="12" cy="4" r="2"/><path d="M8 11V9a4 4 0 0 1 8 0v2"/>
    </svg>
  ),
  Brain: () => (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96-.46 2.5 2.5 0 0 1-1.07-4.78 3 3 0 0 1 .34-5.58 2.5 2.5 0 0 1 1.32-4.24A2.5 2.5 0 0 1 9.5 2Z"/><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96-.46 2.5 2.5 0 0 0 1.07-4.78 3 3 0 0 0-.34-5.58 2.5 2.5 0 0 0-1.32-4.24A2.5 2.5 0 0 0 14.5 2Z"/>
    </svg>
  ),
  FileText: () => (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><line x1="10" y1="9" x2="8" y2="9"/>
    </svg>
  ),
  Zap: () => (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
    </svg>
  ),
  Settings: () => (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
    </svg>
  ),
  Shield: () => (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    </svg>
  ),
  ChevronLeft: () => (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="15 18 9 12 15 6"/>
    </svg>
  ),
  Plus: () => (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
    </svg>
  ),
  LogOut: () => (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>
    </svg>
  ),
  Activity: () => (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
    </svg>
  ),
};

const navItems: NavItem[] = [
  { href: "/chat", label: "AI Chat", icon: <Icon.Bot /> },
  { href: "/memory", label: "Memories", icon: <Icon.Brain /> },
  { href: "/documents", label: "Documents", icon: <Icon.FileText /> },
  { href: "/automation", label: "Automation", icon: <Icon.Zap /> },
  { href: "/approvals", label: "Approvals", icon: <Icon.Shield /> },
  { href: "/activity", label: "Activity", icon: <Icon.Activity /> },
  { href: "/settings", label: "Settings", icon: <Icon.Settings /> },
];

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  const initials = user?.full_name
    ? user.full_name.split(" ").map((n) => n[0]).join("").toUpperCase().slice(0, 2)
    : user?.email?.[0]?.toUpperCase() ?? "U";

  return (
    <aside
      className={cn(
        "flex flex-col h-full bg-[var(--aura-bg-surface)] border-r border-[var(--aura-border)] transition-all duration-[var(--duration-normal)] overflow-hidden",
        collapsed ? "w-16" : "w-[260px]"
      )}
      aria-label="Main navigation"
    >
      {/* Header */}
      <div className="flex items-center justify-between h-14 px-4 border-b border-[var(--aura-border)] shrink-0">
        {!collapsed && (
          <Link href="/chat" className="flex items-center gap-2.5 group">
            <div className="h-7 w-7 rounded-lg bg-[var(--aura-accent)] flex items-center justify-center shrink-0">
              <span className="text-white font-bold text-xs">A</span>
            </div>
            <span className="font-semibold text-[var(--aura-text-primary)] tracking-tight">
              AURA
            </span>
          </Link>
        )}
        {collapsed && (
          <div className="h-7 w-7 rounded-lg bg-[var(--aura-accent)] flex items-center justify-center mx-auto">
            <span className="text-white font-bold text-xs">A</span>
          </div>
        )}
        {!collapsed && (
          <button
            onClick={onToggle}
            className="p-1 rounded-md text-[var(--aura-text-muted)] hover:text-[var(--aura-text-primary)] hover:bg-[var(--aura-bg-hover)] transition-colors"
            aria-label="Collapse sidebar"
          >
            <Icon.ChevronLeft />
          </button>
        )}
      </div>

      {/* New Chat Button */}
      <div className="px-3 pt-3 pb-1 shrink-0">
        <Link
          href="/chat"
          className={cn(
            "flex items-center gap-2.5 w-full h-8 px-3 rounded-[var(--radius-md)] text-sm font-medium transition-all duration-[var(--duration-fast)]",
            "bg-[var(--aura-accent-subtle)] text-[var(--aura-accent-bright)] border border-[var(--aura-border-accent)]",
            "hover:bg-[var(--aura-accent)] hover:text-white hover:border-[var(--aura-accent)]",
            collapsed && "justify-center px-0"
          )}
          aria-label="New conversation"
        >
          <Icon.Plus />
          {!collapsed && <span>New Conversation</span>}
        </Link>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-2 px-3 space-y-0.5" aria-label="Workspace navigation">
        {navItems.map((item) => {
          const isActive = pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 h-9 px-2.5 rounded-[var(--radius-md)] text-sm transition-all duration-[var(--duration-fast)] group",
                collapsed && "justify-center px-0",
                isActive
                  ? "bg-[var(--aura-accent-subtle)] text-[var(--aura-accent-bright)]"
                  : "text-[var(--aura-text-secondary)] hover:text-[var(--aura-text-primary)] hover:bg-[var(--aura-bg-hover)]"
              )}
              aria-current={isActive ? "page" : undefined}
              title={collapsed ? item.label : undefined}
            >
              <span className={cn("shrink-0", isActive && "text-[var(--aura-accent-bright)]")}>
                {item.icon}
              </span>
              {!collapsed && (
                <span className="truncate">{item.label}</span>
              )}
              {!collapsed && item.badge && (
                <span className="ml-auto text-xs bg-[var(--aura-accent)] text-white rounded-full px-1.5 py-0.5 leading-none">
                  {item.badge}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Collapsed toggle button */}
      {collapsed && (
        <div className="px-3 pb-2 shrink-0">
          <button
            onClick={onToggle}
            className="flex items-center justify-center w-full h-8 rounded-[var(--radius-md)] text-[var(--aura-text-muted)] hover:text-[var(--aura-text-primary)] hover:bg-[var(--aura-bg-hover)] transition-colors rotate-180"
            aria-label="Expand sidebar"
          >
            <Icon.ChevronLeft />
          </button>
        </div>
      )}

      {/* User Profile */}
      <div className="px-3 pb-3 pt-2 border-t border-[var(--aura-border)] shrink-0">
        <div className={cn("flex items-center gap-2.5", collapsed && "justify-center")}>
          <div className="h-8 w-8 rounded-full bg-gradient-to-br from-[var(--aura-accent)] to-[var(--aura-cyan)] flex items-center justify-center shrink-0">
            <span className="text-white text-xs font-semibold">{initials}</span>
          </div>
          {!collapsed && (
            <>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-[var(--aura-text-primary)] truncate">
                  {user?.full_name ?? user?.email}
                </p>
                {user?.full_name && (
                  <p className="text-xs text-[var(--aura-text-muted)] truncate">{user.email}</p>
                )}
              </div>
              <button
                onClick={logout}
                className="p-1.5 rounded-md text-[var(--aura-text-muted)] hover:text-[var(--aura-error)] hover:bg-[var(--aura-error-subtle)] transition-colors shrink-0"
                aria-label="Sign out"
                title="Sign out"
              >
                <Icon.LogOut />
              </button>
            </>
          )}
        </div>
      </div>
    </aside>
  );
}
