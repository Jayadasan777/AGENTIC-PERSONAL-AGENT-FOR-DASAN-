"use client";

import { useState, useEffect } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/Button";
import { automationApi } from "@/lib/api";
import { formatRelativeTime } from "@/lib/utils";

interface AuditEvent {
  id: string;
  event_type: string;
  event_data: Record<string, unknown>;
  task_id: string | null;
  schedule_id: string | null;
  occurred_at: string;
}

export default function ActivityPage() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedEvent, setSelectedEvent] = useState<AuditEvent | null>(null);

  const fetchAudit = async () => {
    setIsLoading(true);
    try {
      const res = await automationApi.getAuditLog(1, 50);
      setEvents(res.items);
    } catch (err) {
      console.error("Failed to load audit logs", err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchAudit();
  }, []);

  return (
    <AppShell>
      <div className="max-w-6xl mx-auto px-6 py-8">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
          <div>
            <h1 className="text-2xl font-bold text-[var(--aura-text-primary)]">System Audit & Activity Trail</h1>
            <p className="text-xs text-[var(--aura-text-secondary)] mt-1">
              Tamper-evident chronological log of all autonomous tool invocations, schedule triggers, and policy decisions.
            </p>
          </div>

          <Button variant="ghost" size="sm" onClick={fetchAudit} className="text-xs text-[var(--aura-text-muted)]">
            🔄 Refresh Trail
          </Button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Audit Event Stream */}
          <div className="lg:col-span-2 rounded-2xl bg-[var(--aura-bg-surface)] border border-[var(--aura-border)] overflow-hidden">
            <div className="px-6 py-3.5 border-b border-[var(--aura-border)] text-xs font-semibold text-[var(--aura-text-primary)]">
              Recorded Events ({events.length})
            </div>

            {isLoading ? (
              <div className="py-16 text-center text-xs text-[var(--aura-text-muted)]">
                <div className="w-6 h-6 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin mx-auto mb-2" />
                Querying cryptographic audit logs...
              </div>
            ) : events.length === 0 ? (
              <div className="py-16 text-center text-xs text-[var(--aura-text-muted)]">
                No activity events logged yet.
              </div>
            ) : (
              <div className="divide-y divide-[var(--aura-border)] max-h-[600px] overflow-y-auto">
                {events.map((event) => (
                  <div
                    key={event.id}
                    onClick={() => setSelectedEvent(event)}
                    className={`p-4 hover:bg-[var(--aura-bg-elevated)] cursor-pointer transition-colors flex items-center justify-between ${
                      selectedEvent?.id === event.id ? "bg-[var(--aura-bg-elevated)] border-l-2 border-[var(--aura-accent)]" : ""
                    }`}
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs font-medium text-[var(--aura-text-primary)]">
                          {event.event_type}
                        </span>
                        {event.task_id && (
                          <span className="text-[10px] px-1.5 py-0.2 bg-zinc-800 text-zinc-400 rounded">
                            Task: {event.task_id.slice(0, 8)}
                          </span>
                        )}
                      </div>
                      <div className="text-[11px] text-[var(--aura-text-muted)]">
                        {formatRelativeTime(event.occurred_at)}
                      </div>
                    </div>
                    <span className="text-xs text-[var(--aura-text-muted)]">Inspect →</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Event Detail Inspector */}
          <div className="rounded-2xl bg-[var(--aura-bg-surface)] border border-[var(--aura-border)] p-5">
            <h3 className="text-xs font-semibold text-[var(--aura-text-primary)] mb-3">Payload Inspector</h3>
            {selectedEvent ? (
              <div className="space-y-3">
                <div>
                  <span className="text-[10px] text-[var(--aura-text-muted)]">Event ID</span>
                  <div className="font-mono text-xs text-[var(--aura-text-secondary)]">{selectedEvent.id}</div>
                </div>
                <div>
                  <span className="text-[10px] text-[var(--aura-text-muted)]">Type</span>
                  <div className="text-xs font-semibold text-indigo-400">{selectedEvent.event_type}</div>
                </div>
                <div>
                  <span className="text-[10px] text-[var(--aura-text-muted)]">Timestamp</span>
                  <div className="text-xs text-[var(--aura-text-secondary)]">{new Date(selectedEvent.occurred_at).toLocaleString()}</div>
                </div>
                <div>
                  <span className="text-[10px] text-[var(--aura-text-muted)] mb-1 block">Event Data Payload</span>
                  <pre className="p-3 rounded-xl bg-black/50 border border-[var(--aura-border)] text-[11px] font-mono text-zinc-300 overflow-x-auto max-h-72">
                    {JSON.stringify(selectedEvent.event_data, null, 2)}
                  </pre>
                </div>
              </div>
            ) : (
              <div className="text-center py-20 text-xs text-[var(--aura-text-muted)]">
                Select an audit entry on the left to inspect its detailed parameters and policy outcome.
              </div>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
