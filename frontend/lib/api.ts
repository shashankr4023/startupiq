import { supabase } from "./supabaseClient";

// Single wrapper for every call to the FastAPI backend. It attaches the current
// Supabase access token as a Bearer header (which the backend verifies via
// JWKS) and parses JSON. Centralising this means auth + error handling live in
// one place rather than being copy-pasted into every component.

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function authHeader(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(await authHeader()),
    ...((options.headers as Record<string, string>) ?? {}),
  };

  const res = await fetch(`${API_BASE}/api/v1${path}`, { ...options, headers });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* response had no JSON body */
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ---- Typed API surface -----------------------------------------------------

export interface Idea {
  id: string;
  title: string;
  description: string;
  industry: string | null;
  target_market: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface JobResponse {
  job_id: string;
  status: string; // queued | running | completed | failed
  feature_type?: string;
}

export interface Job {
  job_id: string;
  idea_id: string;
  feature_type: string;
  status: string;
  result: Record<string, unknown> | null;
  error_message: string | null;
}

export const api = {
  listIdeas: () => request<Idea[]>("/ideas"),
  getIdea: (id: string) => request<Idea>(`/ideas/${id}`),
  createIdea: (body: {
    title: string;
    description: string;
    industry?: string;
    target_market?: string;
  }) => request<Idea>("/ideas", { method: "POST", body: JSON.stringify(body) }),
  requestEvaluation: (ideaId: string, feature: string) =>
    request<JobResponse>(`/ideas/${ideaId}/evaluations/${feature}`, {
      method: "POST",
    }),
  getJob: (jobId: string) => request<Job>(`/jobs/${jobId}`),
};
