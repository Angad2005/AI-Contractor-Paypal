from app.schemas.jobs import Contract, Criterion
from app.services.llm_provider import LLMProviderError, complete_json, is_demo_mode


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


def _source_project_contract(budget: float) -> Contract:
    return Contract(
        required_sections=["project source files"],
        required_features=["downloadable source project"],
        criteria=[
            Criterion(
                key="source_package",
                label="Downloadable source project",
                detail="A non-empty project source package is generated and available after payment.",
            )
        ],
        price=round(budget, 2),
    )


def make_contract(
    prompt: str, budget: float, deliverable_type: str = "browser_app"
) -> Contract:
    """Create a contract with a real structured-output LLM when configured.

    Price and currency are always overridden by server-controlled values so the model
    cannot redefine the commercial terms supplied by the customer.
    """
    if deliverable_type == "source_project":
        return _source_project_contract(budget)

    if is_demo_mode():
        return _deterministic_contract(prompt, budget)

    result = None
    try:
        from app.services.agent_workflow import run_contract_analyst_agent
        result = run_contract_analyst_agent(prompt, budget)
    except Exception:
        pass

    if not result:
        result = complete_json(
            """You are the contract analyst for an outcome-based AI software contractor.
Return only JSON with required_sections (array of meaningful screen or section names),
required_features (array of product capabilities), and criteria (array of objects with
key, label, detail, required). Write 4-12 concrete, independently verifiable criteria
for a browser-based software product described in the brief, with one criterion for
each distinct requested feature or workflow. Include an app_shell
criterion and a core_workflow criterion, plus responsive behavior and navigation when
relevant. Use short lowercase snake_case keys and feature-specific criteria. Do not use
landing-page-only hero, features, pricing, or signup criteria unless the brief asks for
a marketing page. Do not turn the contractor budget into a product price or ask for a
generic marketing landing page unless the brief does.""",
            f"Customer brief:\n{prompt}\nApproved contractor budget: {budget:.2f} USD",
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
