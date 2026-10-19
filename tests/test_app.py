from pathlib import Path

from app.main import health
from app.api.routes import run_job
from app.db.database import SessionLocal
from app.db.models import Job
from app.schemas.jobs import Contract
from app.services.artifact_service import make_zip
from app.services.contract_generator import make_contract
from app.services.page_generator import generate_page
from app.services.paypal_service import capture_order, create_order
from app.services.verifier import verify_page


def test_health():
    assert health()["status"] == "ok"


def test_contract_generation_and_verification(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.page_generator.settings.generated_dir", str(tmp_path))
    contract = make_contract(
        "Build a responsive landing page with pricing and signup form for a climate startup.",
        10,
    )
    assert contract.price == 10
    assert {"hero", "features", "pricing", "signup"}.issubset(contract.required_sections)

    path = generate_page("test-job", contract, "climate startup")
    checks = verify_page(path, contract)
    assert all(check["passed"] for check in checks)
    assert Path(path).exists()


def test_mock_payment_and_protected_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.page_generator.settings.generated_dir", str(tmp_path))
    monkeypatch.setattr("app.services.artifact_service.settings.generated_dir", str(tmp_path))
    contract = Contract(
        required_sections=["hero"],
        required_features=["signup"],
        criteria=[],
        price=12.5,
        currency="USD",
    )
    generate_page("paid-job", contract, "brief")
    order = create_order("paid-job", 12.5, "USD")
    capture = capture_order(order["id"], 12.5, "USD", "paid-job")
    archive = make_zip("paid-job")
    assert order["status"] == "CREATED"
    assert capture["status"] == "COMPLETED"
    assert archive.exists()
    assert archive.suffix == ".zip"


def test_worker_persists_verified_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.page_generator.settings.generated_dir", str(tmp_path))
    contract = make_contract("Build a responsive landing page with pricing and signup form.", 10)
    job_id = "worker-test-job"
    job = Job(
        id=job_id,
        prompt="Build a responsive landing page with pricing and signup form.",
        title="Worker test",
        approved_spec=contract.model_dump(),
        price=10,
        currency="USD",
        status="SPEC_APPROVED",
    )
    db = SessionLocal()
    try:
        existing = db.get(Job, job.id)
        if existing:
            db.delete(existing)
            db.commit()
        db.add(job)
        db.commit()
    finally:
        db.close()

    run_job(job_id)

    db = SessionLocal()
    try:
        result = db.get(Job, job_id)
        assert result.status == "VERIFIED"
        assert result.runs and result.runs[-1].passed is True
    finally:
        db.close()
