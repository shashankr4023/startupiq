"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import AuthGuard from "@/components/AuthGuard";
import TopNav from "@/components/TopNav";
import IdeaForm from "@/components/IdeaForm";
import { api, Idea } from "@/lib/api";

function IdeasInner() {
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      setIdeas(await api.listIdeas());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load ideas");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const active = ideas.filter((i) => i.status !== "archived");

  return (
    <>
      <TopNav />
      <main className="mx-auto max-w-6xl px-6 py-10">
        <div className="mb-8">
          <h1 className="text-4xl font-black tracking-tight">
            Your <span className="text-brand-blue">ideas</span>
          </h1>
          <p className="mt-2 text-muted">
            Pick an idea to evaluate it across six dimensions.
          </p>
        </div>

        <div className="grid gap-8 lg:grid-cols-[1fr_360px]">
          {/* List */}
          <section>
            {loading && <p className="text-muted">Loading…</p>}
            {error && <p className="font-medium text-red-600">{error}</p>}
            {!loading && active.length === 0 && (
              <div className="card text-muted">
                No ideas yet — add your first one on the right.
              </div>
            )}
            <div className="grid gap-4 sm:grid-cols-2">
              {active.map((idea) => (
                <Link
                  key={idea.id}
                  href={`/ideas/${idea.id}`}
                  className="card group transition hover:-translate-y-0.5 hover:shadow-lg"
                >
                  <div className="flex items-start justify-between">
                    <h3 className="text-lg font-extrabold group-hover:text-brand-blue">
                      {idea.title}
                    </h3>
                    <span className="text-xl">→</span>
                  </div>
                  <p className="mt-2 line-clamp-3 text-sm text-muted">
                    {idea.description}
                  </p>
                  {idea.industry && (
                    <span className="chip mt-4 bg-brand-blue/10 text-brand-blue">
                      {idea.industry}
                    </span>
                  )}
                </Link>
              ))}
            </div>
          </section>

          {/* Create */}
          <aside>
            <IdeaForm onCreated={() => load()} />
          </aside>
        </div>
      </main>
    </>
  );
}

export default function IdeasPage() {
  return (
    <AuthGuard>
      <IdeasInner />
    </AuthGuard>
  );
}
