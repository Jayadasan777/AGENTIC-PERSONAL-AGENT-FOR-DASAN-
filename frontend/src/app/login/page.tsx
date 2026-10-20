"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";

export default function LoginPage() {
  const router = useRouter();
  const { login, register } = useAuth();

  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password, fullName || undefined);
      }
      router.push("/chat");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Authentication failed. Check your credentials.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleDemoFill = () => {
    setEmail("admin@aura.ai");
    setPassword("AuraMaster2026!");
  };

  return (
    <div className="min-h-screen bg-black flex items-center justify-center p-4 selection:bg-purple-500 selection:text-white">
      {/* Outer ambient glow */}
      <div className="absolute w-[600px] h-[450px] bg-purple-900/15 blur-[120px] rounded-full pointer-events-none" />

      {/* Main Container - Matching Vega.AI Layout & Proportions */}
      <div className="w-full max-w-4xl bg-[#0d0b16] border border-purple-500/25 rounded-[32px] overflow-hidden shadow-2xl shadow-purple-950/40 relative z-10 grid grid-cols-1 md:grid-cols-12 min-h-[540px]">
        
        {/* Left Column (46% width on desktop) - Futuristic 3D Purple Visual Artwork */}
        <div className="md:col-span-5 relative bg-gradient-to-br from-[#1e0e38] via-[#120726] to-[#0a0418] p-8 flex flex-col justify-between overflow-hidden border-b md:border-b-0 md:border-r border-purple-500/20">
          {/* Abstract 3D Geometric Ring Visual Art */}
          <div className="absolute inset-0 pointer-events-none opacity-85">
            <svg viewBox="0 0 400 600" className="w-full h-full object-cover">
              <defs>
                <linearGradient id="ringGrad1" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="#c084fc" />
                  <stop offset="40%" stopColor="#7e22ce" />
                  <stop offset="100%" stopColor="#2e1065" />
                </linearGradient>
                <linearGradient id="ringGrad2" x1="100%" y1="0%" x2="0%" y2="100%">
                  <stop offset="0%" stopColor="#a855f7" />
                  <stop offset="60%" stopColor="#4c1d95" />
                  <stop offset="100%" stopColor="#0f0728" />
                </linearGradient>
                <radialGradient id="ringGlow" cx="50%" cy="50%" r="50%">
                  <stop offset="0%" stopColor="#c084fc" stopOpacity="0.4" />
                  <stop offset="100%" stopColor="#581c87" stopOpacity="0" />
                </radialGradient>
              </defs>

              <circle cx="200" cy="300" r="160" fill="url(#ringGlow)" />
              {/* Outer torus arc */}
              <ellipse cx="180" cy="310" rx="150" ry="170" fill="none" stroke="url(#ringGrad1)" strokeWidth="48" strokeLinecap="round" transform="rotate(-25 180 310)" />
              {/* Inner torus arc */}
              <ellipse cx="210" cy="290" rx="110" ry="130" fill="none" stroke="url(#ringGrad2)" strokeWidth="36" strokeLinecap="round" transform="rotate(35 210 290)" />
              {/* Metallic highlight band */}
              <path d="M 90 260 C 140 180, 260 210, 310 330" fill="none" stroke="#e9d5ff" strokeWidth="6" strokeLinecap="round" opacity="0.6" />
              <path d="M 120 400 C 180 470, 270 440, 290 360" fill="none" stroke="#a855f7" strokeWidth="8" strokeLinecap="round" opacity="0.8" />
            </svg>
          </div>

          {/* Brand Logo - 4-point star + aura.AI */}
          <div className="relative z-10 flex items-center gap-2.5">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" className="text-purple-400">
              <path d="M12 2L14.5 9.5L22 12L14.5 14.5L12 22L9.5 14.5L2 12L9.5 9.5L12 2Z" fill="currentColor" />
            </svg>
            <span className="text-xl font-bold tracking-tight text-white font-sans">
              aura<span className="text-purple-400 font-semibold">.AI</span>
            </span>
          </div>

          {/* Carousel indicators at bottom */}
          <div className="relative z-10 flex items-center gap-2 mt-auto pt-24">
            <div className="h-1 w-12 bg-white rounded-full shadow-[0_0_8px_rgba(255,255,255,0.8)]" />
            <div className="h-1 w-8 bg-purple-900/60 rounded-full" />
            <div className="h-1 w-8 bg-purple-900/60 rounded-full" />
          </div>
        </div>

        {/* Right Column (54% width on desktop) - Login / Registration Panel */}
        <div className="md:col-span-7 p-8 md:p-12 flex flex-col justify-between relative bg-[#0c0a15]">
          {/* Top Row: Switch between Sign In / Sign Up */}
          <div className="flex items-center justify-end gap-3 text-xs">
            <span className="text-slate-400">
              {mode === "login" ? "Ainda não tem cadastro?" : "Já possui uma conta?"}
            </span>
            <button
              type="button"
              onClick={() => {
                setMode(mode === "login" ? "register" : "login");
                setError(null);
              }}
              className="bg-white text-black font-semibold px-4 py-1.5 rounded-lg hover:bg-slate-200 transition-colors shadow-sm"
            >
              {mode === "login" ? "Crie um Perfil" : "Fazer Login"}
            </button>
          </div>

          {/* Center Form Section */}
          <div className="my-auto py-6 max-w-sm w-full mx-auto">
            <h1 className="text-lg md:text-xl font-bold text-white mb-8 tracking-tight">
              {mode === "login"
                ? "Tenha acesso exclusivo a plataforma."
                : "Crie sua conta pessoal no AURA."}
            </h1>

            {error && (
              <div className="mb-5 p-2.5 rounded-lg bg-red-500/15 border border-red-500/30 text-red-400 text-xs">
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-6">
              {mode === "register" && (
                <div className="relative border-b border-purple-500/30 focus-within:border-purple-400 transition-colors pb-1">
                  <div className="flex items-center gap-2.5 text-slate-400">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                      <circle cx="12" cy="7" r="4" />
                    </svg>
                    <input
                      type="text"
                      placeholder="Nome completo"
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      className="bg-transparent text-sm text-white placeholder-slate-500 focus:outline-none w-full"
                    />
                  </div>
                </div>
              )}

              {/* Email field with envelope icon & underline style */}
              <div className="relative border-b border-purple-500/30 focus-within:border-purple-400 transition-colors pb-1">
                <div className="flex items-center gap-2.5 text-slate-400">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#8b5cf6" strokeWidth="2">
                    <rect width="20" height="16" x="2" y="4" rx="2" />
                    <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7" />
                  </svg>
                  <input
                    type="email"
                    placeholder="E-mail"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    className="bg-transparent text-sm text-white placeholder-slate-500 focus:outline-none w-full"
                  />
                </div>
              </div>

              {/* Password field with key icon & underline style */}
              <div className="relative border-b border-purple-500/30 focus-within:border-purple-400 transition-colors pb-1">
                <div className="flex items-center gap-2.5 text-slate-400">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#8b5cf6" strokeWidth="2">
                    <circle cx="7.5" cy="15.5" r="5.5" />
                    <path d="m21 2-9.6 9.6" />
                    <path d="m15.5 7.5 3 3L22 7l-3-3" />
                  </svg>
                  <input
                    type="password"
                    placeholder="Password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    className="bg-transparent text-sm text-white placeholder-slate-500 focus:outline-none w-full"
                  />
                </div>
              </div>

              {/* Centered Solid Vibrant Purple Pill Button */}
              <div className="pt-4 flex flex-col items-center">
                <button
                  type="submit"
                  disabled={loading}
                  className="w-44 py-2.5 rounded-xl bg-[#6415c4] hover:bg-[#741bdc] active:scale-98 text-white font-medium text-sm transition-all shadow-lg shadow-purple-900/50 flex items-center justify-center gap-2"
                >
                  {loading ? (
                    <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  ) : (
                    mode === "login" ? "Login" : "Cadastrar"
                  )}
                </button>

                <button
                  type="button"
                  onClick={handleDemoFill}
                  className="mt-3 text-[11px] text-slate-400 hover:text-purple-300 transition-colors"
                >
                  Esqueceu a sua senha?
                </button>
              </div>
            </form>
          </div>

          {/* Social / Quick Login Icons at bottom */}
          <div className="flex items-center justify-center gap-3 pt-4">
            <button
              type="button"
              onClick={handleDemoFill}
              title="Quick Demo Login"
              className="w-8 h-8 rounded-full bg-[#3b126d] hover:bg-[#4d198f] text-white flex items-center justify-center text-xs font-bold transition-all shadow-sm"
            >
              f
            </button>
            <button
              type="button"
              onClick={handleDemoFill}
              title="Quick Demo Login"
              className="w-8 h-8 rounded-full bg-[#3b126d] hover:bg-[#4d198f] text-white flex items-center justify-center text-xs font-bold transition-all shadow-sm"
            >
              in
            </button>
            <button
              type="button"
              onClick={handleDemoFill}
              title="Quick Demo Login"
              className="w-8 h-8 rounded-full bg-[#3b126d] hover:bg-[#4d198f] text-white flex items-center justify-center text-xs font-bold transition-all shadow-sm"
            >
              G
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
