from prometheus_client import Counter, Histogram

payment_requests_total = Counter(
    "payment_requests_total",
    "Total payment requests received",
    ["status"]
)

payment_failures_total = Counter(
    "payment_failures_total",
    "Total failed payments",
    ["reason"]
)

payment_latency_seconds = Histogram(
    "payment_latency_seconds",
    "Payment request latency",
    buckets=(0.1, 0.2, 0.3, 0.5, 1, 2)
)
