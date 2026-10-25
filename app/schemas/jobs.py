from typing import Literal

from pydantic import BaseModel, Field

class JobCreate(BaseModel):
    prompt: str = Field(min_length=20, max_length=2000)
    budget: float = Field(default=10, gt=0, le=10000)
    deliverable_type: Literal["browser_app", "source_project"] = "browser_app"

class Criterion(BaseModel):
    key: str
    label: str
    detail: str
    required: bool = True

class Contract(BaseModel):
    required_sections: list[str]
    required_features: list[str]
    criteria: list[Criterion]
    price: float
    currency: Literal["USD"] = "USD"

class JobSummary(BaseModel):
    id: str
    title: str
    prompt: str
    status: str
    price: float
    currency: Literal["USD"]
    contract: Contract | None = None
    runs: list[dict] = []
    paid: bool = False
    download_ready: bool = False

class ApproveSpec(BaseModel):
    approved: bool

class PaymentAction(BaseModel):
    order_id: str | None = None
