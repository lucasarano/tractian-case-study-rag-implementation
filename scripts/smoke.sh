#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
AUTH_HEADER="${AUTH_HEADER:-Authorization: Bearer dev:tech-001@companyA}"

tmp_manual_job="$(mktemp)"
tmp_answer="$(mktemp)"
trap 'rm -f "$tmp_manual_job" "$tmp_answer"' EXIT

curl -fsS "$BASE_URL/healthz" >/dev/null

curl -fsS -X POST "$BASE_URL/v1/ingest/manuals/jobs" \
  -H "$AUTH_HEADER" \
  -H "Content-Type: application/json" \
  --data @fixtures/manual_job.json >"$tmp_manual_job"

job_id="$(python - "$tmp_manual_job" <<'PY'
import json
import sys

with open(sys.argv[1]) as handle:
    print(json.load(handle)["job_id"])
PY
)"

for _ in $(seq 1 30); do
  status="$(curl -fsS "$BASE_URL/v1/ingest/manuals/jobs/$job_id" -H "$AUTH_HEADER" | python -c 'import json,sys; print(json.load(sys.stdin)["status"])')"
  if [ "$status" = "succeeded" ]; then
    break
  fi
  if [ "$status" = "failed" ]; then
    echo "manual ingest job failed" >&2
    exit 1
  fi
  sleep 2
done

curl -fsS -X POST "$BASE_URL/v1/ingest/logs" \
  -H "$AUTH_HEADER" \
  -H "Content-Type: application/json" \
  --data @fixtures/log_incident.json >/dev/null

curl -fsS -X POST "$BASE_URL/v1/copilot/answer" \
  -H "$AUTH_HEADER" \
  -H "Content-Type: application/json" \
  -d '{
    "machine_id":"mx17",
    "message":"MX17 overheating after 20 minutes. What should I check first?"
  }' >"$tmp_answer"

python - "$tmp_answer" <<'PY'
import json
import sys

with open(sys.argv[1]) as handle:
    payload = json.load(handle)

evidence = payload["answer"]["supporting_evidence"]
recommended_checks = payload["answer"]["recommended_checks"]

assert recommended_checks, "expected at least one recommended check"
assert any(item["source_type"] == "oem_manual" for item in evidence), "missing OEM evidence"
assert any(item["source_type"] == "historical_log" for item in evidence), "missing log evidence"

print(json.dumps(payload, indent=2))
PY
