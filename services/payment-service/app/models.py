from pydantic import BaseModel, Field
from uuid import UUID

class PaymentRequest(BaseModel):
    transaction_id: UUID
    amount: float = Field(gt=0)
    currency: str = "NGN"
    user_id: str
    idempotency_key: str

class PaymentResponse(BaseModel):
    transaction_id: UUID
    status: str
    message: str
