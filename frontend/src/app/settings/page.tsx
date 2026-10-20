"use client";

import { useState, useEffect } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/ui/Badge";
import { useAuth } from "@/lib/auth-context";
import { healthApi, agentApi, type HealthResponse } from "@/lib/api";

interface ToolInfo {
  name: string;
  description: string;
  risk_tier: string;
  parameters: Record<string, unknown>;
}

export default function SettingsPage() {
  const { user, logout } = useAuth();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [dbReady, setDbReady] = useState<string>("Checking...");
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchSystemInfo = async () => {
      setIsLoading(true);
      try {
        const [hData, rData, tData] = await Promise.allSettled([
          healthApi.check(),
          healthApi.ready(),
          agentApi.listTools(),
        ]);

        if (hData.status === "fulfilled") setHealth(hData.value);
        if (rData.status === "fulfilled") setDbReady(rData.value.database);
        if (tData.status === "fulfilled") setTools(tData.value);
      } catch (err) {
        console.error("Settings load error", err);
      } finally {
        setIsLoading(false);
      }
    };

    fetchSystemInfo();
  }, []);

  return (
    <AppShell>
      <div className="max-w-6xl mx-auto px-6 py-8">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
          <div>
            <h1 className="text-2xl font-bold text-[var(--aura-text-primary)]">System Configuration & Telemetry</h1>
            <p className="text-xs text-[var(--aura-text-secondary)] mt-1">
              Backend connectivity, active agent tool capabilities, database health, and authenticated profile.
            </p>
          </div>

          <Button variant="danger" size="sm" onClick={logout}>
            Log Out
          </Button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          {/* User Profile Card */}
          <div className="p-5 rounded-2xl bg-[var(--aura-bg-surface)] border border-[var(--aura-border)] space-y-4">
            <h2 className="text-sm font-semibold text-[var(--aura-text-primary)]">Authenticated Identity</h2>
            <div className="flex items-center gap-3.5">
              <div className="w-12 h-12 rounded-xl bg-gradient-to-tr from-sky-400 to-indigo-600 flex items-center justify-center text-white font-bold text-lg">
                {user?.full_name?.[0]?.toUpperCase() ?? user?.email?.[0]?.toUpperCase() ?? "U"}
              </div>
              <div>
                <div className="font-semibold text-sm text-[var(--aura-text-primary)]">
                  {user?.full_name || "Agent Operator"}
                </div>
                <div className="text-xs text-[var(--aura-text-muted)]">{user?.email || "Local Session"}</div>
              </div>
            </div>

            <div className="pt-3 border-t border-[var(--aura-border)] grid grid-cols-2 gap-2 text-xs">
              <div>
                <span className="text-[var(--aura-text-muted)]">User ID:</span>
                <p className="font-mono text-[11px] truncate">{user?.id || "local-01"}</p>
              </div>
              <div>
                <span className="text-[var(--aura-text-muted)]">Role:</span>
                <p className="font-medium text-emerald-400">
                  {user?.is_superuser ? "Superuser / Root" : "Standard Operator"}
                </p>
              </div>
            </div>
          </div>

          {/* Engine Health Status */}
          <div className="p-5 rounded-2xl bg-[var(--aura-bg-surface)] border border-[var(--aura-border)] space-y-4">
            <h2 className="text-sm font-semibold text-[var(--aura-text-primary)]">FastAPI Core Telemetry</h2>
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="p-3 rounded-xl bg-[var(--aura-bg-elevated)] border border-[var(--aura-border)]">
                <span className="text-[var(--aura-text-muted)] block mb-1">Backend Status</span>
                <div className="flex items-center gap-1.5 font-semibold text-emerald-400">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                  <span>{health?.status?.toUpperCase() || "ONLINE"}</span>
                </div>
              </div>

              <div className="p-3 rounded-xl bg-[var(--aura-bg-elevated)] border border-[var(--aura-border)]">
                <span className="text-[var(--aura-text-muted)] block mb-1">Database Connectivity</span>
                <div className="font-semibold text-sky-400">{dbReady}</div>
              </div>

              <div className="p-3 rounded-xl bg-[var(--aura-bg-elevated)] border border-[var(--aura-border)]">
                <span className="text-[var(--aura-text-muted)] block mb-1">AURA Version</span>
                <div className="font-mono text-zinc-300">{health?.version || "1.0.0-phase3"}</div>
              </div>

              <div className="p-3 rounded-xl bg-[var(--aura-bg-elevated)] border border-[var(--aura-border)]">
                <span className="text-[var(--aura-text-muted)] block mb-1">Environment</span>
                <div className="font-mono text-zinc-300">{health?.environment || "development"}</div>
              </div>
            </div>
          </div>
        </div>

        {/* Registered Agent Tools Registry */}
        <div className="rounded-2xl bg-[var(--aura-bg-surface)] border border-[var(--aura-border)] overflow-hidden">
          <div className="px-6 py-4 border-b border-[var(--aura-border)] flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold text-[var(--aura-text-primary)]">Agent Capability Tools Registry</h2>
              <p className="text-[11px] text-[var(--aura-text-muted)]">
                Deterministic tools loaded in the sandbox with active policy tiers.
              </p>
            </div>
            <span className="text-xs font-mono text-[var(--aura-text-muted)]">{tools.length} Registered</span>
          </div>

          {isLoading ? (
            <div className="py-12 text-center text-xs text-[var(--aura-text-muted)]">
              Loading tool manifests...
            </div>
          ) : tools.length === 0 ? (
            <div className="py-12 text-center text-xs text-[var(--aura-text-muted)]">
              No custom tools exposed via endpoint.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 p-6">
              {tools.map((tool) => (
                <div
                  key={tool.name}
                  className="p-4 rounded-xl bg-[var(--aura-bg-elevated)] border border-[var(--aura-border)] flex flex-col justify-between"
                >
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <code className="text-xs font-semibold text-indigo-400">{tool.name}</code>
                      <StatusBadge status={tool.risk_tier} />
                    </div>
                    <p className="text-xs text-[var(--aura-text-secondary)] line-clamp-2">
                      {tool.description}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
