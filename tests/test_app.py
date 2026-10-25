from pathlib import Path
from zipfile import ZipFile

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.main import health
from app.api.routes import create_job, download, preview, run_job
from app.core.config import ROOT_DIR, Settings, settings
from app.db.database import Base, SessionLocal, migrate_legacy_columns
from app.db.models import Job, Payment, VerificationRun
from app.schemas.jobs import Contract, JobCreate
from app.services.artifact_service import make_zip
from app.services.contract_generator import make_contract
from app.services.page_generator import generate_page
from app.services.paypal_service import capture_order, create_order
from app.services.project_generator import generate_source_project, verify_source_project
from app.services import browser_verifier
from app.services import runtime_settings
from app.services.verifier import verify_page


@pytest.fixture(autouse=True)
def use_offline_providers(monkeypatch):
    """Keep tests deterministic even when the developer .env uses live sandbox providers."""
    monkeypatch.setattr(settings, "paypal_mode", "mock")
    monkeypatch.setattr(settings, "llm_provider", "demo")
    monkeypatch.setattr(settings, "llm_api_key", "")


def test_health():
    assert health()["status"] == "ok"


def test_migrates_existing_database_columns(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE jobs (id VARCHAR(36) PRIMARY KEY, prompt TEXT NOT NULL, "
            "title VARCHAR(120) NOT NULL, approved_spec JSON, price NUMERIC(10, 2), "
            "currency VARCHAR(3), status VARCHAR(32), preview_path VARCHAR(255), "
            "created_at DATETIME)"
        )
        VerificationRun.__table__.create(connection)
        connection.exec_driver_sql(
            "CREATE TABLE app_settings (key VARCHAR(80) PRIMARY KEY, value TEXT, is_secret BOOLEAN)"
        )
        connection.exec_driver_sql(
            "INSERT INTO app_settings (key, value, is_secret) VALUES ('existing', 'value', FALSE)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE payments (id INTEGER PRIMARY KEY, job_id VARCHAR(36), "
            "paypal_order_id VARCHAR(120), capture_id VARCHAR(120), "
            "amount NUMERIC(10, 2), currency VARCHAR(3), status VARCHAR(32))"
        )

    migrate_legacy_columns(engine)
    with Session(engine) as db:
        db.add(
            Job(
                id="legacy-schema-job",
                prompt="legacy schema test",
                title="Legacy schema test",
                price=10,
                currency="USD",
                status="DRAFT",
            )
        )
        db.commit()

    migrate_legacy_columns(engine)
    migrate_legacy_columns(engine)

    inspector = inspect(engine)
    assert "is_custom" in {
        column["name"] for column in inspector.get_columns("app_settings")
    }
    assert {"approval_url", "order_request_id", "capture_request_id"}.issubset(
        {column["name"] for column in inspector.get_columns("payments")}
    )
    assert {"deliverable_type", "artifact_path"}.issubset(
        {column["name"] for column in inspector.get_columns("jobs")}
    )
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT is_custom FROM app_settings WHERE key = 'existing'")
        ).scalar() in (False, 0)
    with Session(engine) as db:
        assert db.get(Job, "legacy-schema-job").payment is None
    engine.dispose()


def test_settings_load_dotenv_and_only_show_non_secret_values(tmp_path, monkeypatch):
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("PAYPAL_MODE", raising=False)
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "LLM_MODEL=dotenv-model\nLLM_API_KEY=dotenv-secret\nPAYPAL_MODE=sandbox\n",
        encoding="utf-8",
    )
    dotenv_settings = Settings(_env_file=dotenv_path)
    monkeypatch.setattr(runtime_settings, "settings", dotenv_settings)

    class EmptySettingsDB:
        def query(self, _model):
            return self

        def all(self):
            return []

    visible = {
        setting["key"]: setting
        for setting in runtime_settings.visible_settings(EmptySettingsDB())
    }
    assert Settings.model_config["env_file"] == ROOT_DIR / ".env"
    assert visible["llm_model"]["value"] == "dotenv-model"
    assert visible["paypal_mode"]["value"] == "sandbox"
    assert visible["llm_api_key"]["configured"] is True
    assert visible["llm_api_key"]["value"] == ""


