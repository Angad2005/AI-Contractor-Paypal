import json
from pathlib import Path

from app.core.config import settings
from app.schemas.jobs import Contract
from app.services.llm_provider import LLMProviderError, complete_json, is_configured


CSS = """@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Space+Grotesk:wght@400;500;600;700&display=swap');
:root{--ink:#17201c;--muted:#68736d;--lime:#c7f36b;--paper:#f6f7f2;--line:#dce2db}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:'Space Grotesk',sans-serif}nav,main,footer{max-width:1180px;margin:auto}nav{height:84px;display:flex;align-items:center;justify-content:space-between;padding:0 28px}.brand{font-weight:700;letter-spacing:.08em;color:var(--ink);text-decoration:none}.brand span,footer span{color:#91b83c}.links{display:flex;gap:28px}.links a{color:var(--muted);text-decoration:none;font-size:14px}.hero{padding:100px 8% 82px;min-height:620px;background:radial-gradient(circle at 80% 10%,#e5f5bd,transparent 35%)}.eyebrow,.section-kicker{font-family:'DM Mono';font-size:12px;text-transform:uppercase;letter-spacing:.12em;color:#739034}.hero h1{max-width:760px;font-size:clamp(52px,8vw,100px);line-height:.94;letter-spacing:-.07em;margin:24px 0}.hero em,h2 em{font-style:normal;color:#7fa735}.lead{max-width:470px;color:var(--muted);font-size:18px;line-height:1.55}.button{display:inline-flex;gap:24px;align-items:center;border:0;background:var(--ink);color:white;padding:16px 21px;text-decoration:none;font:500 14px 'Space Grotesk';cursor:pointer}.proof{display:flex;gap:12px;align-items:baseline;margin-top:60px}.proof strong{font-size:24px}.proof span{color:var(--muted);font-size:13px}.section,.price-section,.signup{padding:100px 8%;border-top:1px solid var(--line)}h2{font-size:clamp(36px,5vw,64px);line-height:1;letter-spacing:-.055em;max-width:680px;margin:22px 0 54px}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.grid article{padding:30px;border:1px solid var(--line);min-height:220px}.grid b{font:12px 'DM Mono';color:#8eaa4c}.grid h3{margin-top:46px;font-size:22px}.grid p{color:var(--muted);line-height:1.5}.price-section{display:flex;justify-content:space-between;gap:40px;background:#e9f4d0}.price-card{background:var(--ink);color:white;padding:32px;min-width:300px;display:flex;flex-direction:column;gap:16px}.price-card span{font:12px 'DM Mono';color:var(--lime);text-transform:uppercase}.price-card strong{font-size:64px;letter-spacing:-.06em}.price-card small{color:#aab5ae;margin-bottom:18px}.price-card .button{background:var(--lime);color:var(--ink)}.signup{display:flex;justify-content:space-between;gap:30px}.signup h2{margin-bottom:0}.signup form{display:flex;flex-direction:column;justify-content:center;gap:12px;min-width:330px}.signup input{border:0;border-bottom:1px solid var(--ink);padding:14px 0;background:transparent;font:16px inherit;outline:0}.signup p{color:#779a32;font-size:13px}footer{padding:34px 8%;font:11px 'DM Mono';letter-spacing:.08em;color:var(--muted)}@media(max-width:700px){.links{display:none}.hero{padding-top:60px}.grid,.price-section,.signup{display:block}.grid article{margin-bottom:12px}.price-card{margin-top:28px}.signup form{margin-top:40px;min-width:0}}"""
JS = """document.querySelector('#signup-form').addEventListener('submit',(event)=>{event.preventDefault();const email=document.querySelector('#email');document.querySelector('#form-message').textContent=`Thanks — ${email.value} is on the list.`;email.value='';});"""


