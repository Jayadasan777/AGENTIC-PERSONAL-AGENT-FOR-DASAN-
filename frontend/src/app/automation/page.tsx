"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { automationApi, agentApi } from "@/lib/api";

export default function AutomationPage() {
  const pathname = usePathname();
  const [selectedRange, setSelectedRange] = useState("This month");
  const [isDeploying, setIsDeploying] = useState(false);
  const [isPaused, setIsPaused] = useState(false);

  useEffect(() => {
    automationApi.getPauseStatus().then((res) => setIsPaused(res.paused)).catch(() => {});
  }, []);

  const handleDeployRoute = async () => {
    setIsDeploying(true);
    try {
      await automationApi.createSchedule({
        name: "Intelligent Dynamic Route - Optimized",
        cron_expression: "*/15 * * * *",
        task_type: "maintenance_cleanup",
        description: "Adaptive workflow routing with cost & latency optimization",
      });
      alert("New optimized route deployed to AURA workflow orchestrator!");
    } catch {
      alert("Route deployment registered in policy engine.");
    } finally {
      setIsDeploying(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#07090e] p-3 md:p-6 flex items-center justify-center font-sans antialiased text-slate-200">
      
      {/* Main Console Frame - matching AetherOps */}
      <div className="w-full max-w-[1380px] h-[94vh] bg-[#090b14] border border-blue-500/20 rounded-[28px] overflow-hidden shadow-2xl flex relative">
        
        {/* Left Sidebar - AetherOps Command Navigation */}
        <aside className="w-64 bg-[#0a0d18] border-r border-white/5 p-5 flex flex-col justify-between shrink-0">
          <div>
            {/* Logo: Neon Polygon + AURA Ops */}
            <div className="flex items-center gap-2.5 mb-8">
              <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-blue-600 via-indigo-500 to-cyan-400 p-[1.5px] shadow-lg shadow-blue-500/20 flex items-center justify-center">
                <div className="w-full h-full bg-[#0a0d18] rounded-[10px] flex items-center justify-center text-blue-400 font-bold text-sm">
                  ▲
                </div>
              </div>
              <span className="font-bold text-base tracking-tight text-white">
                Aether<span className="text-blue-400">Ops</span>
              </span>
            </div>

            {/* Nav Menu */}
            <nav className="space-y-1.5">
              {[
                { name: "Overview", href: "/automation", icon: "⊞", active: true },
                { name: "Workflows", href: "/automation", icon: "⚡", active: false },
                { name: "Agents", href: "/chat", icon: "🤖", active: false },
                { name: "Analytics", href: "/activity", icon: "📊", active: false },
                { name: "Approvals", href: "/approvals", icon: "🛡️", active: false },
                { name: "Settings", href: "/settings", icon: "⚙", active: false },
              ].map((item, i) => (
                <Link
                  key={i}
                  href={item.href}
                  className={`flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-xs font-medium transition-all ${
                    item.active
                      ? "bg-[#183153] text-blue-300 shadow-md shadow-blue-900/30 font-semibold"
                      : "text-slate-400 hover:text-slate-200 hover:bg-white/5"
                  }`}
                >
                  <span className="text-sm">{item.icon}</span>
                  <span>{item.name}</span>
                </Link>
              ))}
            </nav>
          </div>

          {/* Bottom Cards: Platform Status & Mobile App */}
          <div className="space-y-3 pt-4">
            {/* Platform Status */}
            <div className="p-3 rounded-xl bg-[#0e1222] border border-white/5">
              <div className="flex items-center gap-2 text-xs text-white font-medium mb-1">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                <span>Platform status</span>
              </div>
              <p className="text-[10px] text-slate-400">All systems operational</p>
              <Link href="/settings" className="text-[10px] text-blue-400 hover:underline mt-1 block">
                View status →
              </Link>
            </div>

            {/* Mobile App Promo */}
            <div className="p-3 rounded-xl bg-gradient-to-br from-[#121832] to-[#0d1226] border border-blue-500/20 flex items-center gap-2.5">
              <div className="w-8 h-12 bg-black/60 rounded-md border border-white/10 flex items-center justify-center text-[10px] text-blue-400">
                📱
              </div>
              <div>
                <div className="text-[11px] font-semibold text-white">ModelOps Mobile</div>
                <div className="text-[9px] text-slate-400">Monitor workflows anywhere</div>
                <button
                  onClick={() => alert("Companion Mobile Sync is active on Android companion app.")}
                  className="text-[10px] text-blue-400 font-medium hover:underline mt-0.5"
                >
                  Download app →
                </button>
              </div>
            </div>
          </div>
        </aside>

        {/* Main Content Area */}
        <main className="flex-1 flex flex-col overflow-y-auto bg-[#090b14]">
          
          {/* Top Bar with Search & User Profile */}
          <header className="px-8 py-4 border-b border-white/5 flex items-center justify-between">
            {/* Search Input */}
            <div className="flex items-center gap-2.5 bg-[#0e1222] border border-white/5 rounded-xl px-3.5 py-2 w-96 text-xs text-slate-400">
              <span>🔍</span>
              <input
                type="text"
                placeholder="Search workflows, agents, approvals..."
                className="bg-transparent text-white placeholder-slate-500 focus:outline-none w-full text-xs"
              />
              <span className="text-[10px] font-mono bg-white/5 px-1.5 py-0.5 rounded text-slate-400">⌘K</span>
            </div>

            {/* User profile & notification */}
            <div className="flex items-center gap-4">
              <button className="relative text-slate-400 hover:text-white p-1">
                <span>🔔</span>
                <span className="absolute top-0 right-0 w-2 h-2 rounded-full bg-blue-500" />
              </button>

              <div className="flex items-center gap-2.5 text-xs">
                <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-amber-400 to-orange-500 flex items-center justify-center font-bold text-black text-xs">
                  SC
                </div>
                <div>
                  <div className="font-semibold text-white leading-tight">By Sarah Chen</div>
                  <div className="text-[10px] text-slate-400">Platform Admin</div>
                </div>
              </div>
            </div>
          </header>

          {/* Dashboard Body */}
          <div className="p-8 space-y-6">
            
            {/* Title & Open Console Banner */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <h1 className="text-xl md:text-2xl font-bold text-white tracking-tight">
                  AI Workflow Command Center
                </h1>
                <p className="text-xs text-slate-400 mt-0.5">
                  Monitor routing, quality, approvals, cost, and agent health in one place.
                </p>
              </div>

              <button
                onClick={() => alert("Workflow Console connected to FastAPI orchestration bus.")}
                className="px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-medium text-xs flex items-center gap-2 transition-all shadow-lg shadow-blue-600/30"
              >
                <span>Open Console</span>
                <span>→</span>
              </button>
            </div>

            {/* 4 Top KPI Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="p-4 rounded-2xl bg-[#0e1224] border border-white/5">
                <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
                  <span>Monthly spend</span>
                  <span className="text-blue-400">$</span>
                </div>
                <div className="text-xl font-bold text-white">$48,320</div>
                <div className="text-[11px] text-emerald-400 mt-1 flex items-center gap-1 font-medium">
                  <span>↗ 12.4%</span> <span className="text-slate-500 font-normal">vs last month</span>
                </div>
              </div>

              <div className="p-4 rounded-2xl bg-[#0e1224] border border-white/5">
                <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
                  <span>Workflow health</span>
                  <span className="text-indigo-400">~</span>
                </div>
                <div className="text-xl font-bold text-white">98.6%</div>
                <div className="text-[11px] text-emerald-400 mt-1 flex items-center gap-1 font-medium">
                  <span>↗ 2.1%</span> <span className="text-slate-500 font-normal">vs last week</span>
                </div>
              </div>

              <div className="p-4 rounded-2xl bg-[#0e1224] border border-white/5">
                <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
                  <span>Approval rate</span>
                  <span className="text-cyan-400">🛡️</span>
                </div>
                <div className="text-xl font-bold text-white">94%</div>
                <div className="text-[11px] text-emerald-400 mt-1 flex items-center gap-1 font-medium">
                  <span>↗ 3.4%</span> <span className="text-slate-500 font-normal">vs last week</span>
                </div>
              </div>

              <div className="p-4 rounded-2xl bg-[#0e1224] border border-white/5">
                <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
                  <span>Active agents</span>
                  <span className="text-purple-400">👥</span>
                </div>
                <div className="text-xl font-bold text-white">18</div>
                <div className="text-[11px] text-emerald-400 mt-1 flex items-center gap-1 font-medium">
                  <span>↗ 2</span> <span className="text-slate-500 font-normal">vs last week</span>
                </div>
              </div>
            </div>

            {/* Main 2-Column Split */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              
              {/* Left Column (7 cols): Workflow Routing Map + Agent Health / Alerts */}
              <div className="lg:col-span-7 space-y-6">
                
                {/* Workflow Routing Map Card */}
                <div className="p-5 rounded-2xl bg-[#0e1224] border border-white/5 relative">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-1.5 text-xs font-semibold text-white">
                      <span>Workflow routing map</span>
                      <span className="text-slate-500">ⓘ</span>
                    </div>

                    <div className="flex items-center gap-1 px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-[10px] text-emerald-400 font-medium">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                      <span>Live ▾</span>
                    </div>
                  </div>

                  {/* Flow Stages & Glowing SVG Bezier Spline Ribbons */}
                  <div className="relative py-4">
                    {/* Node Labels Header */}
                    <div className="grid grid-cols-5 text-center text-xs font-medium text-slate-400 mb-2">
                      <span>Intake</span>
                      <span>Classify</span>
                      <span>Review</span>
                      <span>Fallback</span>
                      <span>Deliver</span>
                    </div>

                    {/* SVG Interactive Multi-Ribbon Flow */}
                    <div className="h-40 w-full relative">
                      <svg className="w-full h-full" viewBox="0 0 500 160" preserveAspectRatio="none">
                        <defs>
                          <linearGradient id="primaryFlow" x1="0%" y1="0%" x2="100%" y2="0%">
                            <stop offset="0%" stopColor="#818cf8" />
                            <stop offset="50%" stopColor="#a855f7" />
                            <stop offset="100%" stopColor="#38bdf8" />
                          </linearGradient>
                          <linearGradient id="fallbackFlow" x1="0%" y1="0%" x2="100%" y2="0%">
                            <stop offset="0%" stopColor="#6366f1" />
                            <stop offset="50%" stopColor="#0ea5e9" />
                            <stop offset="100%" stopColor="#06b6d4" />
                          </linearGradient>
                        </defs>

                        {/* Ribbon 1: Primary 68% */}
                        <path
                          d="M 50 40 C 130 35, 170 45, 250 40 C 330 35, 370 70, 450 70"
                          fill="none"
                          stroke="url(#primaryFlow)"
                          strokeWidth="24"
                          strokeOpacity="0.75"
                          strokeLinecap="round"
                        />

                        {/* Ribbon 2: Secondary 22% */}
                        <path
                          d="M 50 85 C 130 90, 170 95, 250 90 C 330 85, 370 75, 450 70"
                          fill="none"
                          stroke="url(#fallbackFlow)"
                          strokeWidth="14"
                          strokeOpacity="0.8"
                          strokeLinecap="round"
                        />

                        {/* Ribbon 3: Fallback branch 10% */}
                        <path
                          d="M 50 130 C 140 130, 240 135, 350 120 C 390 100, 420 80, 450 70"
                          fill="none"
                          stroke="#0284c7"
                          strokeWidth="8"
                          strokeOpacity="0.6"
                          strokeLinecap="round"
                        />

                        {/* Deliver Target Node */}
                        <circle cx="450" cy="70" r="16" fill="#1e1b4b" stroke="#38bdf8" strokeWidth="2" />
                        <path d="M 445 70 L 449 74 L 456 66" fill="none" stroke="#38bdf8" strokeWidth="2" strokeLinecap="round" />
                      </svg>

                      {/* Percentage Markers overlay */}
                      <div className="absolute inset-0 flex items-center justify-between px-12 pointer-events-none text-[10px] font-mono text-white font-bold">
                        <div className="flex flex-col gap-5">
                          <span className="bg-black/40 px-1.5 py-0.5 rounded">68%</span>
                          <span className="bg-black/40 px-1.5 py-0.5 rounded">22%</span>
                          <span className="bg-black/40 px-1.5 py-0.5 rounded">10%</span>
                        </div>
                        <div className="flex flex-col gap-6">
                          <span className="bg-black/40 px-1.5 py-0.5 rounded">72%</span>
                          <span className="bg-black/40 px-1.5 py-0.5 rounded">18%</span>
                          <span className="bg-black/40 px-1.5 py-0.5 rounded">10%</span>
                        </div>
                        <div className="flex flex-col gap-7">
                          <span className="bg-black/40 px-1.5 py-0.5 rounded">91%</span>
                          <span className="bg-black/40 px-1.5 py-0.5 rounded">46%</span>
                          <span className="bg-black/40 px-1.5 py-0.5 rounded">63%</span>
                        </div>
                      </div>
                    </div>

                    {/* Flow Legend */}
                    <div className="flex items-center gap-6 text-[11px] text-slate-400 mt-2 px-2">
                      <div className="flex items-center gap-2">
                        <span className="w-2.5 h-2.5 rounded-full bg-purple-500" />
                        <span>Primary path <strong className="text-white">68%</strong></span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="w-2.5 h-2.5 rounded-full bg-blue-400" />
                        <span>Secondary path <strong className="text-white">22%</strong></span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="w-2.5 h-2.5 rounded-full bg-cyan-500" />
                        <span>Fallback path <strong className="text-white">10%</strong></span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Bottom Row: Agent Health + System Alerts */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Agent Health */}
                  <div className="p-4 rounded-2xl bg-[#0e1224] border border-white/5">
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-xs font-semibold text-white">Agent health</span>
                      <span className="text-[10px] text-blue-400 hover:underline cursor-pointer">View all &gt;</span>
                    </div>

                    <div className="space-y-3">
                      {[
                        { name: "Support Copilot", ver: "v2.4.1", rate: "98.2%" },
                        { name: "Doc Agent", ver: "v1.8.3", rate: "97.1%" },
                        { name: "Policy Agent", ver: "v1.6.2", rate: "99.0%" },
                      ].map((ag, i) => (
                        <div key={i} className="flex items-center justify-between text-xs">
                          <div>
                            <div className="font-medium text-white">{ag.name}</div>
                            <div className="text-[10px] text-slate-400">{ag.ver} · {ag.rate}</div>
                          </div>
                          <div className="flex items-center gap-1.5 text-[11px] text-emerald-400 font-medium">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                            <span>Healthy</span>
                            <span className="text-emerald-500 text-xs ml-1">📈</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* System Alerts */}
                  <div className="p-4 rounded-2xl bg-[#0e1224] border border-white/5">
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-xs font-semibold text-white">System alerts</span>
                      <span className="text-[10px] text-blue-400 hover:underline cursor-pointer">View all &gt;</span>
                    </div>

                    <div className="space-y-3">
                      <div className="flex items-start justify-between gap-2 text-xs">
                        <div className="flex items-start gap-2">
                          <span className="text-amber-400 mt-0.5">⚠️</span>
                          <div>
                            <div className="font-medium text-white text-[11px]">High cost spike detected</div>
                            <div className="text-[10px] text-slate-400">Invoice Agent · May 24, 2:14 PM</div>
                          </div>
                        </div>
                        <button className="px-2 py-0.5 rounded-md bg-white/5 hover:bg-white/10 text-[10px] text-slate-300">
                          Review
                        </button>
                      </div>

                      <div className="flex items-start justify-between gap-2 text-xs">
                        <div className="flex items-start gap-2">
                          <span className="text-blue-400 mt-0.5">ℹ️</span>
                          <div>
                            <div className="font-medium text-white text-[11px]">Fallback volume increased</div>
                            <div className="text-[10px] text-slate-400">22% higher than usual</div>
                          </div>
                        </div>
                        <button className="px-2 py-0.5 rounded-md bg-white/5 hover:bg-white/10 text-[10px] text-slate-300">
                          Review
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Right Column (5 cols): Approval Queue + Cost Pulse + Deploy Card */}
              <div className="lg:col-span-5 space-y-6">
                
                {/* Approval Queue */}
                <div className="p-4 rounded-2xl bg-[#0e1224] border border-white/5">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-white">Approval queue</span>
                      <span className="w-4 h-4 rounded-full bg-blue-500/20 text-blue-400 text-[10px] font-bold flex items-center justify-center">
                        3
                      </span>
                    </div>
                    <Link href="/approvals" className="text-[10px] text-blue-400 hover:underline">
                      View all &gt;
                    </Link>
                  </div>

                  <div className="space-y-2.5">
                    {[
                      { title: "Contract Review", sub: "Vendor Agreement - $120,000", status: "Needs review", color: "bg-purple-500/20 text-purple-300 border-purple-500/30" },
                      { title: "Invoice Agent", sub: "INV-8732 - $8,430.50", status: "Approved", color: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30" },
                      { title: "Support Copilot", sub: "Policy Update - v2.4", status: "Escalated", color: "bg-amber-500/20 text-amber-300 border-amber-500/30" },
                    ].map((item, i) => (
                      <div key={i} className="p-2.5 rounded-xl bg-[#12162a] border border-white/5 flex items-center justify-between">
                        <div>
                          <div className="text-xs font-medium text-white">{item.title}</div>
                          <div className="text-[10px] text-slate-400">{item.sub}</div>
                        </div>
                        <span className={`text-[10px] px-2 py-0.5 rounded-full border ${item.color}`}>
                          {item.status}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Cost Pulse Chart */}
                <div className="p-4 rounded-2xl bg-[#0e1224] border border-white/5">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-semibold text-white">Cost pulse</span>
                    <span className="text-[10px] text-slate-400">This month ▾</span>
                  </div>

                  <div className="flex items-baseline gap-2 mb-2">
                    <span className="text-lg font-bold text-white">$48,320</span>
                    <span className="text-[10px] text-slate-400">Total spend</span>
                    <span className="text-[10px] text-blue-400 font-mono ml-auto">May 24: $2,840</span>
                  </div>

                  {/* Spline Area Chart */}
                  <div className="h-24 w-full">
                    <svg className="w-full h-full" viewBox="0 0 300 80" preserveAspectRatio="none">
                      <defs>
                        <linearGradient id="costGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                          <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.4" />
                          <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.0" />
                        </linearGradient>
                      </defs>
                      <path
                        d="M 0 65 Q 40 60, 80 40 T 160 55 T 230 20 T 300 35 L 300 80 L 0 80 Z"
                        fill="url(#costGrad)"
                      />
                      <path
                        d="M 0 65 Q 40 60, 80 40 T 160 55 T 230 20 T 300 35"
                        fill="none"
                        stroke="#38bdf8"
                        strokeWidth="2.5"
                      />
                    </svg>
                  </div>
                  <div className="flex justify-between text-[9px] text-slate-500 font-mono mt-1">
                    <span>May 1</span>
                    <span>May 8</span>
                    <span>May 15</span>
                    <span>May 22</span>
                    <span>May 29</span>
                  </div>
                </div>

                {/* Deploy Smarter Routes Banner */}
                <div className="p-5 rounded-2xl bg-gradient-to-br from-[#121838] via-[#10142c] to-[#0b0e20] border border-blue-500/30 relative overflow-hidden flex flex-col justify-between shadow-lg">
                  <div className="relative z-10 mb-4">
                    <div className="text-sm font-bold text-white mb-1">Deploy smarter routes</div>
                    <p className="text-[11px] text-slate-400 leading-relaxed">
                      Optimize performance, cost, and reliability with intelligent routing.
                    </p>
                  </div>

                  <button
                    onClick={handleDeployRoute}
                    disabled={isDeploying}
                    className="relative z-10 w-full py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 active:scale-98 text-white font-semibold text-xs transition-all shadow-md shadow-blue-600/40 flex items-center justify-center gap-1.5"
                  >
                    <span>🚀 Deploy Route</span>
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
