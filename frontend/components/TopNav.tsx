"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabaseClient";

// The persistent top bar: brand mark on the left, sign-out on the right.
export default function TopNav() {
  const router = useRouter();

  async function signOut() {
    await supabase.auth.signOut();
    router.replace("/login");
  }

  return (
    <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/80 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <Link href="/ideas" className="flex items-center gap-2">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-blue font-black text-white">
            IQ
          </span>
          <span className="text-lg font-extrabold tracking-tight">
            Startup<span className="text-brand-blue">IQ</span>
          </span>
        </Link>
        <button onClick={signOut} className="btn-ghost py-2 text-sm">
          Sign out
        </button>
      </div>
    </header>
  );
}
