"""Pydantic schemas describing the *structured* output we want the LLM to
return for each evaluation feature type.

These models do double duty:
1. They are passed to the LLM provider as the required output schema
   (OpenAI structured outputs / Claude `messages.parse`), so the model is
   constrained to return exactly this shape.
2. They validate the model's response before we ever use it.

All fields are required (no Optional) and `additionalProperties` is implicitly
forbidden by the providers' strict structured-output modes - this keeps both
OpenAI and Claude happy. Numeric ranges (e.g. scores 1-10) are described in the
field descriptions rather than enforced with ge/le constraints, because strict
structured outputs don't support numeric bounds.
"""

from pydantic import BaseModel, Field

# --- Competitor research ----------------------------------------------------


class Competitor(BaseModel):
    name: str = Field(description="Company or product name")
    description: str = Field(description="What they do, in one or two sentences")
    strengths: list[str] = Field(description="Key strengths / advantages")
    weaknesses: list[str] = Field(description="Key weaknesses / gaps")
    differentiation: str = Field(
        description="How the user's idea could differentiate from this competitor"
    )


class CompetitorResearchResult(BaseModel):
    summary: str = Field(description="Overall competitive landscape summary")
    competitors: list[Competitor] = Field(description="3-6 notable competitors")
    market_saturation: str = Field(
        description="How crowded the market is: 'low', 'medium', or 'high', with a brief reason"
    )


# --- Target customer analysis ----------------------------------------------


class CustomerSegment(BaseModel):
    name: str = Field(description="Short label for this customer segment")
    description: str = Field(description="Who they are")
    pain_points: list[str] = Field(description="Problems this segment feels acutely")
    demographics: str = Field(description="Rough demographic / firmographic profile")


class TargetCustomerResult(BaseModel):
    summary: str = Field(description="Overall target-customer summary")
    segments: list[CustomerSegment] = Field(description="2-4 customer segments")
    primary_segment: str = Field(
        description="Which segment to target first, and why"
    )


# --- Market opportunity (TAM/SAM/SOM) --------------------------------------


class MarketSize(BaseModel):
    estimate: str = Field(description="A figure or range, e.g. '$2.5B'")
    reasoning: str = Field(description="How this estimate was derived")


class MarketOpportunityResult(BaseModel):
    summary: str = Field(description="Overall market opportunity summary")
    tam: MarketSize = Field(description="Total Addressable Market")
    sam: MarketSize = Field(description="Serviceable Addressable Market")
    som: MarketSize = Field(description="Serviceable Obtainable Market (realistic short-term)")
    growth_trend: str = Field(description="Is the market growing, flat, or shrinking, and why")
    key_drivers: list[str] = Field(description="Trends/forces driving this market")


# --- Risk identification ----------------------------------------------------


class Risk(BaseModel):
    category: str = Field(
        description="Risk category, e.g. 'market', 'execution', 'financial', 'regulatory', 'technical'"
    )
    description: str = Field(description="What the risk is")
    severity: str = Field(description="'low', 'medium', or 'high'")
    likelihood: str = Field(description="'low', 'medium', or 'high'")
    mitigation: str = Field(description="How to reduce or manage this risk")


class RiskResult(BaseModel):
    summary: str = Field(description="Overall risk picture")
    risks: list[Risk] = Field(description="4-8 key risks")


# --- MVP generation & feasibility ------------------------------------------


class MVPFeasibilityResult(BaseModel):
    summary: str = Field(description="Overall feasibility summary")
    mvp_features: list[str] = Field(
        description="The minimal set of features the MVP should ship with"
    )
    feasibility_score: int = Field(
        description="Overall feasibility on a 1-10 scale (10 = very feasible)"
    )
    build_complexity: str = Field(description="'low', 'medium', or 'high'")
    estimated_timeline: str = Field(
        description="Rough time for a small team to build the MVP, e.g. '6-8 weeks'"
    )
    key_challenges: list[str] = Field(description="The hardest parts of building this")


# --- Revenue models ---------------------------------------------------------


class RevenueStream(BaseModel):
    name: str = Field(description="e.g. 'Subscription (SaaS)', 'Marketplace fee', 'Freemium'")
    description: str = Field(description="How it works for this idea")
    pros: list[str] = Field(description="Advantages")
    cons: list[str] = Field(description="Drawbacks")
    fit_score: int = Field(description="How well it fits this idea, 1-10")


class RevenueModelResult(BaseModel):
    summary: str = Field(description="Overall monetization summary")
    models: list[RevenueStream] = Field(description="2-4 candidate revenue models")
    recommended_model: str = Field(description="Which model to start with, and why")
