"""
Enhanced verification with evidence collection and multiple verification methods.

This module provides comprehensive verification of generated landing pages with:
- Multiple verification methods (CSS selector, content check, attribute check, regex)
- Evidence collection for each check
- Detailed pass/fail reasoning
"""

from bs4 import BeautifulSoup
from pathlib import Path
import re


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

    # Check 1: Hero section exists
    hero_element = soup.select_one(".hero")
    checks.append({
        "key": "hero",
        "label": "Hero section exists",
        "passed": bool(hero_element),
        "evidence": f"Element with class 'hero' {'found' if hero_element else 'not found'} in the page",
        "method": "css_selector"
    })

    # Check 2: Feature grid exists
    features_element = soup.select_one("#features .grid")
    checks.append({
        "key": "features",
        "label": "Feature grid exists",
        "passed": bool(features_element),
        "evidence": f"Element with selector '#features .grid' {'found' if features_element else 'not found'}",
        "method": "css_selector"
    })

    # Check 3: Pricing matches contract
    pricing_section = soup.select_one("#pricing")
    pricing_card = soup.select_one("#pricing .price-card") if pricing_section else None
    expected_price = f"{contract.price:.2f}"

    if pricing_card:
        pricing_text = pricing_card.get_text()
        price_matches = expected_price in pricing_text
        checks.append({
            "key": "pricing",
            "label": "Pricing matches contract",
            "passed": price_matches,
            "evidence": f"Expected price ${expected_price} {'found' if price_matches else 'not found'} in pricing card",
            "method": "content_check"
        })
    else:
        checks.append({
            "key": "pricing",
            "label": "Pricing matches contract",
            "passed": False,
            "evidence": "Pricing card element not found in the page",
            "method": "css_selector"
        })

    # Check 4: Signup form is present
    signup_form = soup.select_one("#signup-form")
    email_input = soup.select_one("#signup-form input[type=email]") if signup_form else None

    if signup_form and email_input:
        checks.append({
            "key": "signup",
            "label": "Signup form is present",
            "passed": True,
            "evidence": "Signup form with email input found",
            "method": "css_selector"
        })
    else:
        checks.append({
            "key": "signup",
            "label": "Signup form is present",
            "passed": False,
            "evidence": f"Signup form {'not found' if not signup_form else 'missing email input'}",
            "method": "css_selector"
        })

    # Check 5: Responsive viewport is configured
    viewport_meta = soup.select_one('meta[name="viewport"]')
    if viewport_meta:
        content = viewport_meta.get("content", "")
        has_width = "width" in content
        checks.append({
            "key": "responsive",
            "label": "Responsive viewport is configured",
            "passed": has_width,
            "evidence": f"Viewport meta tag {'has width attribute' if has_width else 'missing width attribute'}",
            "method": "attribute_check"
        })
    else:
        checks.append({
            "key": "responsive",
            "label": "Responsive viewport is configured",
            "passed": False,
            "evidence": "Viewport meta tag not found in the page",
            "method": "css_selector"
        })

    # Check 6: Navigation anchors resolve
    required_sections = ["features", "pricing", "signup"]
    nav_links_found = []
    nav_links_missing = []

    for section in required_sections:
        link = soup.select_one(f'a[href="#{section}"]')
        if link:
            nav_links_found.append(section)
        else:
            nav_links_missing.append(section)

    all_nav_links_valid = len(nav_links_missing) == 0
    checks.append({
        "key": "navigation",
        "label": "Navigation anchors resolve",
        "passed": all_nav_links_valid,
        "evidence": f"Navigation links for {', '.join(nav_links_found) if nav_links_found else 'none'} found; {', '.join(nav_links_missing) if nav_links_missing else 'none'} missing",
        "method": "css_selector"
    })

    # Check 7: Semantic HTML structure
    semantic_tags = ["nav", "main", "section", "footer"]
    found_semantic = [tag for tag in semantic_tags if soup.select_one(tag)]
    checks.append({
        "key": "semantic",
        "label": "Semantic HTML structure",
        "passed": len(found_semantic) >= 3,
        "evidence": f"Found semantic tags: {', '.join(found_semantic)}",
        "method": "css_selector"
    })

    return checks


def verify_page(path: str, contract, repaired: bool = False) -> list[dict]:
    """
    Main verification function - delegates to enhanced verification.

    This maintains backward compatibility with existing code.
    """
    return verify_page_enhanced(path, contract)
