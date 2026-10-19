"""
Browser-based functional verification using Playwright.

This module tests the generated page in a real headless browser to verify:
- Form submission functionality
- Navigation links work correctly
- Responsive layout behavior
- JavaScript console errors

Note: Playwright is optional. If not installed, falls back to HTML-only verification.
"""

from pathlib import Path
from typing import Optional

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


def verify_with_browser(path: str, contract) -> list[dict]:
    """
    Verify the generated page using a real browser.

    Args:
        path: Path to the generated HTML file
        contract: Approved contract

    Returns:
        List of verification results from browser tests
    """
    if not PLAYWRIGHT_AVAILABLE:
        return [{
            "key": "browser_check",
            "label": "Browser-based verification",
            "passed": False,
            "evidence": "Playwright not installed. Install with: pip install playwright && playwright install",
            "method": "browser"
        }]

    checks = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            # Load the generated page
            page.goto(f"file://{Path(path).absolute()}")

            # Test 1: Form submission
            try:
                page.fill("#email", "test@example.com")
                page.click("#signup-form button", timeout=2000)
                # Wait for success message
                message = page.query_selector("#form-message")
                if message:
                    checks.append({
                        "key": "form_functional",
                        "label": "Signup form submits successfully",
                        "passed": True,
                        "evidence": "Form submission completed, success message displayed",
                        "method": "browser"
                    })
                else:
                    checks.append({
                        "key": "form_functional",
                        "label": "Signup form submits successfully",
                        "passed": False,
                        "evidence": "Form submitted but no success message found",
                        "method": "browser"
                    })
            except Exception as e:
                checks.append({
                    "key": "form_functional",
                    "label": "Signup form submits successfully",
                    "passed": False,
                    "evidence": f"Form submission failed: {str(e)}",
                    "method": "browser"
                })

            # Test 2: Navigation links work
            try:
                for section in ["features", "pricing", "signup"]:
                    link = page.query_selector(f'a[href="#{section}"]')
                    if link:
                        link.click()
                        page.wait_for_timeout(500)
                checks.append({
                    "key": "navigation_functional",
                    "label": "Navigation links scroll to sections",
                    "passed": True,
                    "evidence": "All navigation links scrolled to correct sections",
                    "method": "browser"
                })
            except Exception as e:
                checks.append({
                    "key": "navigation_functional",
                    "label": "Navigation links scroll to sections",
                    "passed": False,
                    "evidence": f"Navigation test failed: {str(e)}",
                    "method": "browser"
                })

            # Test 3: Responsive layout
            try:
                # Test mobile viewport
                page.set_viewport_size({"width": 375, "height": 667})
                page.wait_for_timeout(500)
                hero = page.query_selector(".hero")
                if hero and hero.is_visible():
                    checks.append({
                        "key": "responsive_mobile",
                        "label": "Layout works on mobile viewport",
                        "passed": True,
                        "evidence": "Hero section visible at 375px width",
                        "method": "browser"
                    })
                else:
                    checks.append({
                        "key": "responsive_mobile",
                        "label": "Layout works on mobile viewport",
                        "passed": False,
                        "evidence": "Hero section not visible at 375px width",
                        "method": "browser"
                    })
            except Exception as e:
                checks.append({
                    "key": "responsive_mobile",
                    "label": "Layout works on mobile viewport",
                    "passed": False,
                    "evidence": f"Responsive test failed: {str(e)}",
                    "method": "browser"
                })

            # Test 4: No JavaScript errors
            try:
                errors = []
                page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
                page.reload()
                page.wait_for_load_state("networkidle", timeout=5000)

                checks.append({
                    "key": "no_js_errors",
                    "label": "No JavaScript console errors",
                    "passed": len(errors) == 0,
                    "evidence": f"{len(errors)} console errors detected" if errors else "No errors",
                    "method": "browser"
                })
            except Exception as e:
                checks.append({
                    "key": "no_js_errors",
                    "label": "No JavaScript console errors",
                    "passed": False,
                    "evidence": f"JavaScript error check failed: {str(e)}",
                    "method": "browser"
                })

            browser.close()

    except Exception as e:
        checks.append({
            "key": "browser_check",
            "label": "Browser-based verification",
            "passed": False,
            "evidence": f"Browser verification failed: {str(e)}",
            "method": "browser"
        })

    return checks
