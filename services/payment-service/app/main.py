import time
import random
import httpx
from fastapi import FastAPI, HTTPException
from prometheus_client import generate_latest
from app.models import PaymentRequest, PaymentResponse
from app.metrics import (
    payment_requests_total,
    payment_failures_total,
    payment_latency_seconds
)
from app.idempotency import check_idempotency, store_idempotency
from app.config import BANK_API_URL, REQUEST_TIMEOUT

app = FastAPI(title="Payment Service", version="1.0.0")

@app.post("/pay", response_model=PaymentResponse)
def process_payment(payload: PaymentRequest):
    start_time = time.time()

    # Idempotency check
    cached = check_idempotency(payload.idempotency_key)
    if cached:
        payment_requests_total.labels(status="idempotent_hit").inc()
        return cached

    # Simulate internal processing failures
    if random.random() < 0.05:
        payment_failures_total.labels(reason="internal_error").inc()
        raise HTTPException(status_code=500, detail="Internal processing error")

    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            response = client.post(
                f"{BANK_API_URL}/authorize",
                json={
                    "transaction_id": str(payload.transaction_id),
                    "amount": payload.amount
                }
            )

        if response.status_code != 200:
            payment_failures_total.labels(reason="bank_rejection").inc()
            raise HTTPException(status_code=502, detail="Bank authorization failed")

    except httpx.TimeoutException:
        payment_failures_total.labels(reason="bank_timeout").inc()
        raise HTTPException(status_code=504, detail="Bank API timeout")

    latency = time.time() - start_time
    payment_latency_seconds.observe(latency)
    payment_requests_total.labels(status="success").inc()

    result = PaymentResponse(
        transaction_id=payload.transaction_id,
        status="SUCCESS",
        message="Payment processed successfully"
    )

    store_idempotency(payload.idempotency_key, result)
    return result

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/metrics")
def metrics():
    return generate_latest()

