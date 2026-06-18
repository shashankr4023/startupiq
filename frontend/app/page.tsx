"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabaseClient";

// The root route just decides where to send you: into the app if logged in,
// otherwise to the login page.
export default function Home() {
  const router = useRouter();
  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      router.replace(data.session ? "/ideas" : "/login");
    });
  }, [router]);

  return (
    <div className="flex min-h-screen items-center justify-center text-muted">
      Loading…
    </div>
  );
}
