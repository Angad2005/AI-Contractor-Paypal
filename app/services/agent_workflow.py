"""
Agentic workflow for AI Contractor using LangChain and LangGraph.

This module replaces fragile monolithic JSON generation with specialized,
collaborative agents:
1. Lead Frontend Architect Agent: Generates semantic HTML with criteria markers.
2. Senior UI/UX Stylist Agent: Generates responsive CSS with modern layout and motion accessibility.
3. Senior Client-side Engineer Agent: Generates interactive JavaScript logic.
4. Assembler: Combines and validates deliverables.
5. Repair Agent: Surgically fixes acceptance check failures during verification.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from app.core.config import settings
from app.schemas.jobs import Contract, Criterion

logger = logging.getLogger(__name__)


def get_chat_model() -> ChatOpenAI:
    """Instantiate a ChatOpenAI client connected to the configured OpenAI-compatible LLM endpoint."""
    model_name = settings.llm_model or "nvidia/nemotron-3.5-bolt-e4b"
    return ChatOpenAI(
        model=model_name,
        base_url=settings.llm_base_url.rstrip("/"),
        api_key=settings.llm_api_key or "no-key-required",
        temperature=0.2,
        timeout=getattr(settings, "llm_timeout_seconds", 180.0),
    )


def extract_code_block(text: str, languages: List[str]) -> str:
    """Extract code from markdown fenced blocks or raw text cleanly without JSON escaping issues."""
    if not text:
        return ""
    cleaned = text.strip()
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()

    for lang in languages:
        match = re.search(rf"```{lang}\s*\n?(.*?)```", cleaned, flags=re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()

    generic_match = re.search(r"```(?:[a-zA-Z0-9_-]+)?\s*\n?(.*?)```", cleaned, flags=re.DOTALL)
    if generic_match:
        return generic_match.group(1).strip()

    return cleaned


class ContractorState(TypedDict):
    prompt: str
    criteria_text: str
    html: Optional[str]
    css: Optional[str]
    js: Optional[str]
    repair_context: Optional[str]
    files: Optional[Dict[str, str]]
    error: Optional[str]


def architect_node(state: ContractorState) -> Dict[str, Any]:
    """Architect Agent: Generates semantic, accessible HTML with embedded criteria markers."""
    llm = get_chat_model()
    system_prompt = (
        "You are the Lead Frontend Architect for an AI software contractor.\n"
        "Your task is to write ONLY the semantic HTML (index.html) for a browser-based application.\n"
        "Requirements:\n"
        "1. Write complete, valid HTML5 with <!doctype html>, <head>, <title>, and <body>.\n"
        "2. Include `<link rel=\"stylesheet\" href=\"style.css\">` in <head> and `<script src=\"script.js\" defer></script>` in <body>.\n"
        "3. CRITICAL: For EVERY acceptance criterion listed below, you MUST add the attribute:\n"
        "   `data-acceptance-key=\"<criterion_key>\"` to the primary visible element that satisfies that criterion.\n"
        "4. Create all needed UI containers, buttons, inputs, navigation, and semantic sections.\n"
        "5. Output ONLY the complete HTML inside a ```html ... ``` block. Do not return JSON."
    )
    user_prompt = (
        f"Customer Brief:\n{state['prompt']}\n\n"
        f"Approved Acceptance Criteria:\n{state['criteria_text']}\n\n"
        "Write the complete index.html:"
    )

    try:
        response = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
        html = extract_code_block(response.content, ["html", "xml"])
        return {"html": html}
    except Exception as exc:
        logger.warning("Architect agent failed: %s", exc)
        return {"error": str(exc)}


def stylist_node(state: ContractorState) -> Dict[str, Any]:
    """Stylist Agent: Generates modern, responsive CSS with typography, layouts, and motion accessibility."""
    llm = get_chat_model()
    html_context = state.get("html") or ""
    system_prompt = (
        "You are the Lead UI/UX Designer and CSS Engineer.\n"
        "Your task is to write ONLY the complete CSS stylesheet (style.css) for the application.\n"
        "Requirements:\n"
        "1. Style all elements, classes, and IDs defined in the provided HTML.\n"
        "2. Use modern CSS custom properties (variables) on `:root` for colors, spacing, and fonts.\n"
        "3. Implement responsive layouts using CSS Grid and Flexbox.\n"
        "4. Include mobile responsive media queries (`@media (max-width: 768px)`).\n"
        "5. Include `@media (prefers-reduced-motion: reduce)` rules for accessibility.\n"
        "6. Do not import external fonts or remote stylesheets. Use system font stacks.\n"
        "7. Output ONLY the complete CSS inside a ```css ... ``` block. Do not return JSON."
    )
    user_prompt = (
        f"Customer Brief:\n{state['prompt']}\n\n"
        f"HTML Structure:\n{html_context[:4000]}\n\n"
        "Write the complete style.css:"
    )

    try:
        response = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
        css = extract_code_block(response.content, ["css"])
        return {"css": css}
    except Exception as exc:
        logger.warning("Stylist agent failed: %s", exc)
        return {"css": "/* Default fallback styles */\nbody { font-family: sans-serif; margin: 0; padding: 20px; }"}


def engineer_node(state: ContractorState) -> Dict[str, Any]:
    """Engineer Agent: Generates client-side JavaScript for interactivity, forms, and state management."""
    llm = get_chat_model()
    html_context = state.get("html") or ""
    system_prompt = (
        "You are the Senior Client-side Engineer.\n"
        "Your task is to write ONLY the client-side JavaScript (script.js) for the application.\n"
        "Requirements:\n"
        "1. Implement all user workflows, buttons, form submissions, filters, modals, and counters.\n"
        "2. Maintain state in memory. Make no backend or remote network calls.\n"
        "3. Use vanilla JavaScript wrapped in an IIFE: `(function() { 'use strict'; ... })();`.\n"
        "4. Attach event listeners cleanly after DOMContentLoaded or defer.\n"
        "5. Prevent default form submission and display clear, visible user feedback on actions.\n"
        "6. Ensure no uncaught runtime exceptions or console errors.\n"
        "7. Output ONLY the complete JavaScript inside a ```javascript ... ``` block. Do not return JSON."
    )
    user_prompt = (
        f"Customer Brief:\n{state['prompt']}\n\n"
        f"Acceptance Criteria:\n{state['criteria_text']}\n\n"
        f"HTML Structure:\n{html_context[:4000]}\n\n"
        "Write the complete script.js:"
    )

    try:
        response = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
        js = extract_code_block(response.content, ["javascript", "js"])
        return {"js": js}
    except Exception as exc:
        logger.warning("Engineer agent failed: %s", exc)
        return {"js": "// Client script\ndocument.addEventListener('DOMContentLoaded', function() {});"}


def repair_node(state: ContractorState) -> Dict[str, Any]:
    """Repair Agent: Surgically fixes deliverable files based on verification failures."""
    llm = get_chat_model()
    system_prompt = (
        "You are the Quality Assurance & Repair Specialist for an AI software contractor.\n"
        "The previous deliverable failed independent automated acceptance checks.\n"
        "Analyze the failures and return the corrected files.\n"
        "CRITICAL REQUIREMENT:\n"
        "If a check failed with 'No element marked data-acceptance-key=KEY', add `data-acceptance-key=\"KEY\"`\n"
        "to the corresponding element in the HTML.\n"
        "Output the corrected files in markdown blocks:\n"
        "```html\n<index.html content>\n```\n"
        "```css\n<style.css content>\n```\n"
        "```javascript\n<script.js content>\n```"
    )
    user_prompt = (
        f"Customer Brief:\n{state['prompt']}\n\n"
        f"Acceptance Criteria:\n{state['criteria_text']}\n\n"
        f"Verification Failures:\n{state.get('repair_context', '')}\n\n"
        f"Current index.html:\n{state.get('html', '')[:3000]}\n\n"
        f"Current style.css:\n{state.get('css', '')[:2000]}\n\n"
        f"Current script.js:\n{state.get('js', '')[:2000]}\n\n"
        "Return the repaired files in their respective markdown code blocks:"
    )

    try:
        response = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
        content = response.content
        html = extract_code_block(content, ["html", "xml"]) or state.get("html") or ""
        css = extract_code_block(content, ["css"]) or state.get("css") or ""
        js = extract_code_block(content, ["javascript", "js"]) or state.get("js") or ""
        return {"html": html, "css": css, "js": js}
    except Exception as exc:
        logger.warning("Repair agent failed: %s", exc)
        return {"html": state.get("html"), "css": state.get("css"), "js": state.get("js")}


def assemble_node(state: ContractorState) -> Dict[str, Any]:
    """Assembler Node: Combines the generated HTML, CSS, and JS files into the final dictionary."""
    html = (state.get("html") or "").strip()
    css = (state.get("css") or "").strip()
    js = (state.get("js") or "").strip()

    if not html:
        html = "<!doctype html><html><head><title>App</title><link rel=\"stylesheet\" href=\"style.css\"></head><body><main><h1>App</h1></main><script src=\"script.js\" defer></script></body></html>"
    if not css:
        css = "body { margin: 0; font-family: sans-serif; }"
    if not js:
        js = "(function() { console.log('Ready'); })();"

    return {"files": {"index.html": html, "style.css": css, "script.js": js}}


def build_contractor_graph() -> StateGraph:
    """Build the LangGraph StateGraph connecting the specialist agents."""
    graph = StateGraph(ContractorState)

    graph.add_node("architect", architect_node)
    graph.add_node("stylist", stylist_node)
    graph.add_node("engineer", engineer_node)
    graph.add_node("repair", repair_node)
    graph.add_node("assembler", assemble_node)

    # Route: initial generation runs architect -> then parallel stylist & engineer -> assemble
    graph.add_edge("architect", "stylist")
    graph.add_edge("architect", "engineer")
    graph.add_edge("stylist", "assembler")
    graph.add_edge("engineer", "assembler")
    graph.add_edge("repair", "assembler")
    graph.add_edge("assembler", END)

    return graph


def run_agentic_workflow(
    contract: Contract,
    prompt: str,
    repair_context: str = "",
    current_files: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Execute the multi-agent software contractor workflow using LangGraph."""
    criteria_lines = [
        f"- key: '{c.key}', label: '{c.label}', detail: '{c.detail}'"
        for c in (contract.criteria or [])
    ]
    criteria_text = "\n".join(criteria_lines)

    initial_state: ContractorState = {
        "prompt": prompt,
        "criteria_text": criteria_text,
        "html": (current_files or {}).get("index.html"),
        "css": (current_files or {}).get("style.css"),
        "js": (current_files or {}).get("script.js"),
        "repair_context": repair_context,
        "files": None,
        "error": None,
    }

    graph = build_contractor_graph()

    if repair_context and current_files:
        graph.set_entry_point("repair")
    else:
        graph.set_entry_point("architect")

    app = graph.compile()
    final_state = app.invoke(initial_state)

    files = final_state.get("files")
    if not files or not all(files.get(k) for k in ("index.html", "style.css", "script.js")):
        raise ValueError("Agentic workflow produced incomplete deliverables")

    return files


def run_contract_analyst_agent(prompt: str, budget: float) -> Dict[str, Any]:
    """Contract Analyst Agent: Analyzes the brief using LangChain to generate structured criteria."""
    llm = get_chat_model()
    system_prompt = (
        "You are the Lead Contract Analyst for an outcome-based AI software contractor.\n"
        "Return ONLY a valid JSON object with:\n"
        "- required_sections: array of screen or section names\n"
        "- required_features: array of product capabilities\n"
        "- criteria: array of objects with key, label, detail, required\n"
        "Write 4-10 concrete, independently verifiable criteria for a browser-based application.\n"
        "Use short lowercase snake_case keys (e.g. hero_section, product_grid, contact_form).\n"
        "Do not wrap in markdown or backticks."
    )
    user_prompt = f"Customer Brief:\n{prompt}\nApproved contractor budget: {budget:.2f} USD"

    response = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
    content = response.content.strip()

    from app.services.llm_provider import _extract_json
    return _extract_json(content)
