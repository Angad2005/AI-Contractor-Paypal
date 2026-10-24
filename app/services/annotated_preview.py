"""Build an isolated preview with the original generated styling and verification marks."""

import re
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup


def _asset_name(url: str) -> str:
    return Path(urlsplit(url).path).name


def _inline_generated_assets(soup: BeautifulSoup, html_path: str) -> None:
    """Inline styling for a read-only preview without exposing application scripts."""
    folder = Path(html_path).parent
    css_path = folder / "style.css"

    if css_path.is_file():
        css = re.sub(r"(?i)</style", r"<\/style", css_path.read_text(encoding="utf-8"))
        links = [
            link for link in soup.find_all("link", href=True)
            if _asset_name(link["href"]) == "style.css"
        ]
        for link in links:
            style = soup.new_tag("style")
            if link.get("media"):
                style["media"] = link["media"]
            style.string = css
            link.replace_with(style)
        if not links:
            style = soup.new_tag("style")
            style.string = css
            (soup.head or soup).append(style)

    # The preview shows the interface but leaves product behavior in the
    # payment-gated ZIP. Remove inline handlers as well as script elements.
    for script in soup.find_all("script"):
        script.decompose()
    for element in soup.find_all(True):
        for attribute in list(element.attrs):
            if attribute.lower().startswith("on"):
                del element[attribute]


def create_annotated_preview(html_path: str, verification_results: list[dict]) -> str:
    """Return a styled, read-only preview with status badges on checked elements."""
    path = Path(html_path)
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    _inline_generated_assets(soup, html_path)

    style = soup.new_tag("style")
    style.string = """
        .verify-pass,.verify-fail{position:relative!important}
        .verify-pass{border:2px solid #22c55e!important;box-shadow:0 0 0 4px #22c55e1f,0 14px 36px #22c55e1f!important}
        .verify-pass::after{content:'✓ PASS';position:absolute;top:10px;right:10px;background:#16a34a;color:#fff;padding:5px 9px;font:700 10px/1.2 system-ui,sans-serif;letter-spacing:.08em;border-radius:999px;z-index:1000}
        .verify-fail{border:2px solid #ef4444!important;box-shadow:0 0 0 4px #ef44441f,0 14px 36px #ef44441f!important}
        .verify-fail::after{content:'✗ FAIL';position:absolute;top:10px;right:10px;background:#ef4444;color:#fff;padding:5px 9px;font:700 10px/1.2 system-ui,sans-serif;letter-spacing:.08em;border-radius:999px;z-index:1000}
        .verify-legend{position:fixed;right:20px;bottom:20px;z-index:10000;min-width:190px;padding:16px 18px;color:#f8fafc;background:rgba(15,23,42,.94);border:1px solid rgba(255,255,255,.16);border-radius:14px;box-shadow:0 18px 48px rgba(2,6,23,.26);backdrop-filter:blur(14px);font:13px/1.5 system-ui,-apple-system,sans-serif}
        .verify-legend strong{display:block;margin-bottom:8px;font-size:13px}
        .verify-legend-item{display:flex;align-items:center;gap:8px;margin:4px 0}
        .verify-legend-color{width:9px;height:9px;border-radius:50%;flex:0 0 auto}
        .verify-legend-pass{background:#22c55e}.verify-legend-fail{background:#ef4444}.verify-legend-skip{background:#94a3b8}
        @media(max-width:600px){.verify-legend{right:12px;bottom:12px;min-width:0;padding:12px 14px;font-size:12px}}
        @media(prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:.01ms!important;transition-duration:.01ms!important;scroll-behavior:auto!important}}
    """
    if soup.head:
        soup.head.append(style)
    else:
        head = soup.new_tag("head")
        head.append(style)
        soup.insert(0, head)

    paywall_note = soup.new_tag(
        "div",
        attrs={"class": "preview-paywall-note", "role": "note"},
    )
    paywall_note.string = "READ-ONLY PRODUCT PREVIEW · SOURCE PACKAGE UNLOCKS AFTER VERIFIED PAYMENT"
    paywall_note_style = soup.new_tag("style")
    paywall_note_style.string = """
        .preview-paywall-note{position:sticky;top:0;z-index:9999;padding:9px 16px;text-align:center;
          color:#ecfdf5;background:#0f172a;border-bottom:1px solid #ffffff2b;
          font:700 10px/1.4 system-ui,-apple-system,sans-serif;letter-spacing:.12em}
        .preview-paywall-note~* button,.preview-paywall-note~* input,
        .preview-paywall-note~* select,.preview-paywall-note~* textarea{pointer-events:none!important}
        @media(max-width:600px){.preview-paywall-note{font-size:9px;letter-spacing:.07em}}
    """
    (soup.head or soup).append(paywall_note_style)
    body = soup.body or soup
    body["inert"] = ""
    body.insert(0, paywall_note)

    passed = sum(1 for result in verification_results if result.get("passed"))
    failed = sum(
        1 for result in verification_results
        if not result.get("passed") and not result.get("skipped")
    )
    skipped = sum(1 for result in verification_results if result.get("skipped"))
    legend = soup.new_tag("aside", attrs={"class": "verify-legend", "aria-label": "Verification summary"})
    legend.append(BeautifulSoup(
        f"<strong>Verification · {passed} passed</strong>"
        f'<div class="verify-legend-item"><i class="verify-legend-color verify-legend-pass"></i><span>{passed} checks passed</span></div>'
        f'<div class="verify-legend-item"><i class="verify-legend-color verify-legend-fail"></i><span>{failed} checks failed</span></div>'
        f'<div class="verify-legend-item"><i class="verify-legend-color verify-legend-skip"></i><span>{skipped} checks skipped</span></div>',
        "html.parser",
    ))
    (soup.body or soup).append(legend)

    selector_map = {
        "hero": ".hero",
        "features": "#features .grid",
        "pricing": "#pricing .price-card",
        "signup": "#signup-form",
        "responsive": 'meta[name="viewport"]',
        "navigation": "nav",
        "semantic": "main",
    }
    for result in verification_results:
        key = result.get("key")
        element = soup.find(attrs={"data-acceptance-key": key})
        if element is None and key in selector_map:
            element = soup.select_one(selector_map[key])
        if element:
            css_class = "verify-pass" if result.get("passed") else "verify-fail"
            existing = element.get("class", [])
            if isinstance(existing, str):
                existing = existing.split()
            element["class"] = existing + [css_class]

    annotated_path = path.with_name(path.stem + "_annotated.html")
    annotated_path.write_text(str(soup), encoding="utf-8")
    return str(annotated_path)
