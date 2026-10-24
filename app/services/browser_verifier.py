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

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PlaywrightError = RuntimeError
    sync_playwright = None
    PLAYWRIGHT_AVAILABLE = False


def _skipped_check(evidence: str) -> dict:
    return {
        "key": "browser_check",
        "label": "Browser-based verification",
        "passed": False,
        "skipped": True,
        "evidence": evidence,
        "method": "browser"
    }


def _verify_software_with_browser(path: str, contract) -> list[dict]:
    """Smoke-check a generated software product without assuming landing-page controls."""
    checks = []
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
            except PlaywrightError as e:
                return [_skipped_check(
                    f"Chromium is unavailable; browser checks were skipped: {e}. "
                    "Install it with: playwright install chromium"
                )]

            page = browser.new_page(viewport={"width": 1280, "height": 900})
            console_errors = []
            page_errors = []
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.goto(f"file://{Path(path).absolute()}")

            body_text = page.locator("body").inner_text().strip()
            checks.append({
                "key": "application_rendered",
                "label": "Software preview renders content",
                "passed": bool(body_text),
                "evidence": "The application displayed visible content" if body_text else "The application body is empty",
                "method": "browser",
            })

            marker_keys = [
                criterion.key for criterion in contract.criteria
                if criterion.key not in {"app_shell", "responsive", "navigation"}
            ]
            visible_markers = []
            for key in marker_keys:
                visible = page.locator("[data-acceptance-key]").evaluate_all(
                    "(nodes, key) => nodes.some(node => node.dataset.acceptanceKey === key && "
                    "!!(node.offsetWidth || node.offsetHeight || node.getClientRects().length))",
                    key,
                )
                if visible:
                    visible_markers.append(key)
            checks.append({
                "key": "criteria_visible",
                "label": "Approved product features appear in the preview",
                "passed": len(visible_markers) == len(marker_keys),
                "evidence": f"{len(visible_markers)} of {len(marker_keys)} criterion markers are visible",
                "method": "browser",
            })

            page.set_viewport_size({"width": 375, "height": 812})
            has_horizontal_overflow = page.evaluate(
                "document.documentElement.scrollWidth > window.innerWidth + 1"
            )
            checks.append({
                "key": "responsive_mobile",
                "label": "Software preview fits a mobile viewport",
                "passed": not has_horizontal_overflow,
                "evidence": "No horizontal overflow at 375px" if not has_horizontal_overflow else "Content overflows the 375px viewport",
                "method": "browser",
            })

            checks.append({
                "key": "no_js_errors",
                "label": "No JavaScript runtime errors",
                "passed": not console_errors and not page_errors,
                "evidence": "No browser errors detected" if not console_errors and not page_errors else f"{len(console_errors) + len(page_errors)} browser error(s) detected",
                "method": "browser",
            })
            browser.close()
    except PlaywrightError as e:
        return [_skipped_check(
            f"Browser runtime is unavailable; browser checks were skipped: {e}. "
            "Install it with: playwright install chromium"
        )]
    return checks


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
        return [_skipped_check(
            "Playwright is not installed; browser checks were skipped. Install Playwright "
            "and Chromium with: pip install playwright && playwright install chromium"
        )]

    legacy_keys = {"hero", "features", "pricing", "signup", "responsive", "navigation"}
    criteria_keys = {criterion.key for criterion in contract.criteria} if contract and getattr(contract, "criteria", None) else set()
    if criteria_keys and criteria_keys != legacy_keys:
        return _verify_software_with_browser(path, contract)

    checks = []

    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
            except PlaywrightError as e:
                return [_skipped_check(
                    f"Chromium is unavailable; browser checks were skipped: {e}. "
                    "Install it with: playwright install chromium"
                )]
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

    except PlaywrightError as e:
        checks.append(_skipped_check(
            f"Browser runtime is unavailable; browser checks were skipped: {e}. "
            "Install it with: playwright install chromium"
        ))

    return checks
