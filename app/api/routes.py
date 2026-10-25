import uuid
import hmac
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from urllib.parse import urlencode
from app.core.config import settings
from app.db.database import get_db
from app.db.models import AppSetting, Job, Payment, VerificationRun, GenerationVersion
from app.schemas.jobs import ApproveSpec, Contract, JobCreate, PaymentAction
from app.services.contract_generator import make_contract
from app.services.page_generator import generate_page, repair_page
from app.services.verifier import verify_page
from app.services.verifier_enhanced import verify_page_enhanced
from app.services.annotated_preview import create_annotated_preview
from app.services.browser_verifier import verify_with_browser
from app.services.artifact_service import make_zip
from app.services.project_generator import generate_source_project, verify_source_project
from app.services.paypal_service import PayPalError, create_order, capture_order, get_order_diagnostics
from app.services.runtime_settings import save_runtime_settings, visible_settings
from app.services.llm_provider import LLMProviderError

router = APIRouter(prefix="/api")
MAX_JOB_ATTEMPTS = 6
PAYMENT_CURRENCY = "USD"


def _billing_summary(job: Job, run: VerificationRun | None = None) -> dict:
    """Split the approved budget evenly across contract criteria and price passed ones."""
    contract_data = job.approved_spec or {}
    criteria = contract_data.get("criteria") or []
    total = len(criteria)
    latest = run or max(job.runs, key=lambda item: item.attempt, default=None)
    results = latest.results_json if latest else []
    results_by_key = {}
    for result in results:
        if not isinstance(result, dict) or not result.get("key"):
            continue
        key = result["key"]
        previous = results_by_key.get(key)
        # Browser smoke checks can share a key with an approved criterion. Keep
        # the criterion-level result so a later, unrelated browser check cannot
        # erase an earned line item from the invoice.
        if previous is None or previous.get("method") == "browser" or result.get("method") != "browser":
            results_by_key[key] = result
    budget_cents = int((Decimal(str(job.price)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    base_cents, remainder_cents = divmod(budget_cents, total) if total else (0, 0)
    bill_items = []
    payable_cents = 0
    passed_count = 0
    for index, criterion in enumerate(criteria):
        if not isinstance(criterion, dict):
            continue
        key = criterion.get("key")
        result = results_by_key.get(key) if key else None
        allocated_cents = base_cents + (1 if index < remainder_cents else 0)
        passed = bool(result and result.get("passed") and not result.get("skipped", False))
        if result is None:
            status = "pending"
        elif result.get("skipped", False):
            status = "skipped"
        elif passed:
            status = "passed"
        else:
            status = "failed"
        billed_cents = allocated_cents if passed else 0
        payable_cents += billed_cents
        passed_count += int(passed)
        bill_items.append({
            "key": key,
            "label": criterion.get("label") or key or "Acceptance check",
            "detail": criterion.get("detail") or "",
            "status": status,
            "allocated_amount": allocated_cents / 100,
            "billed_amount": billed_cents / 100,
        })
    return {
        "total_budget": budget_cents / 100,
        "payable_amount": payable_cents / 100,
        "criteria_passed": passed_count,
        "criteria_total": total,
        "bill_items": bill_items,
    }


def _ready_status(job: Job, run: VerificationRun | None = None) -> str:
    summary = _billing_summary(job, run)
    if summary["criteria_passed"] == 0:
        return "FAILED"
    if summary["criteria_passed"] == summary["criteria_total"]:
        return "VERIFIED"
    return "BILLABLE"


def _checkout_ready(job: Job, summary: dict | None = None) -> bool:
    """Allow checkout for completed partial runs that have a non-zero invoice."""
    summary = summary or _billing_summary(job)
    deliverable_ready = (
        bool(job.artifact_path and Path(job.artifact_path).is_dir())
        if job.deliverable_type == "source_project"
        else bool(job.preview_path and Path(job.preview_path).is_file())
    )
    return bool(
        job.status in {"VERIFIED", "BILLABLE", "FAILED"}
        and job.runs
        and summary["payable_amount"] > 0
        and deliverable_ready
    )


def serialize(job: Job):
    attempts = max((run.attempt for run in job.runs), default=0)
    summary = _billing_summary(job)
    checkout_ready = _checkout_ready(job, summary)
    status = job.status
    # Jobs created before partial billing was introduced can still be stored as
    # FAILED even though their latest run earned billable acceptance checks.
    if checkout_ready:
        status = "VERIFIED" if summary["criteria_passed"] == summary["criteria_total"] else "BILLABLE"
    retryable_payment = not job.payment or job.payment.status == "CANCELLED"
    contract = dict(job.approved_spec) if job.approved_spec else None
    if contract is not None:
        contract["currency"] = PAYMENT_CURRENCY
    return {
        "id": job.id,
        "title": job.title,
        "prompt": job.prompt,
        "deliverable_type": job.deliverable_type,
        "status": status,
        "price": float(job.price),
        "currency": PAYMENT_CURRENCY,
        "total_budget": summary["total_budget"],
        "payable_amount": summary["payable_amount"],
        "criteria_passed": summary["criteria_passed"],
        "criteria_total": summary["criteria_total"],
        "bill_items": summary["bill_items"],
        "can_checkout": checkout_ready,
        "contract": contract,
        "runs": [{"attempt": r.attempt, "passed": r.passed, "results": r.results_json} for r in sorted(job.runs, key=lambda item: item.attempt)],
        "preview_ready": bool(
            job.deliverable_type == "browser_app"
            and job.preview_path
            and Path(job.preview_path).is_file()
        ),
        "artifact_ready": bool(
            job.artifact_path and Path(job.artifact_path).is_dir()
        ),
        "can_regenerate": bool(status in {"VERIFIED", "BILLABLE", "FAILED"} and retryable_payment and attempts < MAX_JOB_ATTEMPTS),
        "paid": bool(job.payment and job.payment.status == "COMPLETED"),
        "capture_id": job.payment.capture_id if job.payment else None,
        "payment_order_id": job.payment.paypal_order_id if job.payment else None,
        "payment_approval_url": job.payment.approval_url if job.payment else None,
        "payment_mode": (
            "mock"
            if job.payment and str(job.payment.paypal_order_id).startswith("MOCK-")
            else settings.paypal_mode
        ),
        "download_ready": bool(job.payment and job.payment.status == "COMPLETED" and job.status in {"PAID", "DELIVERED"}),
    }

def run_job(job_id: str):
    from app.db.database import SessionLocal
    db = SessionLocal(); job = db.get(Job, job_id)
    has_current_run = False
    try:
        if not job:
            return
        rebuilding = job.status == "REBUILDING"
        if rebuilding:
            # Hide an older deliverable while replacing it so a failed new build
            # cannot accidentally leave a stale template available for checkout.
            job.preview_path = None
            job.artifact_path = None
        job.status = "GENERATING"; db.commit(); contract = Contract.model_validate(job.approved_spec)
        if job.deliverable_type == "source_project":
            attempt = max((run.attempt for run in job.runs), default=0) + 1
            job.status = "VERIFYING"
            db.commit()
            project_path = generate_source_project(job.id, job.prompt, attempt)
            result = verify_source_project(project_path)
            job.preview_path = None
            job.artifact_path = project_path
            job.runs.append(
                VerificationRun(
                    attempt=attempt,
                    results_json=[result],
                    passed=result["passed"],
                )
            )
            db.add(
                GenerationVersion(
                    job_id=job.id,
                    attempt_number=attempt,
                    verification_results=[result],
                    browser_results=[],
                )
            )
            has_current_run = True
            job.status = _ready_status(job)
            db.commit()
            return
        path = generate_page(job.id, contract, job.prompt)
        job.preview_path = path

        first_attempt = max((run.attempt for run in job.runs), default=0) + 1
        remaining_attempts = max(0, MAX_JOB_ATTEMPTS - first_attempt + 1)
        for attempt_offset in range(min(3, remaining_attempts)):
            attempt = first_attempt + attempt_offset
            job.status = "VERIFYING"; db.commit()

            # Run enhanced HTML verification
            results = verify_page_enhanced(path, contract)

            browser_results = verify_with_browser(path, contract)
            all_results = results + browser_results

            passed = all(
                check["passed"]
                for check in all_results
                if not check.get("skipped", False)
            )

            # Save version history
            version = GenerationVersion(
                job_id=job.id,
                attempt_number=attempt,
                verification_results=results,
                browser_results=browser_results
            )
            db.add(version)

            job.runs.append(VerificationRun(attempt=attempt, results_json=all_results, passed=passed))
            db.commit()
            has_current_run = True

            if passed:
                job.status = "VERIFIED"
                break

            if attempt_offset < 2 and attempt < MAX_JOB_ATTEMPTS:
                job.status = "REPAIRING"
                db.commit()
                path = repair_page(job.id, contract, job.prompt, results)
                job.preview_path = path
        else:
            job.status = _ready_status(job)

        db.commit()
    except Exception as exc:
        db.rollback()
        job = db.get(Job, job_id)
        if job:
            failure = {
                "key": "generation",
                "label": "AI generation failed",
                "passed": False,
                "evidence": str(exc),
                "method": "provider",
            }
            if has_current_run and job.runs:
                latest_run = max(job.runs, key=lambda item: item.attempt)
                latest_run.results_json = list(latest_run.results_json or []) + [failure]
                latest_run.passed = False
                job.status = _ready_status(job, latest_run)
            else:
                attempt = max((run.attempt for run in job.runs), default=0) + 1
                job.preview_path = None
                job.status = "FAILED"
                job.runs.append(VerificationRun(
                    attempt=attempt,
                    results_json=[failure],
                    passed=False,
                ))
            db.commit()
    finally: db.close()

@router.post("/jobs", status_code=201)
def create_job(payload: JobCreate, db: Session = Depends(get_db)):
    try:
        contract = make_contract(payload.prompt, payload.budget, payload.deliverable_type)
    except (LLMProviderError, ValueError, TypeError) as exc:
        raise HTTPException(502, f"The AI provider could not draft this contract: {exc}") from exc
    job_id = str(uuid.uuid4()); job = Job(id=job_id, prompt=payload.prompt, title="Software build", deliverable_type=payload.deliverable_type, price=contract.price, currency=PAYMENT_CURRENCY, status="DRAFT")
    job.approved_spec = contract.model_dump(); db.add(job); db.commit(); db.refresh(job); return serialize(job)

@router.get("/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job: raise HTTPException(404, "Job not found")
    return serialize(job)

@router.post("/jobs/{job_id}/approve-spec")
def approve(job_id: str, payload: ApproveSpec, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job: raise HTTPException(404, "Job not found")
    if not payload.approved: raise HTTPException(400, "The specification must be approved to continue")
    job.status = "SPEC_APPROVED"; db.commit(); return serialize(job)

@router.post("/jobs/{job_id}/run", status_code=202)
def run(job_id: str, background: BackgroundTasks, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    initial_run = job.status == "SPEC_APPROVED"
    attempts = max((run.attempt for run in job.runs), default=0)
    rebuild = (
        job.status in {"VERIFIED", "BILLABLE", "FAILED"}
        and (not job.payment or job.payment.status == "CANCELLED")
        and attempts < MAX_JOB_ATTEMPTS
    )
    if not initial_run and not rebuild:
        raise HTTPException(400, "Approve the contract first, or rebuild an unpaid verified, billable, or failed job")
    job.status = "REBUILDING" if rebuild else "GENERATING"
    db.commit()
    db.close()
    background.add_task(run_job, job_id); return {"message":"Generation and verification queued", "job_id":job_id}

@router.get("/jobs/{job_id}/preview")
def preview(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job or job.deliverable_type != "browser_app" or not job.preview_path: raise HTTPException(404, "Preview not available for this deliverable")
    return FileResponse(job.preview_path, headers={"Content-Security-Policy": "sandbox", "X-Content-Type-Options": "nosniff", "Content-Disposition": "inline"})


@router.get("/jobs/{job_id}/preview/annotated")
def preview_annotated(job_id: str, db: Session = Depends(get_db)):
    """Return annotated preview with visual verification feedback"""
    job = db.get(Job, job_id)
    if not job or job.deliverable_type != "browser_app" or not job.preview_path:
        raise HTTPException(404, "Preview not available for this deliverable")

    latest_run = max(job.runs, key=lambda item: item.attempt, default=None)
    if not latest_run:
        raise HTTPException(400, "No verification results")

    try:
        annotated_path = create_annotated_preview(job.preview_path, latest_run.results_json)
        return FileResponse(annotated_path, headers={
            "Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com data:; img-src data:; connect-src 'none'; form-action 'none'; base-uri 'none';",
            "X-Content-Type-Options": "nosniff"
        })
    except Exception as e:
        raise HTTPException(500, f"Could not create annotated preview: {str(e)}")


@router.get("/jobs/{job_id}/versions")
def get_versions(job_id: str, db: Session = Depends(get_db)):
    """Get version history for a job"""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    versions = db.query(GenerationVersion).filter(
        GenerationVersion.job_id == job_id
    ).order_by(GenerationVersion.attempt_number).all()

    return [{
        "attempt": v.attempt_number,
        "created_at": v.created_at.isoformat(),
        "passed": all(r["passed"] for r in (v.verification_results or [])),
        "check_count": len(v.verification_results or []),
        "pass_count": sum(1 for r in (v.verification_results or []) if r["passed"]),
        "has_browser_results": any(
            not result.get("skipped", False) for result in (v.browser_results or [])
        )
    } for v in versions]

@router.get("/paypal/return")
def paypal_return(token: str | None = None, db: Session = Depends(get_db)):
    payment = db.query(Payment).filter(Payment.paypal_order_id == token).first() if token else None
    if not payment:
        return RedirectResponse("/?paypal=invalid", status_code=303)
    return RedirectResponse(
        "/?" + urlencode({"paypal": "approved", "job_id": payment.job_id}),
        status_code=303,
    )

@router.get("/paypal/cancel")
def paypal_cancel(token: str | None = None, db: Session = Depends(get_db)):
    payment = db.query(Payment).filter(Payment.paypal_order_id == token).first() if token else None
    if not payment:
        return RedirectResponse("/?paypal=invalid", status_code=303)
    if payment.status == "PENDING":
        payment.status = "CANCELLED"
        payment.job.status = _ready_status(payment.job)
        db.commit()
    outcome = "approved" if payment.status == "COMPLETED" else "cancelled"
    return RedirectResponse(
        "/?" + urlencode({"paypal": outcome, "job_id": payment.job_id}),
        status_code=303,
    )

def _settings_authorized(token: str | None) -> bool:
    configured = settings.settings_admin_token
    return (not configured and settings.app_env.lower() != "production") or bool(token and configured and hmac.compare_digest(token, configured))

@router.get("/settings")
def get_settings_page(token: str | None = Header(default=None, alias="X-Settings-Token"), db: Session = Depends(get_db)):
    if not _settings_authorized(token): raise HTTPException(401, "Settings admin token required")
    return {"settings": visible_settings(db), "warning": "Secret values are never returned. Render environment variables remain the deployment source of truth."}

@router.post("/settings")
def update_settings(payload: dict[str, str], token: str | None = Header(default=None, alias="X-Settings-Token"), db: Session = Depends(get_db)):
    if not _settings_authorized(token): raise HTTPException(401, "Settings admin token required")
    try:
        save_runtime_settings(db, payload)
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc
    return {"saved": True, "settings": visible_settings(db)}

@router.post("/jobs/{job_id}/paypal/order")
def paypal_order(job_id: str, x_paypal_request_id: str | None = Header(default=None), db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job: raise HTTPException(404, "Job not found")
    if job.status == "PAYMENT_PENDING" and job.payment:
        if job.payment.currency != PAYMENT_CURRENCY:
            raise HTTPException(
                409,
                "This pending order is not in USD. Reset it before creating a new USD order.",
            )
        mode = "mock" if str(job.payment.paypal_order_id).startswith("MOCK-") else settings.paypal_mode
        return {"id": job.payment.paypal_order_id, "status": "CREATED", "amount": f"{float(job.payment.amount):.2f}", "currency": job.payment.currency, "mode": mode, "approve_url": job.payment.approval_url}
    billing = _billing_summary(job)
    if billing["payable_amount"] <= 0:
        raise HTTPException(400, "No approved acceptance checks passed, so no payment is due")
    if not _checkout_ready(job, billing):
        raise HTTPException(400, "This job has no completed, payable verification run ready for checkout")
    request_id = x_paypal_request_id or uuid.uuid4().hex
    if job.payment and job.payment.status == "CANCELLED" and request_id == job.payment.order_request_id:
        request_id = uuid.uuid4().hex
    try:
        result = create_order(
            job.id,
            billing["payable_amount"],
            job.currency,
            request_id,
            billing["bill_items"],
        )
    except PayPalError as exc:
        raise HTTPException(502, str(exc)) from exc
    job.status = "PAYMENT_PENDING"
    order_currency = result.get("currency", "USD")
    if job.payment:
        payment = job.payment
        payment.paypal_order_id = result["id"]
        payment.approval_url = result.get("approve_url")
        payment.order_request_id = request_id
        payment.capture_id = None
        payment.capture_request_id = None
        payment.amount = Decimal(f"{billing['payable_amount']:.2f}")
        payment.currency = order_currency
        payment.status = "PENDING"
    else:
        job.payment = Payment(paypal_order_id=result["id"], approval_url=result.get("approve_url"), order_request_id=request_id, amount=Decimal(f"{billing['payable_amount']:.2f}"), currency=order_currency, status="PENDING")
    db.commit(); return result


@router.post("/jobs/{job_id}/paypal/reset")
def reset_paypal_order(job_id: str, db: Session = Depends(get_db)):
    """Abandon a stale local checkout so a fresh PayPal order can be created."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status != "PAYMENT_PENDING" or not job.payment or job.payment.status != "PENDING":
        raise HTTPException(400, "There is no pending PayPal order to reset")
    job.payment.status = "CANCELLED"
    job.status = _ready_status(job)
    db.commit()
    return serialize(job)

@router.get("/jobs/{job_id}/paypal/diagnostics")
def paypal_diagnostics(job_id: str, db: Session = Depends(get_db)):
    """Identify the Sandbox seller attached to this job's own PayPal order."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if not job.payment or not job.payment.paypal_order_id:
        raise HTTPException(404, "This job has no PayPal order to inspect")
    try:
        paypal = get_order_diagnostics(job.payment.paypal_order_id, job.id)
    except PayPalError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {
        "order_id": job.payment.paypal_order_id,
        "payment_status": job.payment.status,
        "bill_currency": job.payment.currency,
        "bill_amount": f"{job.payment.amount:.2f}",
        **paypal,
    }

@router.post("/jobs/{job_id}/paypal/capture")
def paypal_capture(job_id: str, payload: PaymentAction, x_paypal_request_id: str | None = Header(default=None), db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job: raise HTTPException(404, "Job not found")
    if job.payment and job.payment.status == "COMPLETED":
        return {"status": "COMPLETED", "capture_id": job.payment.capture_id, "idempotent": True}
    if job.status != "PAYMENT_PENDING" or not job.payment: raise HTTPException(400, "No pending payment for this job")
    if payload.order_id and payload.order_id != job.payment.paypal_order_id: raise HTTPException(400, "Order does not belong to this job")
    try:
        request_id = job.payment.capture_request_id or x_paypal_request_id or uuid.uuid4().hex
        job.payment.capture_request_id = request_id
        db.commit()
        result = capture_order(job.payment.paypal_order_id, float(job.payment.amount), job.payment.currency, job.id, request_id)
    except PayPalError as exc:
        raise HTTPException(502, str(exc)) from exc
    job.payment.capture_id=result["id"]; job.payment.capture_request_id=request_id; job.payment.status="COMPLETED"; job.status="PAID"; db.commit(); return {"status":"COMPLETED", "capture_id":result["id"], "idempotent": False}

@router.get("/jobs/{job_id}/download")
def download(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job or not job.payment or job.payment.status != "COMPLETED" or job.status not in {"PAID","DELIVERED"}: raise HTTPException(403, "Delivery is locked until payment is confirmed")
    try:
        target = make_zip(
            job_id,
            job.artifact_path if job.deliverable_type == "source_project" else None,
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(500, f"Could not package the paid deliverable: {exc}") from exc
    job.status="DELIVERED"; db.commit(); return FileResponse(target, filename=target.name, media_type="application/zip")
