import json
import logging
from pathlib import Path
from bs4 import BeautifulSoup

from app.core.config import settings
from app.schemas.jobs import Contract
from app.services.llm_provider import complete_json, is_demo_mode

logger = logging.getLogger(__name__)


CSS = """@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Space+Grotesk:wght@400;500;600;700&display=swap');
:root{--ink:#17201c;--muted:#68736d;--lime:#c7f36b;--paper:#f6f7f2;--line:#dce2db}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:'Space Grotesk',sans-serif}nav,main,footer{max-width:1180px;margin:auto}nav{height:84px;display:flex;align-items:center;justify-content:space-between;padding:0 28px}.brand{font-weight:700;letter-spacing:.08em;color:var(--ink);text-decoration:none}.brand span,footer span{color:#91b83c}.links{display:flex;gap:28px}.links a{color:var(--muted);text-decoration:none;font-size:14px}.hero{padding:100px 8% 82px;min-height:620px;background:radial-gradient(circle at 80% 10%,#e5f5bd,transparent 35%)}.eyebrow,.section-kicker{font-family:'DM Mono';font-size:12px;text-transform:uppercase;letter-spacing:.12em;color:#739034}.hero h1{max-width:760px;font-size:clamp(52px,8vw,100px);line-height:.94;letter-spacing:-.07em;margin:24px 0}.hero em,h2 em{font-style:normal;color:#7fa735}.lead{max-width:470px;color:var(--muted);font-size:18px;line-height:1.55}.button{display:inline-flex;gap:24px;align-items:center;border:0;background:var(--ink);color:white;padding:16px 21px;text-decoration:none;font:500 14px 'Space Grotesk';cursor:pointer}.proof{display:flex;gap:12px;align-items:baseline;margin-top:60px}.proof strong{font-size:24px}.proof span{color:var(--muted);font-size:13px}.section,.price-section,.signup{padding:100px 8%;border-top:1px solid var(--line)}h2{font-size:clamp(36px,5vw,64px);line-height:1;letter-spacing:-.055em;max-width:680px;margin:22px 0 54px}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.grid article{padding:30px;border:1px solid var(--line);min-height:220px}.grid b{font:12px 'DM Mono';color:#8eaa4c}.grid h3{margin-top:46px;font-size:22px}.grid p{color:var(--muted);line-height:1.5}.price-section{display:flex;justify-content:space-between;gap:40px;background:#e9f4d0}.price-card{background:var(--ink);color:white;padding:32px;min-width:300px;display:flex;flex-direction:column;gap:16px}.price-card span{font:12px 'DM Mono';color:var(--lime);text-transform:uppercase}.price-card strong{font-size:64px;letter-spacing:-.06em}.price-card small{color:#aab5ae;margin-bottom:18px}.price-card .button{background:var(--lime);color:var(--ink)}.signup{display:flex;justify-content:space-between;gap:30px}.signup h2{margin-bottom:0}.signup form{display:flex;flex-direction:column;justify-content:center;gap:12px;min-width:330px}.signup input{border:0;border-bottom:1px solid var(--ink);padding:14px 0;background:transparent;font:16px inherit;outline:0}.signup p{color:#779a32;font-size:13px}footer{padding:34px 8%;font:11px 'DM Mono';letter-spacing:.08em;color:var(--muted)}@media(max-width:700px){.links{display:none}.hero{padding-top:60px}.grid,.price-section,.signup{display:block}.grid article{margin-bottom:12px}.price-card{margin-top:28px}.signup form{margin-top:40px;min-width:0}}"""
MOTION_CSS = """
html{scroll-behavior:smooth}
.hero .eyebrow,.hero h1,.hero .lead,.hero .button,.hero .proof{animation:rise-in .72s cubic-bezier(.2,.75,.25,1) both}
.hero h1{animation-delay:.08s}.hero .lead{animation-delay:.16s}.hero .button{animation-delay:.24s}.hero .proof{animation-delay:.32s}
.links a,.button,.grid article,.price-card{transition:color .22s ease,background-color .22s ease,border-color .22s ease,box-shadow .22s ease,transform .22s ease}
.reveal{opacity:0;transform:translateY(18px);transition:opacity .7s cubic-bezier(.2,.75,.25,1),transform .7s cubic-bezier(.2,.75,.25,1)}.reveal.is-visible{opacity:1;transform:translateY(0)}
.links a:hover{color:var(--ink)}
.button:hover{transform:translateY(-3px);box-shadow:0 12px 28px #17201c24}
.grid article{animation:rise-in .7s cubic-bezier(.2,.75,.25,1) both}.grid article:nth-child(2){animation-delay:.08s}.grid article:nth-child(3){animation-delay:.16s}
.grid article:hover{transform:translateY(-6px);border-color:#a9c66c;box-shadow:0 18px 38px #17201c12}
.price-card:hover{transform:translateY(-5px);box-shadow:0 22px 44px #17201c24}
.signup input:focus{border-color:#7fa735;box-shadow:0 2px 0 #7fa735}
.button:focus-visible,.links a:focus-visible,.brand:focus-visible,.signup input:focus-visible{outline:3px solid #7fa735;outline-offset:4px}
@keyframes rise-in{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:translateY(0)}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}*,*::before,*::after{animation-duration:.01ms!important;animation-iteration-count:1!important;scroll-behavior:auto!important;transition-duration:.01ms!important}}
"""
JS = """(function(){
  var form=document.querySelector('#signup-form');
  if(form){form.addEventListener('submit',function(event){event.preventDefault();var email=document.querySelector('#email');var message=document.querySelector('#form-message');message.textContent='Thanks — '+email.value+' is on the list.';email.value='';});}
  if(!('IntersectionObserver' in window)||window.matchMedia('(prefers-reduced-motion: reduce)').matches)return;
  var targets=document.querySelectorAll('.section,.price-section,.signup,.grid article');
  targets.forEach(function(element){element.classList.add('reveal');});
  var observer=new IntersectionObserver(function(entries){entries.forEach(function(entry){if(entry.isIntersecting){entry.target.classList.add('is-visible');observer.unobserve(entry.target);}});},{threshold:.12});
  targets.forEach(function(element){observer.observe(element);});
})();"""


