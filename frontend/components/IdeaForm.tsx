"use client";

import { useState } from "react";
import { api, Idea } from "@/lib/api";

// A compact form to create a new idea. Calls the backend and tells the parent
// to refresh its list on success.
export default function IdeaForm({ onCreated }: { onCreated: (idea: Idea) => void }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [industry, setIndustry] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const idea = await api.createIdea({
        title,
        description,
        industry: industry || undefined,
      });
      setTitle("");
      setDescription("");
      setIndustry("");
      onCreated(idea);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create idea");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="card space-y-4">
      <h2 className="text-lg font-extrabold">New idea</h2>
      <input
        className="input"
        placeholder="Idea title"
        required
        value={title}
        onChange={(e) => setTitle(e.target.value)}
      />
      <textarea
        className="input min-h-[96px]"
        placeholder="Describe your startup idea in a sentence or two…"
        required
        value={description}
        onChange={(e) => setDescription(e.target.value)}
      />
      <input
        className="input"
        placeholder="Industry (optional)"
        value={industry}
        onChange={(e) => setIndustry(e.target.value)}
      />
      {error && <p className="text-sm font-medium text-red-600">{error}</p>}
      <button type="submit" disabled={busy} className="btn-primary w-full">
        {busy ? "Saving…" : "Add idea"}
      </button>
    </form>
  );
}
