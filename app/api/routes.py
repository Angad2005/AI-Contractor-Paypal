import uuid
import hmac
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session
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
from app.services.paypal_service import PayPalError, create_order, capture_order
from app.services.runtime_settings import save_runtime_settings, visible_settings

router = APIRouter(prefix="/api")
def serialize(job: Job):
    return {"id":job.id,"title":job.title,"prompt":job.prompt,"status":job.status,"price":float(job.price),"currency":job.currency,"contract":job.approved_spec,"runs":[{"attempt":r.attempt,"passed":r.passed,"results":r.results_json} for r in job.runs],"paid":bool(job.payment and job.payment.status=="COMPLETED"),"download_ready":bool(job.payment and job.payment.status=="COMPLETED" and job.status in {"PAID","DELIVERED"})}

def run_job(job_id: str):
    from app.db.database import SessionLocal
    db = SessionLocal(); job = db.get(Job, job_id)
    try:
        job.status = "GENERATING"; db.commit(); contract = Contract.model_validate(job.approved_spec)
        path = generate_page(job.id, contract, job.prompt)
        job.preview_path = path

        for attempt in range(1, 4):
            job.status = "VERIFYING"; db.commit()

            # Run enhanced HTML verification
            results = verify_page_enhanced(path, contract)

            # Run browser verification if Playwright is available
            try:
                browser_results = verify_with_browser(path, contract)
                # Combine results
                all_results = results + browser_results
            except:
                # Fall back to HTML-only verification if browser check fails
                all_results = results

            passed = all(x["passed"] for x in all_results)

            # Save version history
            version = GenerationVersion(
                job_id=job.id,
                attempt_number=attempt,
                verification_results=results,
                browser_results=browser_results if 'browser_results' in locals() else None
            )
            db.add(version)

            job.runs.append(VerificationRun(attempt=attempt, results_json=all_results, passed=passed))
            db.commit()

            if passed:
                job.status = "VERIFIED"
                break

            if attempt < 3:
                job.status = "REPAIRING"
                db.commit()
                path = repair_page(job.id, contract, job.prompt, results)
                job.preview_path = path
        else:
            job.status = "FAILED"

        db.commit()
    finally: db.close()

@router.post("/jobs", status_code=201)
def create_job(payload: JobCreate, db: Session = Depends(get_db)):
    contract = make_contract(payload.prompt, payload.budget)
    job_id = str(uuid.uuid4()); job = Job(id=job_id, prompt=payload.prompt, title="Launchpad brief", price=contract.price, currency=contract.currency, status="DRAFT")
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
    if not job or job.status != "SPEC_APPROVED": raise HTTPException(400, "Approve the acceptance contract first")
    db.commit()
    db.close()
    background.add_task(run_job, job_id); return {"message":"Generation and verification queued", "job_id":job_id}

@router.get("/jobs/{job_id}/preview")
def preview(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job or not job.preview_path: raise HTTPException(404, "Preview not ready")
    return FileResponse(job.preview_path, headers={"Content-Security-Policy": "sandbox", "X-Content-Type-Options": "nosniff", "Content-Disposition": "inline"})


@router.get("/jobs/{job_id}/preview/annotated")
def preview_annotated(job_id: str, db: Session = Depends(get_db)):
    """Return annotated preview with visual verification feedback"""
    job = db.get(Job, job_id)
    if not job or not job.preview_path:
        raise HTTPException(404, "Preview not ready")

    latest_run = job.runs[-1] if job.runs else None
    if not latest_run:
        raise HTTPException(400, "No verification results")

    try:
        annotated_path = create_annotated_preview(job.preview_path, latest_run.results_json)
        return FileResponse(annotated_path, headers={
            "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline';",
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
        "has_browser_results": bool(v.browser_results)
    } for v in versions]

@router.get("/paypal/return")
def paypal_return(token: str | None = None):
    return {"status": "buyer_returned", "message": "Buyer approval returned. Capture is still server-side and must be confirmed by the application.", "order_id": token}

@router.get("/paypal/cancel")
def paypal_cancel(token: str | None = None):
    return {"status": "cancelled", "message": "PayPal approval was cancelled. No payment or delivery was recorded.", "order_id": token}

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
        return {"id": job.payment.paypal_order_id, "status": "CREATED", "amount": f"{float(job.price):.2f}", "currency": job.currency, "mode": settings.paypal_mode, "approve_url": job.payment.approval_url}
    if job.status != "VERIFIED": raise HTTPException(400, "Only verified jobs can enter checkout")
    request_id = x_paypal_request_id or f"job-{job.id}-order-v1"
    try:
        result = create_order(job.id, float(job.price), job.currency, request_id)
    except PayPalError as exc:
        raise HTTPException(502, str(exc)) from exc
    job.status = "PAYMENT_PENDING"
    job.payment = Payment(paypal_order_id=result["id"], approval_url=result.get("approve_url"), order_request_id=request_id, amount=job.price, currency=job.currency, status="PENDING"); db.commit(); return result

@router.post("/jobs/{job_id}/paypal/capture")
def paypal_capture(job_id: str, payload: PaymentAction, x_paypal_request_id: str | None = Header(default=None), db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job: raise HTTPException(404, "Job not found")
    if job.payment and job.payment.status == "COMPLETED":
        return {"status": "COMPLETED", "capture_id": job.payment.capture_id, "idempotent": True}
    if job.status != "PAYMENT_PENDING" or not job.payment: raise HTTPException(400, "No pending payment for this job")
    if payload.order_id and payload.order_id != job.payment.paypal_order_id: raise HTTPException(400, "Order does not belong to this job")
    try:
        request_id = x_paypal_request_id or f"job-{job.id}-capture-v1"
        result = capture_order(job.payment.paypal_order_id, float(job.price), job.currency, job.id, request_id)
    except PayPalError as exc:
        raise HTTPException(502, str(exc)) from exc
    job.payment.capture_id=result["id"]; job.payment.capture_request_id=request_id; job.payment.status="COMPLETED"; job.status="PAID"; db.commit(); return {"status":"COMPLETED", "capture_id":result["id"], "idempotent": False}

@router.get("/jobs/{job_id}/download")
def download(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job or not job.payment or job.payment.status != "COMPLETED" or job.status not in {"PAID","DELIVERED"}: raise HTTPException(403, "Delivery is locked until payment is confirmed")
    target = make_zip(job_id); job.status="DELIVERED"; db.commit(); return FileResponse(target, filename=target.name, media_type="application/zip")

