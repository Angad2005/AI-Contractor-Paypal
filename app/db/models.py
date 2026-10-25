from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base


def utcnow(): return datetime.now(timezone.utc)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    prompt: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(120))
    deliverable_type: Mapped[str] = mapped_column(String(32), default="browser_app")
    approved_spec: Mapped[dict] = mapped_column(JSON, nullable=True)
    price: Mapped[float] = mapped_column(Numeric(10, 2), default=10)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    status: Mapped[str] = mapped_column(String(32), default="DRAFT")
    preview_path: Mapped[str] = mapped_column(String(255), nullable=True)
    artifact_path: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    runs: Mapped[list["VerificationRun"]] = relationship(cascade="all, delete-orphan")
    payment: Mapped["Payment"] = relationship(back_populates="job", uselist=False, cascade="all, delete-orphan")


class VerificationRun(Base):
    __tablename__ = "verification_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"))
    attempt: Mapped[int] = mapped_column(Integer)
    results_json: Mapped[list] = mapped_column(JSON)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), unique=True)
    paypal_order_id: Mapped[str] = mapped_column(String(120), nullable=True)
    capture_id: Mapped[str] = mapped_column(String(120), nullable=True)
    approval_url: Mapped[str] = mapped_column(String(500), nullable=True)
    order_request_id: Mapped[str] = mapped_column(String(120), nullable=True)
    capture_request_id: Mapped[str] = mapped_column(String(120), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    job: Mapped[Job] = relationship(back_populates="payment")


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False)  # True for user-defined custom env vars
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class GenerationVersion(Base):
    """Track each generation attempt for version history"""
    __tablename__ = "generation_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"))
    attempt_number: Mapped[int] = mapped_column(Integer)
    html_content: Mapped[str] = mapped_column(Text, nullable=True)
    css_content: Mapped[str] = mapped_column(Text, nullable=True)
    js_content: Mapped[str] = mapped_column(Text, nullable=True)
    verification_results: Mapped[list] = mapped_column(JSON, nullable=True)
    browser_results: Mapped[list] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
