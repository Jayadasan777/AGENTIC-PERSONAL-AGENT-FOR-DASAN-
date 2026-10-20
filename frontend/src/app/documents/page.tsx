"use client";

import { useState, useEffect, useRef } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { StatusBadge } from "@/components/ui/Badge";
import { documentsApi, type DocumentResponse, type RAGQueryResponse } from "@/lib/api";
import { formatBytes, formatRelativeTime } from "@/lib/utils";

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<DocumentResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // RAG Query Sandbox State
  const [ragQuery, setRagQuery] = useState("");
  const [isQuerying, setIsQuerying] = useState(false);
  const [ragResult, setRagResult] = useState<RAGQueryResponse | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchDocuments = async () => {
    setIsLoading(true);
    try {
      const data = await documentsApi.list({ limit: 50 });
      setDocuments(data);
    } catch (err) {
      console.error("Failed to load documents", err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, []);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    setUploadError(null);
    try {
      const doc = await documentsApi.upload(file);
      setDocuments((prev) => [doc, ...prev]);
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Document upload failed.";
      setUploadError(msg);
    } finally {
      setIsUploading(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Are you sure you want to delete this document and purge its vector embeddings?")) return;
    try {
      await documentsApi.delete(id, false);
      setDocuments((prev) => prev.filter((d) => d.id !== id));
    } catch (err) {
      alert(`Delete error: ${err instanceof Error ? err.message : "Failed"}`);
    }
  };

  const handleRagQuery = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ragQuery.trim()) return;
    setIsQuerying(true);
    try {
      const result = await documentsApi.queryRag(ragQuery.trim());
      setRagResult(result);
    } catch (err) {
      alert(`Query error: ${err instanceof Error ? err.message : "Failed"}`);
    } finally {
      setIsQuerying(false);
    }
  };

  const totalChunks = documents.reduce((acc, doc) => acc + (doc.total_chunks || 0), 0);
  const indexedDocs = documents.filter((d) => d.status.toLowerCase() === "indexed").length;

  return (
    <AppShell>
      <div className="max-w-6xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
          <div>
            <h1 className="text-2xl font-bold text-[var(--aura-text-primary)]">Knowledge & Document RAG</h1>
            <p className="text-xs text-[var(--aura-text-secondary)] mt-1">
              Ingest PDFs, markdown, text files, and research notes into vectorized chunks for grounded AI retrieval.
            </p>
          </div>

          <div>
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileUpload}
              className="hidden"
              accept=".pdf,.txt,.md,.docx,.json"
            />
            <Button
              variant="primary"
              size="sm"
              isLoading={isUploading}
              onClick={() => fileInputRef.current?.click()}
            >
              📤 Upload Document
            </Button>
          </div>
        </div>

        {uploadError && (
          <div className="mb-6 p-3 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-xs">
            {uploadError}
          </div>
        )}

        {/* Stats Row */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
          <div className="p-4 rounded-xl bg-[var(--aura-bg-surface)] border border-[var(--aura-border)]">
            <span className="text-xs text-[var(--aura-text-muted)]">Ingested Documents</span>
            <div className="text-2xl font-bold text-[var(--aura-text-primary)] mt-1">{documents.length}</div>
          </div>
          <div className="p-4 rounded-xl bg-[var(--aura-bg-surface)] border border-[var(--aura-border)]">
            <span className="text-xs text-[var(--aura-text-muted)]">Active Vector Chunks</span>
            <div className="text-2xl font-bold text-sky-400 mt-1">{totalChunks}</div>
          </div>
          <div className="p-4 rounded-xl bg-[var(--aura-bg-surface)] border border-[var(--aura-border)]">
            <span className="text-xs text-[var(--aura-text-muted)]">Indexed & Searchable</span>
            <div className="text-2xl font-bold text-emerald-400 mt-1">{indexedDocs}</div>
          </div>
        </div>

        {/* RAG Search & Testing Sandbox */}
        <div className="mb-8 p-5 rounded-2xl bg-[var(--aura-bg-surface)] border border-[var(--aura-border)]">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-base">🔍</span>
            <h2 className="text-sm font-semibold text-[var(--aura-text-primary)]">RAG Retrieval Sandbox</h2>
          </div>
          <form onSubmit={handleRagQuery} className="flex gap-2.5">
            <Input
              placeholder="Ask a question against your indexed documents (e.g. What are the key architecture decisions?)..."
              value={ragQuery}
              onChange={(e) => setRagQuery(e.target.value)}
              className="flex-1"
            />
            <Button type="submit" variant="primary" isLoading={isQuerying}>
              Synthesize Answer
            </Button>
          </form>

          {ragResult && (
            <div className="mt-4 p-4 rounded-xl bg-[var(--aura-bg-elevated)] border border-[var(--aura-border)]">
              <h3 className="text-xs font-semibold text-[var(--aura-accent-hover)] mb-2">Synthesized Answer:</h3>
              <p className="text-xs text-[var(--aura-text-primary)] leading-relaxed whitespace-pre-wrap mb-4">
                {ragResult.answer}
              </p>

              {ragResult.citations.length > 0 && (
                <div className="pt-3 border-t border-[var(--aura-border)]">
                  <span className="text-[11px] font-medium text-[var(--aura-text-muted)]">Citations & Confidence:</span>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-2">
                    {ragResult.citations.map((c, i) => (
                      <div key={i} className="text-xs p-2 rounded-lg bg-black/30 border border-[var(--aura-border)] flex items-center justify-between">
                        <span className="truncate max-w-[200px] text-zinc-300">📄 {c.document_name}</span>
                        <span className="font-mono text-[10px] text-emerald-400">{Math.round(c.score * 100)}% match</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Document Ingestion Table */}
        <div className="rounded-2xl bg-[var(--aura-bg-surface)] border border-[var(--aura-border)] overflow-hidden">
          <div className="px-6 py-4 border-b border-[var(--aura-border)] flex items-center justify-between">
            <h2 className="text-sm font-semibold text-[var(--aura-text-primary)]">Document Catalog</h2>
            <Button variant="ghost" size="sm" onClick={fetchDocuments} className="text-xs text-[var(--aura-text-muted)]">
              🔄 Refresh
            </Button>
          </div>

          {isLoading ? (
            <div className="py-16 text-center text-xs text-[var(--aura-text-muted)]">
              <div className="w-6 h-6 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin mx-auto mb-2" />
              Scanning document catalog...
            </div>
          ) : documents.length === 0 ? (
            <div className="py-16 text-center text-xs text-[var(--aura-text-muted)]">
              <div className="text-3xl mb-2">📂</div>
              <p>No documents uploaded yet. Add a PDF, Markdown, or text file to start vector search.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-[var(--aura-bg-elevated)] text-[var(--aura-text-muted)] border-b border-[var(--aura-border)]">
                  <tr>
                    <th className="px-6 py-3 font-medium">Filename</th>
                    <th className="px-6 py-3 font-medium">Size</th>
                    <th className="px-6 py-3 font-medium">Status</th>
                    <th className="px-6 py-3 font-medium">Chunks</th>
                    <th className="px-6 py-3 font-medium">Uploaded</th>
                    <th className="px-6 py-3 font-medium text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--aura-border)] text-[var(--aura-text-secondary)]">
                  {documents.map((doc) => (
                    <tr key={doc.id} className="hover:bg-[var(--aura-bg-elevated)]/50 transition-colors">
                      <td className="px-6 py-3.5 font-medium text-[var(--aura-text-primary)] flex items-center gap-2">
                        <span>📄</span>
                        <span className="truncate max-w-xs" title={doc.filename}>{doc.filename}</span>
                      </td>
                      <td className="px-6 py-3.5 font-mono text-[11px]">{formatBytes(doc.file_size_bytes)}</td>
                      <td className="px-6 py-3.5">
                        <StatusBadge status={doc.status} />
                      </td>
                      <td className="px-6 py-3.5 font-mono">{doc.total_chunks}</td>
                      <td className="px-6 py-3.5">{formatRelativeTime(doc.created_at)}</td>
                      <td className="px-6 py-3.5 text-right">
                        <button
                          onClick={() => handleDelete(doc.id)}
                          className="text-red-400 hover:text-red-300 text-xs transition-colors"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
