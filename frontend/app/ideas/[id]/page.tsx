"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import AuthGuard from "@/components/AuthGuard";
import TopNav from "@/components/TopNav";
import FeatureTile from "@/components/FeatureTile";
import { FEATURES } from "@/lib/features";
import { api, Idea } from "@/lib/api";

function IdeaDetailInner({ id }: { id: string }) {
  const [idea, setIdea] = useState<Idea | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getIdea(id)
      .then(setIdea)
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Could not load idea")
      );
  }, [id]);

  return (
    <>
      <TopNav />
      <main className="mx-auto max-w-6xl px-6 py-10">
        <Link href="/ideas" className="text-sm font-semibold text-muted hover:text-ink">
          ← All ideas
        </Link>

        {error && <p className="mt-6 font-medium text-red-600">{error}</p>}

        {idea && (
          <>
            {/* Idea header */}
            <div className="mt-4 rounded-tile bg-brand-blue p-8 text-white shadow-tile">
              <span className="chip bg-brand-green text-ink">Startup idea</span>
              <h1 className="mt-4 text-4xl font-black">{idea.title}</h1>
              <p className="mt-3 max-w-2xl text-white/80">{idea.description}</p>
              {idea.industry && (
                <span className="chip mt-4 bg-white/15 text-white">{idea.industry}</span>
              )}
            </div>

            {/* Evaluation tiles */}
            <div className="mt-8 mb-4 flex items-baseline justify-between">
              <h2 className="text-2xl font-extrabold">
                Evaluate this <span className="text-brand-blue">idea</span>
              </h2>
              <p className="text-sm text-muted">Run each analysis independently</p>
            </div>

            <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {FEATURES.map((meta) => (
                <FeatureTile key={meta.key} ideaId={idea.id} meta={meta} />
              ))}
            </div>
          </>
        )}
      </main>
    </>
  );
}

export default function IdeaDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  // Next.js 15: route params are a Promise, unwrapped with React's `use()`.
  const { id } = use(params);
  return (
    <AuthGuard>
      <IdeaDetailInner id={id} />
    </AuthGuard>
  );
}
