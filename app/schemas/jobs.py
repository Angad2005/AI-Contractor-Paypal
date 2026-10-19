from pydantic import BaseModel, Field

class JobCreate(BaseModel):
    prompt: str = Field(min_length=20, max_length=2000)
    budget: float = Field(default=10, gt=0, le=10000)

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
    currency: str = "USD"

class JobSummary(BaseModel):
    id: str
    title: str
    prompt: str
    status: str
    price: float
    currency: str
    contract: Contract | None = None
    runs: list[dict] = []
    paid: bool = False
    download_ready: bool = False

class ApproveSpec(BaseModel):
    approved: bool

class PaymentAction(BaseModel):
    order_id: str | None = None
