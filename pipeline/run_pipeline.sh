#!/usr/bin/env bash
# =============================================================================
# MLOps Pipeline Orchestration Script
# Stages: prepare → train → validate → publish → deploy
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Environment variables with defaults
# -----------------------------------------------------------------------------
EPOCHS=${EPOCHS:-5}
BATCH_SIZE=${BATCH_SIZE:-32}
THRESHOLD=${THRESHOLD:-0.30}
TRAIN_RECORDS=${TRAIN_RECORDS:-20000}
VAL_RECORDS=${VAL_RECORDS:-2000}
OUTPUT_DIR=${OUTPUT_DIR:-data/processed}
ARTIFACTS_DIR=${ARTIFACTS_DIR:-artifacts}
API_URL=${API_URL:-http://localhost:8000}
GIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

PIPELINE_START_TIME=$(date +%s)

# -----------------------------------------------------------------------------
# Logging helpers
# -----------------------------------------------------------------------------
log_stage() {
    local stage_num="$1"
    local stage_name="$2"
    echo ""
    echo "============================================================"
    echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] STAGE ${stage_num}: ${stage_name}"
    echo "============================================================"
}

log_info() {
    echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] INFO  $*"
}

log_error() {
    echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] ERROR $*" >&2
}

log_warn() {
    echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] WARN  $*"
}

log_done() {
    local stage_name="$1"
    echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] DONE  ${stage_name}"
}

# -----------------------------------------------------------------------------
# Stage 1 — Prepare Dataset
# -----------------------------------------------------------------------------
log_stage 1 "Prepare Dataset"
log_info "OUTPUT_DIR=${OUTPUT_DIR}  TRAIN_RECORDS=${TRAIN_RECORDS}  VAL_RECORDS=${VAL_RECORDS}"

OUTPUT_DIR="${OUTPUT_DIR}" \
TRAIN_RECORDS="${TRAIN_RECORDS}" \
VAL_RECORDS="${VAL_RECORDS}" \
    docker compose --profile prepare up --build

log_done "Prepare Dataset"

# -----------------------------------------------------------------------------
# Stage 2 — Train
# The train container prints several progress lines, then a final JSON summary
# on the last stdout line. We capture that last line and extract run_id from it.
# -----------------------------------------------------------------------------
log_stage 2 "Train"
log_info "EPOCHS=${EPOCHS}  BATCH_SIZE=${BATCH_SIZE}  THRESHOLD=${THRESHOLD}  GIT_SHA=${GIT_SHA}"

TRAIN_OUTPUT=$(
    EPOCHS="${EPOCHS}" \
    BATCH_SIZE="${BATCH_SIZE}" \
    THRESHOLD="${THRESHOLD}" \
    TRAIN_RECORDS="${TRAIN_RECORDS}" \
    VAL_RECORDS="${VAL_RECORDS}" \
    OUTPUT_DIR="${OUTPUT_DIR}" \
    ARTIFACTS_DIR="${ARTIFACTS_DIR}" \
    GIT_SHA="${GIT_SHA}" \
        docker compose --profile train up --exit-code-from train 2>/dev/null \
    | tail -1
)

if [[ -z "${TRAIN_OUTPUT}" ]]; then
    log_error "No output captured from the train container."
    exit 1
fi

log_info "Train output (last line): ${TRAIN_OUTPUT}"

RUN_ID=$(python3 -c "
import sys, json
try:
    data = json.loads(sys.stdin.read())
    print(data['run_id'])
except Exception as e:
    sys.exit(f'Failed to parse train JSON: {e}')
" <<< "${TRAIN_OUTPUT}")

if [[ -z "${RUN_ID}" ]]; then
    log_error "Could not extract run_id from train output."
    exit 1
fi

log_info "run_id=${RUN_ID}"
log_done "Train"

# -----------------------------------------------------------------------------
# Stage 3 — Validate
# -----------------------------------------------------------------------------
log_stage 3 "Validate"
log_info "run_id=${RUN_ID}  threshold=${THRESHOLD}"

if ! python3 pipeline/validate.py --run_id "${RUN_ID}" --threshold "${THRESHOLD}"; then
    log_error "Validation failed for run_id=${RUN_ID} (metric below threshold=${THRESHOLD})."
    log_error "Aborting pipeline. Artifacts preserved at ${ARTIFACTS_DIR}/${RUN_ID}/"
    exit 1
fi

log_done "Validate"

# -----------------------------------------------------------------------------
# Stage 4 — Publish
# -----------------------------------------------------------------------------
log_stage 4 "Publish"
log_info "run_id=${RUN_ID}  git_sha=${GIT_SHA}  epochs=${EPOCHS}  threshold=${THRESHOLD}"

python3 pipeline/publish.py \
    --run_id "${RUN_ID}" \
    --git_sha "${GIT_SHA}" \
    --epochs "${EPOCHS}" \
    --threshold "${THRESHOLD}" \
    --artifacts_dir "${ARTIFACTS_DIR}"

log_done "Publish"

# -----------------------------------------------------------------------------
# Stage 5 — Deploy (API reload)
# Non-fatal: API may not be running in all environments.
# -----------------------------------------------------------------------------
log_stage 5 "Deploy"
log_info "Calling ${API_URL}/reload for run_id=${RUN_ID}"

RELOAD_RESPONSE=$(
    curl -s -X POST "${API_URL}/reload" \
        -H "Content-Type: application/json" \
        -d "{\"run_id\": \"${RUN_ID}\"}" \
    2>/dev/null || true
)

if echo "${RELOAD_RESPONSE}" | python3 -c "
import sys, json
try:
    data = json.loads(sys.stdin.read())
    assert data.get('status') == 'reloaded', f'unexpected status: {data}'
    sys.exit(0)
except Exception as e:
    sys.exit(1)
" 2>/dev/null; then
    log_info "API reloaded successfully. Response: ${RELOAD_RESPONSE}"
else
    log_warn "API reload did not confirm 'reloaded' status. Response: ${RELOAD_RESPONSE:-<no response>}"
    log_warn "Continuing — API may not be running in this environment."
fi

log_done "Deploy"

# -----------------------------------------------------------------------------
# Final summary
# -----------------------------------------------------------------------------
METRICS_FILE="${ARTIFACTS_DIR}/${RUN_ID}/metrics.json"
METRIC_VALUE="N/A"
if [[ -f "${METRICS_FILE}" ]]; then
    METRIC_VALUE=$(python3 -c "
import json, sys
data = json.load(open('${METRICS_FILE}'))
print(data.get('val_token_accuracy', 'N/A'))
")
fi

PIPELINE_END_TIME=$(date +%s)
ELAPSED=$(( PIPELINE_END_TIME - PIPELINE_START_TIME ))
ELAPSED_MIN=$(( ELAPSED / 60 ))
ELAPSED_SEC=$(( ELAPSED % 60 ))

echo ""
echo "============================================================"
echo "  PIPELINE SUMMARY"
echo "============================================================"
echo "  run_id        : ${RUN_ID}"
echo "  metric_value  : ${METRIC_VALUE}  (val_token_accuracy)"
echo "  threshold     : ${THRESHOLD}"
echo "  git_sha       : ${GIT_SHA}"
echo "  elapsed       : ${ELAPSED_MIN}m ${ELAPSED_SEC}s"
echo "  artifacts     : ${ARTIFACTS_DIR}/${RUN_ID}/"
echo "  published     : ${ARTIFACTS_DIR}/published/${RUN_ID}/"
echo "============================================================"
