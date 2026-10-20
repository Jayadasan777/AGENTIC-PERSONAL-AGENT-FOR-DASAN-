"use client";

import { useState, useEffect } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/ui/Badge";
import { agentApi, type PendingApproval, type KillSwitchResponse } from "@/lib/api";
import { formatRelativeTime } from "@/lib/utils";

export default function ApprovalsPage() {
  const [approvals, setApprovals] = useState<PendingApproval[]>([]);
  const [killSwitch, setKillSwitch] = useState<KillSwitchResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isActing, setIsActing] = useState<string | null>(null);

  const loadData = async () => {
    setIsLoading(true);
    try {
      const [apprData, ksData] = await Promise.all([
        agentApi.listApprovals(),
        agentApi.getKillSwitch(),
      ]);
      setApprovals(apprData);
      setKillSwitch(ksData);
    } catch (err) {
      console.error("Failed to load approvals", err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 10000); // 10s auto-refresh
    return () => clearInterval(interval);
  }, []);

  const handleDecision = async (approvalId: string, approved: boolean) => {
    setIsActing(approvalId);
    try {
      await agentApi.decide(
        approvalId,
        approved,
        approved ? "Explicit user consent granted via Approvals portal" : "Rejected by user"
      );
      setApprovals((prev) => prev.filter((a) => a.approval_id !== approvalId));
    } catch (err) {
      alert(`Decision error: ${err instanceof Error ? err.message : "Failed"}`);
    } finally {
      setIsActing(null);
    }
  };

  const handleToggleKillSwitch = async () => {
    if (!killSwitch) return;
    const next = !killSwitch.is_engaged;
    const reason = prompt(
      next
        ? "Enter reason for engaging Emergency Kill Switch:"
        : "Enter reason for restoring normal agent operation:"
    );
    if (reason === null) return;

    try {
      const updated = await agentApi.toggleKillSwitch(next, reason);
      setKillSwitch(updated);
    } catch (err) {
      alert(`Kill switch toggle error: ${err instanceof Error ? err.message : "Failed"}`);
    }
  };

  return (
    <AppShell>
      <div className="max-w-6xl mx-auto px-6 py-8">
        {/* Page Title */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
          <div>
            <h1 className="text-2xl font-bold text-[var(--aura-text-primary)]">Human-in-the-Loop Governance</h1>
            <p className="text-xs text-[var(--aura-text-secondary)] mt-1">
              Deterministic policy enforcement, tool authorization gates, and emergency agent intercept.
            </p>
          </div>

          <Button variant="ghost" size="sm" onClick={loadData} className="text-xs text-[var(--aura-text-muted)]">
            🔄 Refresh Queue
          </Button>
        </div>

        {/* Emergency Kill Switch Banner / Card */}
        <div
          className={`p-5 rounded-2xl mb-8 border transition-all flex flex-col md:flex-row items-center justify-between gap-4 ${
            killSwitch?.is_engaged
              ? "bg-red-500/15 border-red-500/40 text-red-200"
              : "bg-[var(--aura-bg-surface)] border-[var(--aura-border)] text-[var(--aura-text-secondary)]"
          }`}
        >
          <div className="flex items-center gap-3.5">
            <div
              className={`w-10 h-10 rounded-xl flex items-center justify-center text-lg ${
                killSwitch?.is_engaged ? "bg-red-600 text-white animate-pulse" : "bg-[var(--aura-bg-elevated)]"
              }`}
            >
              🚨
            </div>
            <div>
              <div className="text-sm font-semibold text-[var(--aura-text-primary)]">
                Agent Hard Kill Switch
              </div>
              <div className="text-xs">
                {killSwitch?.is_engaged ? (
                  <span className="text-red-400 font-medium">
                    ENGAGED — All agent execution and external tool calls are locked. Reason: {killSwitch.reason}
                  </span>
                ) : (
                  <span>Disengaged · Normal autonomous execution permitted under policy guardrails.</span>
                )}
              </div>
            </div>
          </div>

          <Button
            variant={killSwitch?.is_engaged ? "success" : "danger"}
            size="sm"
            onClick={handleToggleKillSwitch}
            className="shrink-0"
          >
            {killSwitch?.is_engaged ? "🔓 Resume Agent System" : "🛑 Engage Emergency Stop"}
          </Button>
        </div>

        {/* Pending Approvals List */}
        <div className="mb-10">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-semibold text-[var(--aura-text-primary)]">Pending Action Gate Queue</h2>
            <span className="text-xs text-[var(--aura-text-muted)] font-mono">{approvals.length} pending actions</span>
          </div>

          {isLoading ? (
            <div className="py-16 text-center text-xs text-[var(--aura-text-muted)]">
              <div className="w-6 h-6 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin mx-auto mb-2" />
              Scanning security gate queue...
            </div>
          ) : approvals.length === 0 ? (
            <div className="py-14 text-center border border-dashed border-[var(--aura-border)] rounded-2xl bg-[var(--aura-bg-surface)]/40 text-xs text-[var(--aura-text-muted)]">
              <div className="text-3xl mb-2">🛡️</div>
              <p className="font-medium text-[var(--aura-text-primary)]">Security Queue Clear</p>
              <p className="mt-1">No agent tool calls currently await human sign-off.</p>
            </div>
          ) : (
            <div className="space-y-4">
              {approvals.map((appr) => (
                <div
                  key={appr.approval_id}
                  className="p-5 rounded-2xl bg-[var(--aura-bg-surface)] border border-amber-500/30 shadow-md shadow-amber-500/5 space-y-3"
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-bold text-[var(--aura-text-primary)]">
                        Action Request: <code className="text-indigo-400 bg-zinc-900 px-1.5 py-0.5 rounded text-xs">{appr.tool_name}</code>
                      </span>
                      <StatusBadge status={appr.risk_tier} />
                    </div>
                    <span className="text-xs text-[var(--aura-text-muted)] font-mono">
                      Expires: {formatRelativeTime(appr.expires_at)}
                    </span>
                  </div>

                  <p className="text-xs text-[var(--aura-text-secondary)]">
                    <strong className="text-[var(--aura-text-primary)]">Escalation Rationale:</strong> {appr.reason}
                  </p>

                  <div className="bg-black/50 p-3 rounded-xl border border-[var(--aura-border)] font-mono text-[11px] text-zinc-300 overflow-x-auto max-h-36">
                    {JSON.stringify(appr.args, null, 2)}
                  </div>

                  <div className="flex items-center justify-end gap-3 pt-2">
                    <Button
                      variant="danger"
                      size="sm"
                      isLoading={isActing === appr.approval_id}
                      onClick={() => handleDecision(appr.approval_id, false)}
                    >
                      Reject Action
                    </Button>
                    <Button
                      variant="success"
                      size="sm"
                      isLoading={isActing === appr.approval_id}
                      onClick={() => handleDecision(appr.approval_id, true)}
                    >
                      Authorize & Execute
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Policy Guardrails Reference */}
        <div className="p-5 rounded-2xl bg-[var(--aura-bg-surface)] border border-[var(--aura-border)]">
          <h3 className="text-sm font-semibold text-[var(--aura-text-primary)] mb-3">Security Tiers & Policy Boundaries</h3>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs">
            <div className="p-3 rounded-xl bg-[var(--aura-bg-elevated)] border border-[var(--aura-border)]">
              <div className="flex items-center gap-2 font-semibold text-emerald-400 mb-1">
                <span>Tier 1: Read-Only</span>
              </div>
              <p className="text-[var(--aura-text-muted)] text-[11px]">
                Memory search, knowledge retrieval, system health checks. Automatically allowed.
              </p>
            </div>
            <div className="p-3 rounded-xl bg-[var(--aura-bg-elevated)] border border-[var(--aura-border)]">
              <div className="flex items-center gap-2 font-semibold text-sky-400 mb-1">
                <span>Tier 2: Low-Risk</span>
              </div>
              <p className="text-[var(--aura-text-muted)] text-[11px]">
                Drafting notes, temporary caching, safe document chunking. Audited and auto-approved.
              </p>
            </div>
            <div className="p-3 rounded-xl bg-[var(--aura-bg-elevated)] border border-[var(--aura-border)]">
              <div className="flex items-center gap-2 font-semibold text-amber-400 mb-1">
                <span>Tier 3: Elevated</span>
              </div>
              <p className="text-[var(--aura-text-muted)] text-[11px]">
                File system writes, automation schedules, web requests. Requires Human Authorization.
              </p>
            </div>
            <div className="p-3 rounded-xl bg-[var(--aura-bg-elevated)] border border-[var(--aura-border)]">
              <div className="flex items-center gap-2 font-semibold text-red-400 mb-1">
                <span>Tier 4: Critical</span>
              </div>
              <p className="text-[var(--aura-text-muted)] text-[11px]">
                Permanent data purge, system shell execution, privilege modification. Strict block or manual override.
              </p>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
