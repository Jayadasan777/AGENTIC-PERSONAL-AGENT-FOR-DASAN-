"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { agentApi, documentsApi, type StepTrace, type PendingApproval } from "@/lib/api";
import { formatRelativeTime } from "@/lib/utils";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  traces?: StepTrace[];
  pendingApproval?: PendingApproval | null;
}

export default function ChatPage() {
  const pathname = usePathname();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [selectedModel, setSelectedModel] = useState("AURA v2.5 Orchestrator");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  const handleSend = async (customPrompt?: string) => {
    const textToSend = customPrompt ?? input.trim();
    if (!textToSend || isLoading) return;

    const userMsg: ChatMessage = {
      id: `usr_${Date.now()}`,
      role: "user",
      content: textToSend,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg]);
    if (!customPrompt) setInput("");
    setIsLoading(true);

    try {
      const res = await agentApi.run(textToSend);
      const content =
        res.final_answer ??
        (res.pending_approval
          ? `🛡️ Human Approval Required: AURA proposed executing '${res.pending_approval.tool_name}'. Please review and approve below.`
          : res.error
          ? `⚠️ Error: ${res.error}`
          : "Task completed successfully.");

      setMessages((prev) => [
        ...prev,
        {
          id: `ast_${Date.now()}`,
          role: "assistant",
          content,
          timestamp: new Date().toISOString(),
          traces: res.traces,
          pendingApproval: res.pending_approval,
        },
      ]);
    } catch (err: unknown) {
      setMessages((prev) => [
        ...prev,
        {
          id: `ast_${Date.now()}`,
          role: "assistant",
          content: `⚠️ Failed to execute: ${err instanceof Error ? err.message : "Error"}`,
          timestamp: new Date().toISOString(),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDecision = async (
    approvalId: string,
    approved: boolean,
    toolName?: string,
    toolArgs?: Record<string, unknown>
  ) => {
    setIsLoading(true);
    // Remove the pending action buttons immediately so user can see it's processing
    setMessages((prev) =>
      prev.map((msg) =>
        msg.pendingApproval?.approval_id === approvalId
          ? { ...msg, pendingApproval: undefined }
          : msg
      )
    );

    try {
      const decisionRes = await agentApi.decide(approvalId, approved);
      if (approved && decisionRes.approval_token) {
        const safeArgs = toolArgs && Object.keys(toolArgs).length > 0 ? toolArgs : {};
        const res = await agentApi.run("Proceed with authorized action", {
          approval_token: decisionRes.approval_token,
          approved_tool: toolName,
          approved_args: safeArgs,
        });
        setMessages((prev) => [
          ...prev,
          {
            id: `ast_${Date.now()}`,
            role: "assistant",
            content: res.final_answer ?? "Action completed with user authorization.",
            timestamp: new Date().toISOString(),
            traces: res.traces,
          },
        ]);
      } else {
        setMessages((prev) => [
          ...prev,
          {
            id: `ast_${Date.now()}`,
            role: "assistant",
            content: "Action was rejected by user.",
            timestamp: new Date().toISOString(),
          },
        ]);
      }
    } catch (err: unknown) {
      alert(`Decision error: ${err instanceof Error ? err.message : "Failed"}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleNewChat = () => {
    setMessages([]);
    setInput("");
  };

  return (
    /* Outer vertical-striped purple backdrop matching Zyricon reference */
    <div className="min-h-screen bg-striped-purple p-3 md:p-6 flex items-center justify-center font-sans antialiased text-slate-200">
      
      {/* Main Tablet Frame - matching Zyricon layout, radii, and shadows */}
      <div className="w-full max-w-[1340px] h-[92vh] bg-[#0c0a14] border border-white/10 rounded-[28px] overflow-hidden shadow-2xl flex relative">
        
        {/* Left Sidebar - Zyricon dark bar */}
        <aside
          className={`bg-[#0e0c18] border-r border-white/5 flex flex-col justify-between transition-all duration-300 ${
            sidebarCollapsed ? "w-20 p-4" : "w-64 p-5"
          }`}
        >
          <div>
            {/* Logo row + Collapse toggle */}
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-2.5">
                <div className="w-7 h-7 rounded-full bg-gradient-to-tr from-purple-500 to-indigo-600 flex items-center justify-center text-white text-xs font-bold shadow-md shadow-purple-900/40">
                  ✦
                </div>
                {!sidebarCollapsed && (
                  <span className="font-bold text-base tracking-tight text-white">Zyricon</span>
                )}
              </div>
              <button
                onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
                className="text-slate-500 hover:text-slate-300 p-1"
                title="Toggle Sidebar"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect width="18" height="18" x="3" y="3" rx="2" />
                  <path d="M9 3v18" />
                </svg>
              </button>
            </div>

            {/* + New Chat Pill */}
            <button
              onClick={handleNewChat}
              className="w-full py-2 px-3 mb-6 rounded-xl bg-[#1b172a] hover:bg-[#231e36] border border-white/5 text-xs font-medium text-slate-300 flex items-center gap-2 transition-all"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
              {!sidebarCollapsed && <span>New Chat</span>}
            </button>

            {/* Navigation: Features */}
            {!sidebarCollapsed && (
              <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-2 px-1">
                Features
              </div>
            )}
            <nav className="space-y-1 mb-6">
              <Link
                href="/chat"
                className={`flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium transition-all ${
                  pathname === "/chat"
                    ? "bg-[#251e3a] text-purple-300 shadow-sm"
                    : "text-slate-400 hover:text-slate-200 hover:bg-white/5"
                }`}
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
                {!sidebarCollapsed && <span>Chat</span>}
              </Link>

              <Link
                href="/automation"
                className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-white/5 transition-all"
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="m22 8-6 4 6 4V8Z" />
                  <rect width="14" height="12" x="2" y="6" rx="2" />
                </svg>
                {!sidebarCollapsed && <span>Archived</span>}
              </Link>

              <Link
                href="/memory"
                className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-white/5 transition-all"
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z" />
                </svg>
                {!sidebarCollapsed && <span>Library</span>}
              </Link>
            </nav>

            {/* Navigation: Workspaces */}
            {!sidebarCollapsed && (
              <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-2 px-1">
                Workspaces
              </div>
            )}
            <nav className="space-y-1">
              {[
                { name: "New Project", href: "/chat" },
                { name: "Image", href: "/chat" },
                { name: "Presentation", href: "/chat" },
                { name: "Riset", href: "/documents" },
                { name: "Command Center", href: "/automation" },
              ].map((ws, i) => (
                <Link
                  key={i}
                  href={ws.href}
                  className="flex items-center gap-2.5 px-3 py-1.5 rounded-xl text-xs text-slate-400 hover:text-slate-200 hover:bg-white/5 transition-all"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z" />
                  </svg>
                  {!sidebarCollapsed && <span className="truncate">{ws.name}</span>}
                </Link>
              ))}
            </nav>
          </div>

          {/* Bottom Card: Upgrade to Premium */}
          {!sidebarCollapsed && (
            <div className="p-3.5 rounded-2xl bg-[#171324] border border-white/5 text-center mt-4">
              <div className="w-7 h-7 mx-auto rounded-full bg-purple-500/15 text-purple-400 flex items-center justify-center text-xs mb-2">
                👑
              </div>
              <h4 className="text-xs font-semibold text-white">Upgrade to premium</h4>
              <p className="text-[10px] text-slate-400 leading-tight mt-1 mb-2.5">
                Boost productivity with seamless automation and responsive AI, built to adapt to your needs.
              </p>
              <button className="w-full py-1.5 rounded-lg bg-[#272138] hover:bg-[#322a48] text-white text-xs font-medium transition-colors">
                Upgrade
              </button>
            </div>
          )}
        </aside>

        {/* Main Chat Canvas Area */}
        <main className="flex-1 flex flex-col justify-between bg-[#0c0a14] relative overflow-hidden">
          
          {/* Top Header Bar */}
          <header className="px-6 py-4 flex items-center justify-between border-b border-white/5">
            {/* Model Selector Dropdown */}
            <div className="relative">
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="bg-[#171424] text-xs font-medium text-slate-300 py-1.5 px-3 rounded-lg border border-white/10 focus:outline-none cursor-pointer"
              >
                <option value="ChatGPT v4.0">ChatGPT v4.0</option>
                <option value="AURA v2.5 Orchestrator">AURA v2.5 Orchestrator</option>
                <option value="Claude 3.5 Sonnet">Claude 3.5 Sonnet</option>
              </select>
            </div>

            {/* Right Buttons: Configuration & Export */}
            <div className="flex items-center gap-2.5 text-xs">
              <Link
                href="/settings"
                className="px-3 py-1.5 rounded-lg bg-[#171424] hover:bg-[#201c32] border border-white/10 text-slate-300 flex items-center gap-1.5 transition-colors"
              >
                <span>Configuration</span>
                <span>⚙</span>
              </Link>
              <button
                onClick={() => alert("Chat conversation exported.")}
                className="px-3 py-1.5 rounded-lg bg-[#171424] hover:bg-[#201c32] border border-white/10 text-slate-300 flex items-center gap-1.5 transition-colors"
              >
                <span>Export</span>
                <span>⤤</span>
              </button>
            </div>
          </header>

          {/* Central Area: Welcome or Message History */}
          <div className="flex-1 overflow-y-auto p-6 flex flex-col justify-center">
            {messages.length === 0 ? (
              /* Hero Empty State - Replicating Zyricon 3D Orb and Typography */
              <div className="max-w-xl mx-auto w-full flex flex-col items-center text-center my-auto">
                {/* 3D Iridescent Glowing Liquid Orb */}
                <div className="relative mb-5 flex items-center justify-center">
                  <div className="w-16 h-16 rounded-full orb-glow animate-pulse" />
                  <div className="absolute inset-0 rounded-full bg-white/20 blur-sm pointer-events-none" />
                </div>

                {/* Main Heading */}
                <h1 className="text-2xl md:text-3xl font-bold text-white tracking-tight mb-6">
                  Ready to Create Something New?
                </h1>

                {/* Prompt Starter Pills above input */}
                <div className="flex flex-wrap items-center justify-center gap-2 mb-6">
                  <button
                    onClick={() => handleSend("Create a futuristic design mockup for an agentic dashboard")}
                    className="px-3.5 py-1.5 rounded-full bg-[#181426] hover:bg-[#231e36] border border-white/5 text-xs text-slate-300 flex items-center gap-1.5 transition-all"
                  >
                    <span>Create Image</span>
                    <span>🖼️</span>
                  </button>
                  <button
                    onClick={() => handleSend("Brainstorm architecture improvements for autonomous memory caching")}
                    className="px-3.5 py-1.5 rounded-full bg-[#181426] hover:bg-[#231e36] border border-white/5 text-xs text-slate-300 flex items-center gap-1.5 transition-all"
                  >
                    <span>Brainstorm</span>
                    <span>💡</span>
                  </button>
                  <button
                    onClick={() => handleSend("Make an execution plan for deploying the companion synchronization bridge")}
                    className="px-3.5 py-1.5 rounded-full bg-[#181426] hover:bg-[#231e36] border border-white/5 text-xs text-slate-300 flex items-center gap-1.5 transition-all"
                  >
                    <span>Make a plan</span>
                    <span>📄</span>
                  </button>
                </div>
              </div>
            ) : (
              /* Active Chat History */
              <div className="max-w-2xl mx-auto w-full space-y-4 my-auto">
                {messages.map((m) => (
                  <div
                    key={m.id}
                    className={`p-4 rounded-2xl text-xs leading-relaxed ${
                      m.role === "user"
                        ? "bg-[#251e3a] text-white ml-auto max-w-[80%]"
                        : "bg-[#161324] border border-white/5 text-slate-200 mr-auto max-w-[85%]"
                    }`}
                  >
                    <div className="font-semibold text-[10px] text-purple-400 mb-1">
                      {m.role === "user" ? "YOU" : "AURA"}
                    </div>
                    <div className="whitespace-pre-wrap">{m.content}</div>

                    {/* Agent Traces & Rich Output Cards */}
                    {m.traces && m.traces.length > 0 && (
                      <div className="mt-3 space-y-2 border-t border-white/10 pt-2">
                        <div className="text-[10px] text-slate-400 font-mono">
                          ⚙ {m.traces.length} autonomous step{m.traces.length > 1 ? "s" : ""} executed
                        </div>
                        {m.traces.map((trace, idx) => {
                          const resultData = trace.tool_result as Record<string, unknown> | null;
                          const innerData = resultData?.data as Record<string, unknown> | null;
                          const isWhatsApp = trace.tool_name === "send_whatsapp_message" || innerData?.whatsapp_app_url;
                          
                          if (isWhatsApp && innerData) {
                            return (
                              <div key={idx} className="p-3 rounded-xl bg-[#0b2b1d]/80 border border-emerald-500/40 text-xs shadow-md">
                                <div className="flex items-center justify-between mb-2">
                                  <div className="flex items-center gap-2 font-semibold text-emerald-400">
                                    <span>📱</span>
                                    <span>WhatsApp Dispatch Ready</span>
                                  </div>
                                  <span className="text-[10px] bg-emerald-950 px-2 py-0.5 rounded text-emerald-300 border border-emerald-500/30">
                                    {String(innerData.recipient_name || "Contact")}
                                  </span>
                                </div>
                                <div className="p-2 rounded bg-black/40 border border-emerald-500/20 text-emerald-100 text-[11px] mb-2.5">
                                  "{String(innerData.message || "")}"
                                </div>
                                <div className="flex flex-wrap gap-2">
                                  <a
                                    href={String(innerData.whatsapp_app_url)}
                                    className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-[11px] font-semibold transition-all inline-flex items-center gap-1.5 shadow-md shadow-emerald-950/60"
                                  >
                                    <span>📱</span>
                                    <span>Open in WhatsApp Phone App</span>
                                  </a>
                                  <a
                                    href={String(innerData.whatsapp_universal_url)}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="px-3 py-1.5 bg-[#173a27] hover:bg-[#1f4a33] text-emerald-200 rounded-lg text-[11px] transition-all"
                                  >
                                    Web / Browser Link
                                  </a>
                                </div>
                              </div>
                            );
                          }
                          return null;
                        })}
                      </div>
                    )}

                    {/* Interactive Human-in-the-Loop Approval Card */}
                    {m.pendingApproval && (
                      <div className="mt-3 p-3.5 rounded-xl bg-purple-950/40 border border-purple-500/40 text-xs shadow-lg">
                        <div className="flex items-center gap-1.5 font-semibold text-purple-300 mb-1.5">
                          <span>🛡️</span>
                          <span>Human-in-the-Loop Authorization Required</span>
                        </div>
                        <p className="text-[11px] text-slate-300 mb-2">
                          Proposed Action: <code className="bg-purple-900/60 px-1.5 py-0.5 rounded text-purple-200 font-mono">{m.pendingApproval.tool_name}</code>
                        </p>
                        {(m.pendingApproval.args || (m.pendingApproval as unknown as { tool_args?: Record<string, unknown> }).tool_args) && (
                          <pre className="p-2 rounded bg-black/50 text-[10px] text-purple-200 font-mono mb-3 overflow-x-auto border border-white/5">
                            {JSON.stringify(m.pendingApproval.args || (m.pendingApproval as unknown as { tool_args?: Record<string, unknown> }).tool_args, null, 2)}
                          </pre>
                        )}
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() =>
                              handleDecision(
                                m.pendingApproval!.approval_id,
                                true,
                                m.pendingApproval!.tool_name,
                                m.pendingApproval!.args || (m.pendingApproval as unknown as { tool_args?: Record<string, unknown> }).tool_args || {}
                              )
                            }
                            className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-[11px] font-semibold transition-all shadow-md shadow-emerald-900/40"
                          >
                            ✓ Authorize & Execute
                          </button>
                          <button
                            onClick={() => handleDecision(m.pendingApproval!.approval_id, false)}
                            className="px-3 py-1.5 bg-rose-900/60 hover:bg-rose-800 text-rose-200 rounded-lg text-[11px] font-semibold transition-all"
                          >
                            ✕ Cancel
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                ))}

                {isLoading && (
                  <div className="p-3 rounded-xl bg-[#161324] border border-white/5 text-xs text-purple-400 flex items-center gap-2 max-w-xs">
                    <span className="w-3 h-3 border-2 border-purple-400 border-t-transparent rounded-full animate-spin" />
                    <span>Reasoning...</span>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>
            )}
          </div>

          {/* Bottom Area: Zyricon Floating Purple-Bordered Input Bar & 3 Feature Cards */}
          <div className="p-6 max-w-3xl mx-auto w-full">
            
            {/* Center Input Box - Zyricon exact design */}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSend();
              }}
              className="rounded-2xl border border-purple-500/40 bg-[#151224] p-3 shadow-xl mb-6 relative"
            >
              <div className="flex items-center gap-2 px-2 pb-2">
                <span className="text-purple-400 text-sm select-none">✦</span>
                <input
                  type="text"
                  placeholder="Ask Anything..."
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  className="bg-transparent text-xs text-white placeholder-slate-500 focus:outline-none w-full"
                />
              </div>

              {/* Bottom toolbar inside input box */}
              <div className="flex items-center justify-between pt-2 border-t border-white/5 px-2 text-xs text-slate-400">
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => alert("Upload file to RAG context")}
                    className="hover:text-slate-200 flex items-center gap-1 transition-colors"
                  >
                    <span>📎</span> <span>Attach</span>
                  </button>
                  <Link href="/settings" className="hover:text-slate-200 flex items-center gap-1 transition-colors">
                    <span>⚙</span> <span>Settings</span>
                  </Link>
                  <button
                    type="button"
                    onClick={() => alert("Agent execution options")}
                    className="hover:text-slate-200 flex items-center gap-1 transition-colors"
                  >
                    <span>⚑</span> <span>Options</span>
                  </button>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => alert("Microphone voice input ready")}
                    className="p-1 text-slate-400 hover:text-white"
                  >
                    🎙️
                  </button>
                  <button
                    type="submit"
                    disabled={!input.trim() || isLoading}
                    className="w-7 h-7 rounded-full bg-[#7c3aed] hover:bg-[#8b5cf6] text-white flex items-center justify-center text-xs font-bold transition-all shadow-md shadow-purple-900/50 disabled:opacity-40"
                  >
                    ↑
                  </button>
                </div>
              </div>
            </form>

            {/* Bottom 3 Feature Cards (matching Zyricon bottom row) */}
            {messages.length === 0 && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {/* Card 1 */}
                <div className="p-3.5 rounded-2xl bg-[#131021] border border-white/5 flex flex-col justify-between hover:border-purple-500/30 transition-all">
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-base">🖼️</span>
                    <button
                      onClick={() => handleSend("Generate a high resolution hero graphic")}
                      className="text-[10px] font-medium bg-[#1e1934] text-slate-300 px-2 py-0.5 rounded-full hover:bg-purple-900/40"
                    >
                      Create Image
                    </button>
                  </div>
                  <h4 className="text-xs font-semibold text-white">Image Generator</h4>
                  <p className="text-[10px] text-slate-400 leading-tight mt-0.5">
                    Create high-quality images instantly from text.
                  </p>
                </div>

                {/* Card 2 */}
                <div className="p-3.5 rounded-2xl bg-[#131021] border border-white/5 flex flex-col justify-between hover:border-purple-500/30 transition-all">
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-base">📄</span>
                    <button
                      onClick={() => handleSend("Generate an AI presentation summary")}
                      className="text-[10px] font-medium bg-[#1e1934] text-slate-300 px-2 py-0.5 rounded-full hover:bg-purple-900/40"
                    >
                      Make Slides
                    </button>
                  </div>
                  <h4 className="text-xs font-semibold text-white">AI Presentation</h4>
                  <p className="text-[10px] text-slate-400 leading-tight mt-0.5">
                    Turn ideas into engaging, professional presentations.
                  </p>
                </div>

                {/* Card 3 */}
                <div className="p-3.5 rounded-2xl bg-[#131021] border border-white/5 flex flex-col justify-between hover:border-purple-500/30 transition-all">
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-base">⚡</span>
                    <button
                      onClick={() => handleSend("Execute an automated codebase diagnostic")}
                      className="text-[10px] font-medium bg-[#1e1934] text-slate-300 px-2 py-0.5 rounded-full hover:bg-purple-900/40"
                    >
                      Generate Code
                    </button>
                  </div>
                  <h4 className="text-xs font-semibold text-white">Dev Assistant</h4>
                  <p className="text-[10px] text-slate-400 leading-tight mt-0.5">
                    Generate clean, production ready code in seconds.
                  </p>
                </div>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
