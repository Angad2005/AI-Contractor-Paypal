"""
Enhanced verification with evidence collection and multiple verification methods.

This module verifies generated browser software with:
- Multiple verification methods (CSS selector, content check, attribute check, regex)
- Evidence collection for each check
- Detailed pass/fail reasoning
"""

from bs4 import BeautifulSoup
from pathlib import Path


LEGACY_KEYS = {"hero", "features", "pricing", "signup", "responsive", "navigation"}


def _legacy_checks(soup: BeautifulSoup, contract) -> list[dict]:
    checks = []

    hero_element = soup.select_one(".hero")
    checks.append({"key": "hero", "label": "Hero section exists", "passed": bool(hero_element), "evidence": f"Element with class 'hero' {'found' if hero_element else 'not found'} in the page", "method": "css_selector"})

    features_element = soup.select_one("#features .grid")
    checks.append({"key": "features", "label": "Feature grid exists", "passed": bool(features_element), "evidence": f"Element with selector '#features .grid' {'found' if features_element else 'not found'}", "method": "css_selector"})

    pricing_section = soup.select_one("#pricing")
    pricing_card = soup.select_one("#pricing .price-card") if pricing_section else None
    expected_price = f"{contract.price:.2f}"
    pricing_text = pricing_card.get_text() if pricing_card else ""
    checks.append({"key": "pricing", "label": "Pricing matches contract", "passed": bool(pricing_card and expected_price in pricing_text), "evidence": f"Expected price ${expected_price} {'found' if pricing_card and expected_price in pricing_text else 'not found'} in pricing card", "method": "content_check" if pricing_card else "css_selector"})

    signup_form = soup.select_one("#signup-form")
    email_input = soup.select_one("#signup-form input[type=email]") if signup_form else None
    checks.append({"key": "signup", "label": "Signup form is present", "passed": bool(signup_form and email_input), "evidence": "Signup form with email input found" if signup_form and email_input else f"Signup form {'not found' if not signup_form else 'missing email input'}", "method": "css_selector"})

    viewport_meta = soup.select_one('meta[name="viewport"]')
    viewport_content = viewport_meta.get("content", "") if viewport_meta else ""
    checks.append({"key": "responsive", "label": "Responsive viewport is configured", "passed": bool("width" in viewport_content), "evidence": "Viewport meta tag has width configured" if "width" in viewport_content else "Responsive viewport meta tag not found", "method": "attribute_check" if viewport_meta else "css_selector"})

    required_sections = ["features", "pricing", "signup"]
    missing_sections = [section for section in required_sections if not soup.select_one(f'a[href="#{section}"]')]
    checks.append({"key": "navigation", "label": "Navigation anchors resolve", "passed": not missing_sections, "evidence": f"Missing links: {', '.join(missing_sections)}" if missing_sections else "Navigation links for features, pricing, and signup found", "method": "css_selector"})

    semantic_tags = [tag for tag in ("nav", "main", "section", "footer") if soup.select_one(tag)]
    checks.append({"key": "semantic", "label": "Semantic HTML structure", "passed": len(semantic_tags) >= 3, "evidence": f"Found semantic tags: {', '.join(semantic_tags)}", "method": "css_selector"})
    return checks


def _software_checks(soup: BeautifulSoup, contract) -> list[dict]:
    """Verify product-specific acceptance markers instead of assuming a landing page."""
    checks = []
    for criterion in contract.criteria:
        key = criterion.key
        if key == "app_shell":
            main = soup.select_one("main")
            heading = soup.select_one("h1")
            passed = bool(main and heading and heading.get_text(strip=True))
            evidence = "Application main landmark and product heading found" if passed else "Application main landmark or product heading is missing"
        elif key == "responsive":
            viewport = soup.select_one('meta[name="viewport"]')
            passed = bool(viewport and "width" in viewport.get("content", ""))
            evidence = "Responsive viewport is configured" if passed else "Responsive viewport meta tag is missing"
        elif key == "navigation":
            nav = soup.select_one("nav")
            nav_items = nav.select("a[href], button") if nav else []
            passed = bool(nav_items)
            evidence = f"Found {len(nav_items)} usable navigation controls" if passed else "No usable navigation controls found"
        elif key == "core_workflow":
            elements = soup.find_all(attrs={"data-acceptance-key": key})
            interactive_tags = ["button", "input", "select", "textarea", "a"]
            passed = any(
                element.name in interactive_tags
                or element.get("role") in {"button", "link"}
                or element.find(interactive_tags)
                for element in elements
            )
            evidence = "A marked core-workflow control was found" if passed else "No interactive control is marked for the core workflow"
        else:
            elements = soup.find_all(attrs={"data-acceptance-key": key})
            passed = bool(elements)
            evidence = f"Found {len(elements)} element(s) marked for criterion '{key}'" if passed else f"No element marked data-acceptance-key='{key}'"

        checks.append({
            "key": key,
            "label": criterion.label,
            "passed": passed,
            "evidence": evidence,
            "method": "acceptance_marker" if key not in {"app_shell", "responsive", "navigation"} else "html_structure",
        })
    return checks


def verify_page_enhanced(path: str, contract) -> list[dict]:
    """
    Enhanced verification with evidence collection.

    Args:
        path: Path to the generated HTML file
        contract: Approved contract with criteria

    Returns:
        List of verification results with evidence
    """
    soup = BeautifulSoup(Path(path).read_text(encoding="utf-8"), "html.parser")
    checks = []

    criteria_keys = {criterion.key for criterion in contract.criteria}
    if criteria_keys == LEGACY_KEYS:
        checks.extend(_legacy_checks(soup, contract))
    else:
        checks.extend(_software_checks(soup, contract))
    return checks


def verify_page(path: str, contract, repaired: bool = False) -> list[dict]:
    """
    Main verification function - delegates to enhanced verification.

    This maintains backward compatibility with existing code.
    """
    return verify_page_enhanced(path, contract)
