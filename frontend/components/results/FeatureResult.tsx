"use client";

import { useState } from "react";
import { FeatureKey } from "@/lib/features";
import { Badge, Bar, Chips, ScoreRing, Stat, levelColor } from "./primitives";

// Renders the structured evaluation result for one feature as a small
// visualisation plus a summary, with an expandable "details" section. Each
// branch reads the fields produced by the matching backend result schema.

type AnyResult = Record<string, any>;

function Summary({ text }: { text: string }) {
  return <p className="mt-3 text-sm leading-relaxed text-slate-600">{text}</p>;
}

function Details({ open, onToggle, children }: {
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="mt-3">
      <button onClick={onToggle} className="text-xs font-bold text-brand-blue">
        {open ? "Hide details ▲" : "Show details ▼"}
      </button>
      {open && <div className="mt-3 space-y-3 text-sm text-slate-600">{children}</div>}
    </div>
  );
}

export default function FeatureResult({
  feature,
  result,
}: {
  feature: FeatureKey;
  result: AnyResult;
}) {
  const [open, setOpen] = useState(false);

  if (feature === "competitor_research") {
    const comps = (result.competitors ?? []) as AnyResult[];
    return (
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge color={levelColor(result.market_saturation ?? "")}>
            {result.market_saturation}
          </Badge>
          <Badge color="blue">{comps.length} competitors</Badge>
        </div>
        <Summary text={result.summary} />
        <Details open={open} onToggle={() => setOpen(!open)}>
          {comps.map((c, i) => (
            <div key={i} className="rounded-lg bg-surface p-3">
              <div className="font-bold text-ink">{c.name}</div>
              <div>{c.description}</div>
              <div className="mt-1 text-xs">
                <span className="font-semibold text-brand-green-dark">Edge: </span>
                {c.differentiation}
              </div>
            </div>
          ))}
        </Details>
      </div>
    );
  }

  if (feature === "target_customer") {
    const segs = (result.segments ?? []) as AnyResult[];
    return (
      <div>
        <Badge color="blue">Primary: {result.primary_segment}</Badge>
        <Summary text={result.summary} />
        <Details open={open} onToggle={() => setOpen(!open)}>
          {segs.map((s, i) => (
            <div key={i} className="rounded-lg bg-surface p-3">
              <div className="font-bold text-ink">{s.name}</div>
              <div>{s.description}</div>
              <div className="mt-1.5">
                <Chips items={s.pain_points ?? []} />
              </div>
            </div>
          ))}
        </Details>
      </div>
    );
  }

  if (feature === "market_opportunity") {
    return (
      <div>
        <div className="grid grid-cols-3 gap-2">
          <Stat value={result.tam?.estimate ?? "—"} caption="TAM" />
          <Stat value={result.sam?.estimate ?? "—"} caption="SAM" />
          <Stat value={result.som?.estimate ?? "—"} caption="SOM" />
        </div>
        <div className="mt-2">
          <Badge color="green">{result.growth_trend}</Badge>
        </div>
        <Summary text={result.summary} />
        <Details open={open} onToggle={() => setOpen(!open)}>
          <p><b>TAM:</b> {result.tam?.reasoning}</p>
          <p><b>SAM:</b> {result.sam?.reasoning}</p>
          <p><b>SOM:</b> {result.som?.reasoning}</p>
          <Chips items={result.key_drivers ?? []} />
        </Details>
      </div>
    );
  }

  if (feature === "risk_identification") {
    const risks = (result.risks ?? []) as AnyResult[];
    const bySeverity = risks.reduce<Record<string, number>>((acc, r) => {
      const key = (r.severity ?? "unknown").toLowerCase();
      acc[key] = (acc[key] ?? 0) + 1;
      return acc;
    }, {});
    return (
      <div>
        <div className="flex flex-wrap gap-2">
          {Object.entries(bySeverity).map(([sev, n]) => (
            <Badge key={sev} color={levelColor(sev)}>
              {n} {sev}
            </Badge>
          ))}
        </div>
        <Summary text={result.summary} />
        <Details open={open} onToggle={() => setOpen(!open)}>
          {risks.map((r, i) => (
            <div key={i} className="rounded-lg bg-surface p-3">
              <div className="flex items-center gap-2">
                <Badge color={levelColor(r.severity ?? "")}>{r.severity}</Badge>
                <span className="font-bold text-ink">{r.category}</span>
              </div>
              <div className="mt-1">{r.description}</div>
              <div className="mt-1 text-xs">
                <span className="font-semibold text-brand-green-dark">Mitigation: </span>
                {r.mitigation}
              </div>
            </div>
          ))}
        </Details>
      </div>
    );
  }

  if (feature === "mvp_feasibility") {
    return (
      <div>
        <ScoreRing value={Number(result.feasibility_score) || 0} label="Feasibility" />
        <div className="mt-2 flex flex-wrap gap-2">
          <Badge color={levelColor(result.build_complexity ?? "")}>
            {result.build_complexity} complexity
          </Badge>
          <Badge color="blue">{result.estimated_timeline}</Badge>
        </div>
        <Summary text={result.summary} />
        <Details open={open} onToggle={() => setOpen(!open)}>
          <div>
            <div className="font-semibold text-ink">MVP features</div>
            <ul className="mt-1 list-disc pl-5">
              {(result.mvp_features ?? []).map((f: string, i: number) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          </div>
          <div>
            <div className="font-semibold text-ink">Key challenges</div>
            <Chips items={result.key_challenges ?? []} />
          </div>
        </Details>
      </div>
    );
  }

  if (feature === "revenue_model") {
    const models = (result.models ?? []) as AnyResult[];
    return (
      <div>
        <Badge color="green">Recommended: {result.recommended_model}</Badge>
        <div className="mt-3 space-y-2">
          {models.map((m, i) => (
            <Bar key={i} label={m.name} value={Number(m.fit_score) || 0} />
          ))}
        </div>
        <Summary text={result.summary} />
        <Details open={open} onToggle={() => setOpen(!open)}>
          {models.map((m, i) => (
            <div key={i} className="rounded-lg bg-surface p-3">
              <div className="font-bold text-ink">{m.name}</div>
              <div>{m.description}</div>
            </div>
          ))}
        </Details>
      </div>
    );
  }

  return <Summary text={result.summary ?? "Done."} />;
}
