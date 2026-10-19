"""
Create annotated preview with visual verification feedback.

This module adds visual annotations (green/red borders) to the generated page
to show which elements passed or failed verification.
"""

from bs4 import BeautifulSoup
from pathlib import Path


def create_annotated_preview(html_path: str, verification_results: list[dict]) -> str:
    """
    Add visual annotations to the generated page showing verification results.

    Args:
        html_path: Path to the generated HTML file
        verification_results: List of verification results

    Returns:
        Path to the annotated HTML file
    """
    with open(html_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')

    # Add annotation styles
    style = soup.new_tag('style')
    style.string = """
        .verify-pass {
            border: 3px solid #4ade80 !important;
            position: relative;
            box-shadow: 0 0 10px rgba(74, 222, 128, 0.3);
        }
        .verify-pass::after {
            content: '✓ PASS';
            position: absolute;
            top: -20px;
            right: 0;
            background: #4ade80;
            color: white;
            padding: 2px 8px;
            font-size: 12px;
            font-weight: bold;
            border-radius: 2px;
            z-index: 1000;
        }
        .verify-fail {
            border: 3px solid #ef4444 !important;
            position: relative;
            box-shadow: 0 0 10px rgba(239, 68, 68, 0.3);
        }
        .verify-fail::after {
            content: '✗ FAIL';
            position: absolute;
            top: -20px;
            right: 0;
            background: #ef4444;
            color: white;
            padding: 2px 8px;
            font-size: 12px;
            font-weight: bold;
            border-radius: 2px;
            z-index: 1000;
        }
        .verify-legend {
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: white;
            padding: 15px;
            border: 2px solid #e5e7eb;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            z-index: 10000;
            font-family: system-ui, -apple-system, sans-serif;
            font-size: 13px;
        }
        .verify-legend strong {
            display: block;
            margin-bottom: 8px;
        }
        .verify-legend-item {
            display: flex;
            align-items: center;
            gap: 8px;
            margin: 4px 0;
        }
        .verify-legend-color {
            width: 16px;
            height: 16px;
            border-radius: 2px;
        }
        .verify-legend-pass {
            background: #4ade80;
        }
        .verify-legend-fail {
            background: #ef4444;
        }
    """
    if soup.head:
        soup.head.append(style)
    else:
        head = soup.new_tag('head')
        head.append(style)
        soup.insert(0, head)

    # Add legend
    legend = soup.new_tag('div', attrs={'class': 'verify-legend'})
    legend_content = """
        <strong>Verification Legend:</strong>
        <div class="verify-legend-item">
            <div class="verify-legend-color verify-legend-pass"></div>
            <span>Green border = PASS</span>
        </div>
        <div class="verify-legend-item">
            <div class="verify-legend-color verify-legend-fail"></div>
            <span>Red border = FAIL</span>
        </div>
    """
    legend.append(BeautifulSoup(legend_content, 'html.parser'))

    if soup.body:
        soup.body.append(legend)
    else:
        body = soup.new_tag('body')
        body.append(legend)
        soup.append(body)

    # Annotate elements based on verification results
    selector_map = {
        "hero": ".hero",
        "features": "#features .grid",
        "pricing": "#pricing .price-card",
        "signup": "#signup-form",
        "responsive": 'meta[name="viewport"]',
        "navigation": "nav",
        "semantic": "main"
    }

    for result in verification_results:
        key = result.get("key")
        if key in selector_map:
            selector = selector_map[key]
            element = soup.select_one(selector)
            if element:
                css_class = 'verify-pass' if result.get("passed") else 'verify-fail'
                existing_classes = element.get("class", [])
                if isinstance(existing_classes, str):
                    existing_classes = existing_classes.split()
                element["class"] = existing_classes + [css_class]

    # Save annotated version
    annotated_path = html_path.replace('.html', '_annotated.html')
    with open(annotated_path, 'w', encoding='utf-8') as f:
        f.write(str(soup))

    return annotated_path
