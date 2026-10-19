import re

from app.schemas.jobs import Contract, Criterion
from app.services.llm_provider import LLMProviderError, complete_json, is_configured


def _deterministic_contract(prompt: str, budget: float) -> Contract:
    lowered = prompt.lower()
    sections = ["hero", "features", "pricing", "signup"]
    if "testimonial" in lowered:
        sections.insert(3, "testimonials")
    criteria = [
        Criterion(key="hero", label="Hero section", detail="Clear value proposition with primary call to action."),
        Criterion(key="features", label="Feature grid", detail="Three scannable benefits that explain the offer."),
        Criterion(key="pricing", label="Pricing card", detail="A visible price card matching the approved budget."),
        Criterion(key="signup", label="Working signup form", detail="Email form validates input and shows success feedback."),
        Criterion(key="responsive", label="Responsive layout", detail="Readable at mobile and desktop viewport widths."),
        Criterion(key="navigation", label="Working navigation", detail="Navigation links point to real sections on the page."),
    ]
    return Contract(
        required_sections=sections,
        required_features=[criterion.key for criterion in criteria],
        criteria=criteria,
        price=round(budget, 2),
    )


def make_contract(prompt: str, budget: float) -> Contract:
    """Create a contract with a real structured-output LLM when configured.

    Price and currency are always overridden by server-controlled values so the model
    cannot redefine the commercial terms supplied by the customer.
    """
    if is_configured():
        try:
            result = complete_json(
                """You are the contract analyst for an outcome-based AI contractor.
Return only JSON with required_sections (array of strings), required_features (array
of strings), and criteria (array of objects with key, label, detail, required).
Criteria must be concrete and independently testable for an HTML landing page.""",
                f"Customer brief:\n{prompt}\nApproved budget: {budget:.2f} USD",
            )
            contract = Contract.model_validate(
                {
                    **result,
                    "price": round(budget, 2),
                    "currency": "USD",
                }
            )
            if not contract.criteria:
                raise ValueError("The model returned no acceptance criteria")
            return contract
        except (LLMProviderError, ValueError, TypeError):
            # The demo remains runnable if a provider is temporarily unavailable.
            # The configured-provider path is still exercised whenever the request succeeds.
            pass
    return _deterministic_contract(prompt, budget)