def _fallback_files(contract: Contract) -> dict[str, str]:
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Launchpad Studio</title><link rel="stylesheet" href="style.css"></head><body><nav><a class="brand" href="#top">LAUNCHPAD<span>•</span></a><div class="links"><a href="#features">Features</a><a href="#pricing">Pricing</a><a href="#signup">Get started</a></div></nav><main id="top"><section class="hero"><div class="eyebrow">AI-verified growth system</div><h1>Turn your next big idea into a <em>breakthrough.</em></h1><p class="lead">A conversion-ready launchpad for ambitious teams who want clarity, momentum, and measurable progress.</p><a class="button" href="#signup">Build your momentum <span>→</span></a><div class="proof"><strong>4.9/5</strong><span>from 2,000+ builders</span></div></section><section id="features" class="section"><div class="section-kicker">Why teams choose us</div><h2>Everything you need to move from maybe to momentum.</h2><div class="grid"><article><b>01</b><h3>Clarity first</h3><p>One sharp strategy replaces a dozen scattered ideas.</p></article><article><b>02</b><h3>Built to convert</h3><p>Thoughtful experiences turn attention into action.</p></article><article><b>03</b><h3>Always improving</h3><p>Feedback loops keep every release moving forward.</p></article></div></section><section id="pricing" class="price-section"><div><div class="section-kicker">One clear plan</div><h2>Serious momentum.<br><em>Simple price.</em></h2></div><div class="price-card"><span>Launchpad</span><strong>${contract.price:.2f}</strong><small>one-time project investment</small><a class="button" href="#signup">Start your project →</a></div></section><section id="signup" class="signup"><div><div class="section-kicker">Ready when you are</div><h2>Let’s make it<br><em>remarkable.</em></h2></div><form id="signup-form"><input id="email" type="email" placeholder="Your best email" required><button class="button" type="submit">Join the list →</button><p id="form-message" role="status"></p></form></section></main><footer>LAUNCHPAD STUDIO <span>·</span> Designed for the next move.</footer><script src="script.js"></script></body></html>'''
    return {"index.html": html, "style.css": CSS + MOTION_CSS, "script.js": JS}


def _write_files(folder: Path, files: dict[str, str]) -> str:
    allowed = {"index.html", "style.css", "script.js"}
    if set(files) != allowed or not all(isinstance(value, str) and value.strip() for value in files.values()):
        raise ValueError("The deliverable must contain non-empty index.html, style.css, and script.js")
    soup = BeautifulSoup(files["index.html"], "html.parser")
    if soup.head is None:
        head = soup.new_tag("head")
        if soup.html:
            soup.html.insert(0, head)
        else:
            html = soup.new_tag("html")
            html.append(head)
            for child in list(soup.contents):
                html.append(child.extract())
            soup.append(html)
    css_links = [
        link for link in soup.find_all("link", href=True)
        if "stylesheet" in link.get("rel", [])
        and Path(link.get("href", "").split("?", 1)[0].split("#", 1)[0]).name == "style.css"
    ]
    css_linked = bool(css_links)
    for link in css_links:
        link["href"] = "style.css"
    if not css_linked:
        style_link = soup.new_tag("link", rel="stylesheet", href="style.css")
        soup.head.append(style_link)
    script_links = [
        script for script in soup.find_all("script", src=True)
        if Path(script.get("src", "").split("?", 1)[0].split("#", 1)[0]).name == "script.js"
    ]
    script_linked = bool(script_links)
    for script in script_links:
        script["src"] = "script.js"
        script["defer"] = True
    if not script_linked:
        script = soup.new_tag("script", src="script.js", defer=True)
        (soup.body or soup).append(script)
    has_doctype = any(str(node).lower().startswith("<!doctype") for node in soup.contents)
    files["index.html"] = ("" if has_doctype else "<!doctype html>\n") + str(soup)
    for name, content in files.items():
        (folder / name).write_text(content, encoding="utf-8")
    return str(folder / "index.html")


def _ai_files(
    contract: Contract,
    prompt: str,
    repair_context: str = "",
    current_files: dict[str, str] | None = None,
) -> dict[str, str]:
    # First priority: execute the LangChain and LangGraph agentic workflow
    try:
        from app.services.agent_workflow import run_agentic_workflow
        return run_agentic_workflow(contract, prompt, repair_context, current_files)
    except Exception as exc:
        logger.warning(
            "Agentic workflow encountered: %s. Falling back to direct generator with escape sanitation.",
            exc,
        )

    # Fallback: direct complete_json with escape sanitization in _extract_json
    result = complete_json(
        """You are the software engineer for a verified outcome-based contract.
Return only JSON with exactly three non-empty string fields: index.html, style.css,
script.js. Build the actual browser-based software product requested in the customer
brief, not a generic marketing page or an unrelated template. Implement its central
user workflow with working controls and meaningful client-side behavior. Use the
approved criteria as the product requirements. Add data-acceptance-key="<criterion key>"
to the primary visible element that demonstrates each criterion. Make the application
responsive and accessible, and include a clear product name and useful empty state.
Keep all product UI and behavior in these three files. The product must run as a static
browser application: use vanilla HTML/CSS/JavaScript, keep state in memory, make no
network requests, use no backend, avoid external scripts, and do not require remote
images or fonts. The approved contractor budget is not the product's selling price;
show a price only if the customer brief explicitly requests one. Return full CSS and
working JavaScript, and ensure the HTML links to style.css and script.js. Respect
prefers-reduced-motion and never hide essential content when JavaScript is unavailable.""",
        f"Brief:\n{prompt}\nApproved acceptance contract:\n{contract.model_dump_json()}\n{repair_context}",
    )
    return {key: result[key] for key in ("index.html", "style.css", "script.js")}


def generate_page(job_id: str, contract: Contract, prompt: str, repaired: bool = False) -> str:
    folder = Path(settings.generated_dir) / job_id
    folder.mkdir(parents=True, exist_ok=True)
    files = _fallback_files(contract) if is_demo_mode() else _ai_files(contract, prompt)
    return _write_files(folder, files)


def repair_page(job_id: str, contract: Contract, prompt: str, failures: list[dict]) -> str:
    folder = Path(settings.generated_dir) / job_id
    current_files = {}
    for name in ("index.html", "style.css", "script.js"):
        p = folder / name
        if p.is_file():
            current_files[name] = p.read_text(encoding="utf-8")
    context = "Failed independent checks:\n" + json.dumps(failures)
    files = (
        _fallback_files(contract)
        if is_demo_mode()
        else _ai_files(contract, prompt, context, current_files)
    )
    return _write_files(folder, files)
