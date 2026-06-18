"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { FeatureMeta } from "@/lib/features";
import FeatureResult from "@/components/results/FeatureResult";

type Status = "idle" | "queued" | "running" | "completed" | "failed";

// One evaluation tile. Clicking "Evaluate" enqueues a job on the backend, then
// polls GET /jobs/{id} every 2s until it's done, then renders the visualised
// result. This is the async pattern from Phase 3, seen from the client side.
export default function FeatureTile({
  ideaId,
  meta,
}: {
  ideaId: string;
  meta: FeatureMeta;
}) {
  const [status, setStatus] = useState<Status>("idle");
  const [jobId, setJobId] = useState<string | null>(null);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = () => {
    if (timer.current) {
      clearInterval(timer.current);
      timer.current = null;
    }
  };

  const run = useCallback(async () => {
    setError(null);
    setResult(null);
    setStatus("queued");
    try {
      const job = await api.requestEvaluation(ideaId, meta.key);
      setJobId(job.job_id);
    } catch (err) {
      setStatus("failed");
      setError(err instanceof Error ? err.message : "Could not start evaluation");
    }
  }, [ideaId, meta.key]);

  // Poll while we have a job that isn't finished.
  useEffect(() => {
    if (!jobId) return;
    stopPolling();
    timer.current = setInterval(async () => {
      try {
        const job = await api.getJob(jobId);
        if (job.status === "completed") {
          stopPolling();
          setResult(job.result);
          setStatus("completed");
        } else if (job.status === "failed") {
          stopPolling();
          setError(job.error_message ?? "Evaluation failed");
          setStatus("failed");
        } else {
          setStatus(job.status as Status); // queued | running
        }
      } catch (err) {
        stopPolling();
        setError(err instanceof Error ? err.message : "Lost the job");
        setStatus("failed");
      }
    }, 2000);
    return stopPolling;
  }, [jobId]);

  const accentBar =
    meta.accent === "blue" ? "bg-brand-blue" : "bg-brand-green";
  const busy = status === "queued" || status === "running";

  return (
    <div className="card flex flex-col overflow-hidden p-0">
      <div className={`h-1.5 w-full ${accentBar}`} />
      <div className="flex flex-1 flex-col p-5">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-surface text-xl">
              {meta.icon}
            </span>
            <div>
              <h3 className="font-extrabold leading-tight">{meta.label}</h3>
              <p className="text-xs text-muted">{meta.blurb}</p>
            </div>
          </div>
          {status === "completed" && (
            <button onClick={run} className="text-xs font-bold text-brand-blue">
              Re-run
            </button>
          )}
        </div>

        <div className="mt-4 flex-1">
          {status === "idle" && (
            <button onClick={run} className="btn-primary w-full text-sm">
              Evaluate
            </button>
          )}

          {busy && (
            <div className="flex items-center gap-2 text-sm font-semibold text-muted">
              <span className="h-3 w-3 animate-spin rounded-full border-2 border-brand-blue border-t-transparent" />
              {status === "queued" ? "Queued…" : "Analyzing…"}
            </div>
          )}

          {status === "failed" && (
            <div className="space-y-2">
              <p className="text-sm font-medium text-red-600">{error}</p>
              <button onClick={run} className="btn-ghost w-full text-sm">
                Try again
              </button>
            </div>
          )}

          {status === "completed" && result && (
            <FeatureResult feature={meta.key} result={result} />
          )}
        </div>
      </div>
    </div>
  );
}
