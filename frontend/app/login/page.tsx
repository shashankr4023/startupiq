"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabaseClient";

type Mode = "login" | "signup";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setInfo(null);
    setBusy(true);
    try {
      if (mode === "login") {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
        router.replace("/ideas");
      } else {
        const { data, error } = await supabase.auth.signUp({ email, password });
        if (error) throw error;
        // Depending on your Supabase settings, signup may require email
        // confirmation before a session exists.
        if (data.session) {
          router.replace("/ideas");
        } else {
          setInfo("Account created. Check your email to confirm, then log in.");
          setMode("login");
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      {/* Brand panel */}
      <div className="relative hidden overflow-hidden bg-brand-blue p-12 text-white lg:block">
        <div className="absolute -right-16 top-24 h-72 w-72 rotate-12 rounded-[3rem] bg-brand-green/80" />
        <div className="relative">
          <span className="chip bg-brand-green text-ink">Welcome</span>
          <h1 className="mt-8 text-6xl font-black leading-none">
            Startup<span className="text-brand-green">IQ</span>
          </h1>
          <p className="mt-6 max-w-sm text-lg text-white/80">
            Evaluate your startup idea with AI — competitors, market, risks, MVP,
            and revenue, all in one place.
          </p>
        </div>
      </div>

      {/* Form panel */}
      <div className="flex items-center justify-center p-6">
        <div className="card w-full max-w-md">
          <h2 className="text-2xl font-extrabold">
            {mode === "login" ? "Log in" : "Create account"}
          </h2>
          <p className="mt-1 text-sm text-muted">
            {mode === "login"
              ? "Welcome back. Enter your details."
              : "Start evaluating your ideas."}
          </p>

          <form onSubmit={submit} className="mt-6 space-y-4">
            <div>
              <label className="mb-1 block text-sm font-semibold">Email</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="input"
                placeholder="you@example.com"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-semibold">Password</label>
              <input
                type="password"
                required
                minLength={6}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="input"
                placeholder="••••••••"
              />
            </div>

            {error && <p className="text-sm font-medium text-red-600">{error}</p>}
            {info && <p className="text-sm font-medium text-brand-green-dark">{info}</p>}

            <button type="submit" disabled={busy} className="btn-primary w-full">
              {busy ? "Please wait…" : mode === "login" ? "Log in" : "Sign up"}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-muted">
            {mode === "login" ? "No account yet?" : "Already have an account?"}{" "}
            <button
              onClick={() => {
                setMode(mode === "login" ? "signup" : "login");
                setError(null);
                setInfo(null);
              }}
              className="font-semibold text-brand-blue"
            >
              {mode === "login" ? "Sign up" : "Log in"}
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}