def test_new_jobs_are_created_in_usd(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'usd-jobs.db'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(
        "app.api.routes.make_contract",
        lambda _prompt, budget, _deliverable_type: Contract(
            required_sections=["app"],
            required_features=["workflow"],
            criteria=[],
            price=budget,
        ),
    )

    with Session(engine) as db:
        result = create_job(
            JobCreate(prompt="Build a project tracker for my team", budget=20),
            db,
        )
        saved = db.get(Job, result["id"])
        assert result["currency"] == "USD"
        assert result["contract"]["currency"] == "USD"
        assert saved.currency == "USD"
        source = create_job(
            JobCreate(
                prompt="Build a desktop timer for my team",
                budget=20,
                deliverable_type="source_project",
            ),
            db,
        )
        assert db.get(Job, source["id"]).deliverable_type == "source_project"
    engine.dispose()


def test_missing_chromium_skips_browser_check(monkeypatch, tmp_path):
    class MissingChromium:
        def launch(self, **_kwargs):
            raise browser_verifier.PlaywrightError("Executable doesn't exist")

    class Playwright:
        chromium = MissingChromium()

    class PlaywrightContext:
        def __enter__(self):
            return Playwright()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(browser_verifier, "PLAYWRIGHT_AVAILABLE", True)
    monkeypatch.setattr(browser_verifier, "sync_playwright", PlaywrightContext)
    checks = browser_verifier.verify_with_browser(str(tmp_path / "index.html"), None)

    assert checks[0]["skipped"] is True
    assert checks[0]["passed"] is False
    assert "playwright install chromium" in checks[0]["evidence"]


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


def test_source_project_is_private_packaged_and_payment_gated(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.project_generator.settings.generated_dir", str(tmp_path))
    monkeypatch.setattr("app.services.artifact_service.settings.generated_dir", str(tmp_path))
    engine = create_engine(f"sqlite:///{tmp_path / 'source-project.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr("app.db.database.SessionLocal", factory)
    contract = make_contract(
        "Build a desktop timer app with start and stop controls.",
        15,
        "source_project",
    )
    job = Job(
        id="source-project-test",
        prompt="Build a desktop timer app with start and stop controls.",
        title="Software build",
        deliverable_type="source_project",
        approved_spec=contract.model_dump(),
        price=15,
        currency="USD",
        status="SPEC_APPROVED",
    )
    job_id = job.id
    with Session(engine) as db:
        db.add(job)
        db.commit()

    run_job(job_id)

    with Session(engine) as db:
        result = db.get(Job, job_id)
        assert result.status == "VERIFIED"
        assert result.preview_path is None
        assert Path(result.artifact_path).is_dir()
        assert verify_source_project(result.artifact_path)["passed"] is True
        with pytest.raises(HTTPException) as no_preview:
            preview(job_id, db)
        assert no_preview.value.status_code == 404
        with pytest.raises(HTTPException) as locked:
            download(job_id, db)
        assert getattr(locked.value, "status_code", None) == 403

        result.payment = Payment(
            amount=15,
            currency="USD",
            status="COMPLETED",
        )
        result.status = "PAID"
        db.commit()
        response = download(job_id, db)
        with ZipFile(response.path) as archive:
            assert "README.md" in archive.namelist()
            assert "src/main.py" in archive.namelist()
    engine.dispose()


def test_source_project_rejects_traversal_and_requires_project_files(tmp_path, monkeypatch):
    from app.services.project_generator import _validate_files

    with pytest.raises(ValueError, match="Unsafe source project path"):
        _validate_files({"../outside.py": "unsafe", "README.md": "instructions"})
    with pytest.raises(ValueError, match="Unsafe source project path"):
        _validate_files({".": "unsafe"})
    with pytest.raises(ValueError, match="README.md"):
        _validate_files({"main.py": "print('hello')"})


def test_worker_persists_verified_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.page_generator.settings.generated_dir", str(tmp_path))
    monkeypatch.setattr(
        "app.api.routes.verify_with_browser",
        lambda _path, _contract: [{
            "key": "browser_check",
            "label": "Browser-based verification",
            "passed": False,
            "skipped": True,
            "evidence": "Chromium unavailable",
            "method": "browser",
        }],
    )
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
        assert any(
            check.get("skipped") for check in result.runs[-1].results_json
        )
    finally:
        db.close()
