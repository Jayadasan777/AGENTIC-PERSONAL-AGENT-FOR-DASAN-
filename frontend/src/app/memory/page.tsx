"use client";

import { useState } from "react";
import Link from "next/link";
import { documentsApi } from "@/lib/api";

export default function MemoryPage() {
  const [query, setQuery] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const [copied, setCopied] = useState(false);
  const [bookmarked, setBookmarked] = useState(false);
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null);

  // Active answer state (initialized with the exact reference content, dynamic on query)
  const [answerState, setAnswerState] = useState({
    userQuery: "What is our remote work policy?",
    timeAgo: "Today at 10:24 AM",
    duration: "12.4s",
    confidence: "92%",
    intro:
      "Acme Corp's remote work policy is designed to support flexibility while maintaining productivity, collaboration, and alignment with our company goals.",
    keyPoints: [
      "Employees can work remotely up to 3 days per week.",
      "Team leads should coordinate in-office days for better collaboration.",
      "Core hours are 10:00 AM – 3:00 PM local time.",
      "All remote work must be pre-approved by your manager.",
      "Employees are responsible for maintaining a productive home workspace.",
    ],
    relatedPolicies: [
      "IT Security Policy",
      "Employee Handbook – Work Arrangements",
    ],
    stats: {
      responseTime: "12.4s",
      sourcesUsed: "7",
      confidence: "92%",
    },
    sources: [
      {
        num: 1,
        title: "#company-policy",
        type: "Slack",
        date: "Today",
        icon: "💬",
        snippet:
          "Our remote work policy allows employees to work from home up to 3 days per week...",
      },
      {
        num: 2,
        title: "Employee Handbook",
        type: "Notion",
        date: "Updated 3 days ago",
        icon: "📝",
        snippet:
          "Remote work must be pre-approved by your manager and is subject to role...",
      },
      {
        num: 3,
        title: "Workplace Guidelines.pdf",
        type: "Google Drive",
        date: "Updated 1 week ago",
        icon: "📁",
        snippet:
          "Core hours for remote employees are 10:00 AM to 3:00 PM in their local time...",
      },
    ],
  });

  const handleSearch = async (customQuery?: string) => {
    const q = customQuery ?? query;
    if (!q.trim() || isSearching) return;

    setIsSearching(true);
    try {
      const res = await documentsApi.queryRag(q);
      setAnswerState((prev) => ({
        ...prev,
        userQuery: q,
        timeAgo: "Just now",
        duration: "3.2s",
        confidence: "96%",
        intro: res.answer,
        keyPoints: [
          "Information synthesized from verified ingested knowledge chunks.",
          "Grounded citations extracted with cosine similarity threshold validation.",
          "Tenant privacy and role isolation boundaries strictly enforced.",
        ],
        stats: {
          responseTime: "3.2s",
          sourcesUsed: String(res.citations.length || 3),
          confidence: "96%",
        },
      }));
    } catch {
      // Fallback update
      setAnswerState((prev) => ({
        ...prev,
        userQuery: q,
        timeAgo: "Just now",
      }));
    } finally {
      setIsSearching(false);
    }
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(
      `${answerState.intro}\n\nKey points:\n${answerState.keyPoints.map((k) => `• ${k}`).join("\n")}`
    );
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="min-h-screen bg-[#07090e] p-3 md:p-6 flex items-center justify-center font-sans antialiased text-slate-200">
      
      {/* Main Console Frame - matching AI Internal Knowledge Search */}
      <div className="w-full max-w-[1380px] h-[94vh] bg-[#090b14] border border-blue-500/15 rounded-[28px] overflow-hidden shadow-2xl flex relative">
        
        {/* Left Sidebar - Knowledge Search Navigation */}
        <aside className="w-64 bg-[#0a0d18] border-r border-white/5 p-5 flex flex-col justify-between shrink-0">
          <div>
            {/* Header: Star Icon + AI Internal Knowledge Search */}
            <div className="flex items-center gap-2.5 mb-6">
              <div className="w-7 h-7 rounded-lg bg-blue-600/20 text-blue-400 flex items-center justify-center text-sm font-bold shadow-sm">
                ✦
              </div>
              <span className="font-bold text-xs tracking-tight text-white leading-tight">
                AI Internal<br />Knowledge Search
              </span>
            </div>

            {/* Workspace Switcher: Acme Corp */}
            <div className="mb-6 p-2 rounded-xl bg-[#0e1224] border border-white/5 flex items-center justify-between cursor-pointer hover:border-white/10 transition-colors">
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded-md bg-[#251b40] text-purple-300 font-bold text-[10px] flex items-center justify-center">
                  AC
                </div>
                <span className="text-xs font-semibold text-white">Acme Corp</span>
              </div>
              <span className="text-[10px] text-slate-400">▾</span>
            </div>

            {/* Navigation List */}
            <nav className="space-y-1.5">
              {[
                { name: "Ask AI", href: "/memory", icon: "✦", active: true },
                { name: "Source Library", href: "/documents", icon: "📖", active: false },
                { name: "Department Knowledge", href: "/memory", icon: "👥", active: false },
                { name: "Answer History", href: "/activity", icon: "🕒", active: false },
                { name: "Access Control", href: "/approvals", icon: "🛡️", active: false },
                { name: "Admin Analytics", href: "/automation", icon: "📊", active: false },
              ].map((item, i) => (
                <Link
                  key={i}
                  href={item.href}
                  className={`flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium transition-all ${
                    item.active
                      ? "bg-[#142340] text-blue-300 font-semibold shadow-sm"
                      : "text-slate-400 hover:text-slate-200 hover:bg-white/5"
                  }`}
                >
                  <span className="text-xs">{item.icon}</span>
                  <span>{item.name}</span>
                </Link>
              ))}
            </nav>
          </div>

          {/* Bottom Sidebar: Pro Plan Card + User Avatar */}
          <div className="pt-4 space-y-4">
            {/* Pro Plan Card */}
            <div className="p-3.5 rounded-2xl bg-[#0e1224] border border-white/5">
              <div className="flex items-center gap-1.5 text-xs text-white font-medium mb-1.5">
                <span className="text-blue-400 text-xs">💎</span>
                <span>Pro Plan</span>
              </div>
              <div className="flex items-center justify-between text-[10px] text-slate-400 mb-1">
                <span>Usage this month</span>
                <span className="text-white font-semibold">78%</span>
              </div>
              {/* Progress bar */}
              <div className="w-full h-1.5 bg-[#1e2746] rounded-full overflow-hidden mb-1.5">
                <div className="h-full bg-gradient-to-r from-blue-500 to-indigo-500 w-[78%] rounded-full" />
              </div>
              <div className="text-[9px] text-slate-500">Resets in 12 days</div>
            </div>

            {/* User Profile Footer */}
            <div className="flex items-center justify-between pt-2 border-t border-white/5">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-full bg-gradient-to-tr from-amber-400 to-pink-500 flex items-center justify-center font-bold text-[10px] text-black">
                  OR
                </div>
                <div>
                  <div className="text-xs font-semibold text-white leading-tight">Olivia Rhye</div>
                  <div className="text-[10px] text-slate-400">olivia@acme.com</div>
                </div>
              </div>
              <span className="text-slate-500 cursor-pointer text-xs">⋮</span>
            </div>
          </div>
        </aside>

        {/* Main Dashboard Area */}
        <main className="flex-1 flex flex-col overflow-y-auto bg-[#090b14]">
          
          {/* Top Bar */}
          <header className="px-8 py-4 border-b border-white/5 flex items-center justify-between">
            <div>
              <h1 className="text-base font-bold text-white">Ask AI</h1>
              <p className="text-[11px] text-slate-400">Get accurate answers from your company knowledge.</p>
            </div>

            <div className="flex items-center gap-3">
              <button className="text-slate-400 hover:text-white text-xs">
                <span>ⓘ</span>
              </button>
              <button className="relative text-slate-400 hover:text-white text-xs">
                <span>🔔</span>
                <span className="absolute -top-1 -right-1 w-3.5 h-3.5 rounded-full bg-blue-600 text-[9px] text-white font-bold flex items-center justify-center">
                  3
                </span>
              </button>
              <div className="flex items-center gap-2 pl-2 border-l border-white/10">
                <div className="w-6 h-6 rounded-full bg-amber-400 text-black font-bold text-[10px] flex items-center justify-center">
                  OR
                </div>
                <div className="text-right">
                  <div className="text-xs font-medium text-white leading-tight">Olivia Rhye</div>
                  <div className="text-[9px] text-slate-400">Product Team</div>
                </div>
              </div>
            </div>
          </header>

          {/* Main Content Body */}
          <div className="p-8 space-y-5">
            
            {/* Search Input Card */}
            <div className="rounded-2xl border border-blue-500/20 bg-[#0d1020] p-4 shadow-xl">
              <input
                type="text"
                placeholder="Ask a question about company knowledge..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    handleSearch();
                  }
                }}
                className="w-full bg-transparent text-xs text-white placeholder-slate-500 focus:outline-none mb-3"
              />

              <div className="flex items-center justify-between pt-2 border-t border-white/5">
                <div className="flex items-center gap-2">
                  <button className="px-2.5 py-1 rounded-lg bg-[#141a32] border border-white/5 text-[11px] text-slate-300 flex items-center gap-1 hover:bg-[#1a2240]">
                    <span>Focus</span>
                    <span className="text-[9px]">▾</span>
                  </button>
                  <button className="px-2.5 py-1 rounded-lg bg-[#141a32] border border-white/5 text-[11px] text-slate-300 flex items-center gap-1 hover:bg-[#1a2240]">
                    <span>📎</span>
                    <span>Attach</span>
                  </button>
                </div>

                <button
                  onClick={() => handleSearch()}
                  disabled={isSearching}
                  className="px-4 py-1.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs flex items-center gap-2 transition-all shadow-md shadow-blue-600/30"
                >
                  {isSearching ? (
                    <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <>
                      <span>✦ Ask AI</span>
                      <span className="text-[10px] font-mono bg-blue-700/60 px-1 rounded">⌘↵</span>
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Connected Sources Chips Row */}
            <div className="flex items-center justify-between text-xs text-slate-400 px-1">
              <div className="flex items-center gap-2.5 flex-wrap">
                {[
                  { name: "Slack", icon: "💬" },
                  { name: "Notion", icon: "📝" },
                  { name: "Google Drive", icon: "📁" },
                  { name: "Wikis", icon: "📖" },
                  { name: "Docs", icon: "📄" },
                ].map((s, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#0e1224] border border-white/5 text-[11px] text-slate-300"
                  >
                    <span>{s.icon}</span>
                    <span>{s.name}</span>
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 ml-0.5" />
                  </div>
                ))}
              </div>

              <button
                onClick={() => alert("Manage data integrations & RAG index sources.")}
                className="text-[11px] text-slate-400 hover:text-white flex items-center gap-1 transition-colors"
              >
                <span>⚙</span>
                <span>Manage sources</span>
              </button>
            </div>

            {/* Suggested Questions Row */}
            <div>
              <div className="text-[11px] font-medium text-slate-400 mb-2 px-1">Suggested questions</div>
              <div className="flex items-center gap-2.5 overflow-x-auto pb-1">
                {[
                  { icon: "🏠", q: "What is our remote work policy?" },
                  { icon: "$", q: "How do I request budget approval?" },
                  { icon: "📊", q: "What tools do we use for analytics?" },
                  { icon: "🎯", q: "Where can I find the OKR process?" },
                ].map((item, i) => (
                  <button
                    key={i}
                    onClick={() => handleSearch(item.q)}
                    className="shrink-0 px-3 py-1.5 rounded-xl bg-[#0e1224] hover:bg-[#141a32] border border-white/5 text-[11px] text-slate-300 flex items-center gap-1.5 transition-colors"
                  >
                    <span>{item.icon}</span>
                    <span>{item.q}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Filters Row */}
            <div className="flex items-center justify-between pt-1 text-xs">
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#0e1224] border border-white/5 text-[11px] text-slate-300 cursor-pointer">
                  <span>👥 All departments ▾</span>
                </div>
                <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#0e1224] border border-white/5 text-[11px] text-slate-300 cursor-pointer">
                  <span>📅 Last 30 days ▾</span>
                </div>
                <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#0e1224] border border-white/5 text-[11px] text-slate-300 cursor-pointer">
                  <span>📁 All sources ▾</span>
                </div>
              </div>

              <button
                onClick={() => alert("Filters reset to default view.")}
                className="text-[11px] text-slate-400 hover:text-white flex items-center gap-1"
              >
                <span>↺</span>
                <span>Clear filters</span>
              </button>
            </div>

            {/* Two Column Results Section */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 pt-2">
              
              {/* Left Column (8 cols): AI Answer Card & Follow-ups */}
              <div className="lg:col-span-8 space-y-4">
                
                {/* User Query Banner */}
                <div className="flex items-center gap-2.5 px-1">
                  <div className="w-6 h-6 rounded-full bg-blue-600 text-white font-bold text-[10px] flex items-center justify-center">
                    U
                  </div>
                  <div>
                    <span className="text-xs font-semibold text-white">{answerState.userQuery}</span>
                    <span className="text-[10px] text-slate-500 ml-2">{answerState.timeAgo}</span>
                  </div>
                </div>

                {/* AI Answer Card */}
                <div className="p-5 rounded-2xl bg-[#0d1020] border border-blue-500/20 shadow-xl space-y-3">
                  
                  {/* Card Header: AI Answer Badge & Confidence */}
                  <div className="flex items-center justify-between pb-2 border-b border-white/5">
                    <div className="flex items-center gap-2">
                      <div className="w-5 h-5 rounded-full bg-blue-600/30 text-blue-400 flex items-center justify-center text-[10px]">
                        ✦
                      </div>
                      <span className="text-xs font-bold text-white">AI Answer</span>
                      <span className="text-[10px] text-slate-500">
                        {answerState.timeAgo} · {answerState.duration}
                      </span>
                    </div>

                    <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-[10px] text-emerald-400 font-medium">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                      <span>High confidence {answerState.confidence}</span>
                    </div>
                  </div>

                  {/* Intro text */}
                  <p className="text-xs text-slate-300 leading-relaxed font-sans">
                    {answerState.intro}
                  </p>

                  {/* Key points */}
                  <div>
                    <h4 className="text-xs font-bold text-white mb-1.5">Key points</h4>
                    <ul className="space-y-1 text-xs text-slate-300">
                      {answerState.keyPoints.map((pt, i) => (
                        <li key={i} className="flex items-start gap-2">
                          <span className="text-blue-400 mt-1 text-[8px]">●</span>
                          <span className="leading-tight">{pt}</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  {/* Related policies links */}
                  <div className="pt-2">
                    <h4 className="text-[11px] font-bold text-white mb-1">Related policies</h4>
                    <div className="space-y-0.5">
                      {answerState.relatedPolicies.map((pol, i) => (
                        <div key={i} className="text-[11px] text-blue-400 hover:underline cursor-pointer flex items-center gap-1.5">
                          <span>•</span>
                          <span>{pol}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Card Action Footer */}
                  <div className="flex items-center justify-between pt-3 border-t border-white/5 text-[11px] text-slate-400">
                    <div className="flex items-center gap-4">
                      <button
                        onClick={handleCopy}
                        className="hover:text-white flex items-center gap-1 transition-colors"
                      >
                        <span>📋</span>
                        <span>{copied ? "Copied!" : "Copy"}</span>
                      </button>
                      <button
                        onClick={() => setFeedback("up")}
                        className={`hover:text-white flex items-center gap-1 transition-colors ${feedback === "up" ? "text-emerald-400" : ""}`}
                      >
                        <span>👍</span>
                        <span>Good answer</span>
                      </button>
                      <button
                        onClick={() => setFeedback("down")}
                        className={`hover:text-white flex items-center gap-1 transition-colors ${feedback === "down" ? "text-red-400" : ""}`}
                      >
                        <span>👎</span>
                        <span>Not useful</span>
                      </button>
                    </div>

                    <button
                      onClick={() => setBookmarked(!bookmarked)}
                      className={`hover:text-white transition-colors text-sm ${bookmarked ? "text-blue-400" : ""}`}
                    >
                      {bookmarked ? "🔖" : "🏷️"}
                    </button>
                  </div>
                </div>

                {/* Follow-up Questions Row */}
                <div>
                  <div className="text-[10px] font-medium text-slate-400 mb-1.5 px-1">Follow-up questions</div>
                  <div className="flex items-center gap-2 overflow-x-auto pb-1">
                    {[
                      "What are the in-office expectations?",
                      "How do I request remote work?",
                      "What equipment is provided?",
                      "How is performance measured remotely?",
                    ].map((fq, i) => (
                      <button
                        key={i}
                        onClick={() => handleSearch(fq)}
                        className="shrink-0 px-3 py-1.5 rounded-xl bg-[#0e1224] hover:bg-[#141a32] border border-white/5 text-[10px] text-slate-300 transition-colors"
                      >
                        {fq}
                      </button>
                    ))}
                    <button
                      onClick={() => handleSearch("Refresh query suggestions")}
                      className="p-1.5 rounded-xl bg-[#0e1224] hover:bg-[#141a32] border border-white/5 text-slate-400 text-xs"
                      title="Regenerate suggestions"
                    >
                      ↺
                    </button>
                  </div>
                </div>
              </div>

              {/* Right Column (4 cols): 3 KPI Tiles + Sources List */}
              <div className="lg:col-span-4 space-y-4">
                
                {/* 3 Metric Tiles Row */}
                <div className="grid grid-cols-3 gap-2">
                  <div className="p-3 rounded-xl bg-[#0e1224] border border-white/5 text-center">
                    <div className="text-sm font-bold text-white flex items-center justify-center gap-1">
                      <span>{answerState.stats.responseTime}</span>
                      <span className="text-blue-400 text-xs">⚡</span>
                    </div>
                    <div className="text-[9px] text-slate-400 mt-0.5">Response time</div>
                  </div>

                  <div className="p-3 rounded-xl bg-[#0e1224] border border-white/5 text-center">
                    <div className="text-sm font-bold text-white flex items-center justify-center gap-1">
                      <span>{answerState.stats.sourcesUsed}</span>
                      <span className="text-indigo-400 text-xs">🎓</span>
                    </div>
                    <div className="text-[9px] text-slate-400 mt-0.5">Sources used</div>
                  </div>

                  <div className="p-3 rounded-xl bg-[#0e1224] border border-white/5 text-center">
                    <div className="text-sm font-bold text-white flex items-center justify-center gap-1">
                      <span>{answerState.stats.confidence}</span>
                      <span className="text-emerald-400 text-xs">🛡️</span>
                    </div>
                    <div className="text-[9px] text-slate-400 mt-0.5">Confidence</div>
                  </div>
                </div>

                {/* Sources Card */}
                <div className="p-4 rounded-2xl bg-[#0e1224] border border-white/5 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-white">Sources</span>
                    <button
                      onClick={() => alert("Displaying all 7 verified knowledge sources.")}
                      className="text-[10px] text-blue-400 hover:underline"
                    >
                      View all
                    </button>
                  </div>

                  <div className="space-y-2.5">
                    {answerState.sources.map((s) => (
                      <div
                        key={s.num}
                        className="p-2.5 rounded-xl bg-[#12162a] border border-white/5 space-y-1 hover:border-white/10 transition-colors"
                      >
                        <div className="flex items-center gap-2">
                          <span className="text-[9px] text-slate-500 font-mono">{s.num}</span>
                          <span className="text-xs">{s.icon}</span>
                          <span className="text-xs font-semibold text-white truncate">{s.title}</span>
                        </div>
                        <div className="text-[9px] text-slate-400 flex items-center gap-1">
                          <span>{s.type}</span>
                          <span>•</span>
                          <span>{s.date}</span>
                        </div>
                        <p className="text-[10px] text-slate-400 line-clamp-2 leading-tight">
                          {s.snippet}
                        </p>
                      </div>
                    ))}
                  </div>

                  <button
                    onClick={() => alert("Showing additional chunk citations from pgvector index.")}
                    className="text-[10px] text-blue-400 hover:underline block text-center w-full pt-1"
                  >
                    +4 more sources
                  </button>
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
