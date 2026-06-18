// Metadata for the six evaluation features, mirroring the backend's FeatureType.
// Drives the tile grid: label, an emoji icon, and an alternating accent colour
// (blue / green) to match the reference design.

export type FeatureKey =
  | "competitor_research"
  | "target_customer"
  | "market_opportunity"
  | "risk_identification"
  | "mvp_feasibility"
  | "revenue_model";

export interface FeatureMeta {
  key: FeatureKey;
  label: string;
  blurb: string;
  icon: string;
  accent: "blue" | "green";
}

export const FEATURES: FeatureMeta[] = [
  {
    key: "competitor_research",
    label: "Competitor Research",
    blurb: "Who else is in this space",
    icon: "🥊",
    accent: "blue",
  },
  {
    key: "target_customer",
    label: "Target Customers",
    blurb: "Who you're building for",
    icon: "🎯",
    accent: "green",
  },
  {
    key: "market_opportunity",
    label: "Market Opportunity",
    blurb: "How big the prize is",
    icon: "📈",
    accent: "blue",
  },
  {
    key: "risk_identification",
    label: "Risk Analysis",
    blurb: "What could go wrong",
    icon: "⚠️",
    accent: "green",
  },
  {
    key: "mvp_feasibility",
    label: "MVP & Feasibility",
    blurb: "What to build first",
    icon: "🛠️",
    accent: "blue",
  },
  {
    key: "revenue_model",
    label: "Revenue Models",
    blurb: "How it makes money",
    icon: "💰",
    accent: "green",
  },
];
