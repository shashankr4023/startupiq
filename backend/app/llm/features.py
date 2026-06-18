"""The registry that ties everything together for the evaluation engine.

Each evaluation "feature" (competitor research, risk identification, ...) is
described once here by a `FeatureSpec`:

- which Pydantic result schema the LLM must fill in
- a human label
- the feature-specific instruction added to the prompt

The API and worker never hard-code feature logic - they look it up in this
registry. Adding a new evaluation type later means adding one entry here plus a
result schema, nothing else.
"""

from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel

from app.db.models.idea import StartupIdea
from app.schemas.llm_results import (
    CompetitorResearchResult,
    MarketOpportunityResult,
    MVPFeasibilityResult,
    RevenueModelResult,
    RiskResult,
    TargetCustomerResult,
)


class FeatureType(str, Enum):
    """The evaluation types a user can request for an idea.

    Inheriting from `str` makes these usable directly as URL path values and
    JSON strings (e.g. "competitor_research").
    """

    competitor_research = "competitor_research"
    target_customer = "target_customer"
    market_opportunity = "market_opportunity"
    risk_identification = "risk_identification"
    mvp_feasibility = "mvp_feasibility"
    revenue_model = "revenue_model"


@dataclass(frozen=True)
class FeatureSpec:
    label: str
    result_schema: type[BaseModel]
    instruction: str


# The single source of truth mapping each feature type to its schema + prompt.
FEATURES: dict[FeatureType, FeatureSpec] = {
    FeatureType.competitor_research: FeatureSpec(
        label="Competitor Research",
        result_schema=CompetitorResearchResult,
        instruction=(
            "Identify the most relevant existing competitors and substitutes for this "
            "startup idea. For each, assess strengths, weaknesses, and how this idea could "
            "differentiate. Then judge how saturated the market is."
        ),
    ),
    FeatureType.target_customer: FeatureSpec(
        label="Target Customer Analysis",
        result_schema=TargetCustomerResult,
        instruction=(
            "Identify the most promising target customer segments for this idea. For each "
            "segment, describe who they are, their acute pain points, and their rough "
            "demographic/firmographic profile. Recommend which segment to target first."
        ),
    ),
    FeatureType.market_opportunity: FeatureSpec(
        label="Market Opportunity",
        result_schema=MarketOpportunityResult,
        instruction=(
            "Estimate the market opportunity using TAM (total addressable), SAM "
            "(serviceable addressable), and SOM (realistic short-term obtainable). Show your "
            "reasoning for each figure, describe the growth trend, and list the key drivers."
        ),
    ),
    FeatureType.risk_identification: FeatureSpec(
        label="Risk Identification",
        result_schema=RiskResult,
        instruction=(
            "Identify the key risks facing this idea across categories such as market, "
            "execution, financial, regulatory, and technical. For each risk give a severity, "
            "a likelihood, and a concrete mitigation."
        ),
    ),
    FeatureType.mvp_feasibility: FeatureSpec(
        label="MVP & Feasibility",
        result_schema=MVPFeasibilityResult,
        instruction=(
            "Propose the minimal set of features for an MVP that tests this idea's core "
            "hypothesis. Assess build complexity, estimate a realistic timeline for a small "
            "team, give an overall feasibility score from 1-10, and list the key challenges."
        ),
    ),
    FeatureType.revenue_model: FeatureSpec(
        label="Revenue Models",
        result_schema=RevenueModelResult,
        instruction=(
            "Propose candidate revenue models for this idea. For each, explain how it would "
            "work, its pros and cons, and a fit score from 1-10. Recommend which model to "
            "start with and why."
        ),
    ),
}


SYSTEM_PROMPT = (
    "You are StartupIQ, an experienced startup analyst and venture advisor. "
    "You give realistic, specific, and honest assessments of startup ideas - never "
    "generic filler. When evidence is thin, reason from first principles and clearly "
    "label estimates as estimates. Respond ONLY with the requested structured data."
)


def build_user_prompt(idea: StartupIdea, spec: FeatureSpec) -> str:
    """Assemble the per-request prompt from the idea's details and the feature
    instruction."""
    lines = [
        f"Startup idea title: {idea.title}",
        f"Description: {idea.description}",
    ]
    if idea.industry:
        lines.append(f"Industry: {idea.industry}")
    if idea.target_market:
        lines.append(f"Target market (as stated by founder): {idea.target_market}")
    lines.append("")
    lines.append(f"Task: {spec.instruction}")
    return "\n".join(lines)