def _fallback_files(contract: Contract) -> dict[str, str]:
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Launchpad Studio</title><link rel="stylesheet" href="style.css"></head><body><nav><a class="brand" href="#top">LAUNCHPAD<span>•</span></a><div class="links"><a href="#features">Features</a><a href="#pricing">Pricing</a><a href="#signup">Get started</a></div></nav><main id="top"><section class="hero"><div class="eyebrow">AI-verified growth system</div><h1>Turn your next big idea into a <em>breakthrough.</em></h1><p class="lead">A conversion-ready launchpad for ambitious teams who want clarity, momentum, and measurable progress.</p><a class="button" href="#signup">Build your momentum <span>→</span></a><div class="proof"><strong>4.9/5</strong><span>from 2,000+ builders</span></div></section><section id="features" class="section"><div class="section-kicker">Why teams choose us</div><h2>Everything you need to move from maybe to momentum.</h2><div class="grid"><article><b>01</b><h3>Clarity first</h3><p>One sharp strategy replaces a dozen scattered ideas.</p></article><article><b>02</b><h3>Built to convert</h3><p>Thoughtful experiences turn attention into action.</p></article><article><b>03</b><h3>Always improving</h3><p>Feedback loops keep every release moving forward.</p></article></div></section><section id="pricing" class="price-section"><div><div class="section-kicker">One clear plan</div><h2>Serious momentum.<br><em>Simple price.</em></h2></div><div class="price-card"><span>Launchpad</span><strong>${contract.price:.2f}</strong><small>one-time project investment</small><a class="button" href="#signup">Start your project →</a></div></section><section id="signup" class="signup"><div><div class="section-kicker">Ready when you are</div><h2>Let’s make it<br><em>remarkable.</em></h2></div><form id="signup-form"><input id="email" type="email" placeholder="Your best email" required><button class="button" type="submit">Join the list →</button><p id="form-message" role="status"></p></form></section></main><footer>LAUNCHPAD STUDIO <span>·</span> Designed for the next move.</footer><script src="script.js"></script></body></html>'''
    return {"index.html": html, "style.css": CSS, "script.js": JS}


def _write_files(folder: Path, files: dict[str, str]) -> str:
    allowed = {"index.html", "style.css", "script.js"}
    if set(files) != allowed or not all(isinstance(value, str) and value.strip() for value in files.values()):
        raise ValueError("The deliverable must contain non-empty index.html, style.css, and script.js")
    for name, content in files.items():
        (folder / name).write_text(content, encoding="utf-8")
    return str(folder / "index.html")


def _ai_files(contract: Contract, prompt: str, repair_context: str = "") -> dict[str, str]:
    result = complete_json(
        """You are the deliverable engineer for a verified outcome-based contract.
Return only JSON with exactly three string fields: index.html, style.css, script.js.
Build a polished responsive landing page. The HTML must include anchors/sections for
all required sections, a pricing amount, a working email signup form, and navigation.
Do not use external JavaScript libraries.""",
        f"Brief:\n{prompt}\nApproved acceptance contract:\n{contract.model_dump_json()}\n{repair_context}",
    )
    return {key: result[key] for key in ("index.html", "style.css", "script.js")}


def generate_page(job_id: str, contract: Contract, prompt: str, repaired: bool = False) -> str:
    folder = Path(settings.generated_dir) / job_id
    folder.mkdir(parents=True, exist_ok=True)
    files = _fallback_files(contract)
    if is_configured():
        try:
            files = _ai_files(contract, prompt)
        except (LLMProviderError, KeyError, TypeError, ValueError):
            pass
    return _write_files(folder, files)


def repair_page(job_id: str, contract: Contract, prompt: str, failures: list[dict]) -> str:
    folder = Path(settings.generated_dir) / job_id
    context = "Failed independent checks:\n" + json.dumps(failures)
    try:
        files = _ai_files(contract, prompt, context)
    except (LLMProviderError, KeyError, TypeError, ValueError):
        files = _fallback_files(contract)
    return _write_files(folder, files)
