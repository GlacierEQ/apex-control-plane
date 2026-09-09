#!/usr/bin/env bash
# Retry Always Free Ampere plant until RUNNING or trial end. No PAYG.
set -euo pipefail
export SUPPRESS_LABEL_WARNING=True
DIR="$(cd "$(dirname "$0")" && pwd)"
PLANT="${DIR}/plant_ampere_always_free.sh"
STATUS="/tmp/ampere_retry_status.txt"
LOG="/tmp/ampere_retry.log"
USB="/Volumes/ANTIGRAVITY_MEMORY_01/Mac_Offload/oci-glacier-agent-20260903/glacier-artifacts"
DEADLINE=$(date -u -j -f '%Y-%m-%dT%H:%M:%SZ' '2026-09-10T23:59:59Z' +%s 2>/dev/null || date -u -d '2026-09-10T23:59:59Z' +%s)
SLEEP_SEC="${AMPERE_RETRY_SLEEP:-900}"

append_usb() {
  local line="$1"
  mkdir -p "$USB" 2>/dev/null || true
  if [[ -d "$USB" ]]; then
    echo "$line" >>"${USB}/ampere-retry.jsonl"
  fi
}

: >"$STATUS"
echo "RETRY_START ts=$(date -u +%FT%TZ) sleep=${SLEEP_SEC}" | tee -a "$LOG"
while :; do
  now=$(date -u +%s)
  if (( now >= DEADLINE )); then
    echo "DEADLINE ts=$(date -u +%FT%TZ)" | tee "$STATUS" | tee -a "$LOG"
    append_usb "{\"ts\":\"$(date -u +%FT%TZ)\",\"event\":\"deadline\"}"
    exit 3
  fi
  set +e
  "$PLANT"
  rc=$?
  set -e
  echo "ATTEMPT rc=${rc} ts=$(date -u +%FT%TZ)" | tee -a "$LOG"
  append_usb "{\"ts\":\"$(date -u +%FT%TZ)\",\"event\":\"attempt\",\"rc\":${rc}}"
  if [[ $rc -eq 0 ]]; then
    echo "PLANTED ts=$(date -u +%FT%TZ)" | tee "$STATUS" | tee -a "$LOG"
    append_usb "{\"ts\":\"$(date -u +%FT%TZ)\",\"event\":\"planted\"}"
    exit 0
  fi
  if [[ $rc -eq 1 ]]; then
    echo "HARD_FAIL ts=$(date -u +%FT%TZ)" | tee "$STATUS" | tee -a "$LOG"
    append_usb "{\"ts\":\"$(date -u +%FT%TZ)\",\"event\":\"hard_fail\"}"
    exit 1
  fi
  echo "CAPACITY_WAIT sleep=${SLEEP_SEC} ts=$(date -u +%FT%TZ)" | tee -a "$LOG"
  sleep "$SLEEP_SEC"
done
