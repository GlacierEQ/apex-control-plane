#!/usr/bin/env bash
# Always Free Ampere A1 plant. No PAYG. No exhibits. No temporal 4/24 script.
# Exit 0 planted/already-running, 2 retryable (capacity/429), 1 hard error.
set -euo pipefail
export SUPPRESS_LABEL_WARNING=True
export OCI_CLI_SUPPRESS_FILE_PERMISSIONS_WARNING=True

TEN=$(awk -F= '/^tenancy=/{print $2}' "${HOME}/.oci/config")
IMAGE=ocid1.image.oc1.mx-monterrey-1.aaaaaaaahbj4xkqewxrcusebdpe6rleyklxszasyqwqc52h7az6ewbecrova
AD='Jmyy:MX-MONTERREY-1-AD-1'
SUBNET=ocid1.subnet.oc1.mx-monterrey-1.aaaaaaaafmj4gluro7zn7acl63oamopcjv77sz4m6sztccczhsvp53nyttwa
UDATA="$(cd "$(dirname "$0")" && pwd)/cloud_init_arm_runner.sh"
KEY="${HOME}/.ssh/glacier_agent_ed25519.pub"
NAME=glacier-agent-arm
WORKDIR=/tmp/ampere-plant
mkdir -p "$WORKDIR"
LIST="${WORKDIR}/instances.json"
LOCK=/tmp/ampere_plant.lock
LOCKDIR="${LOCK}.dir"
# macOS has no flock(1). mkdir is atomic; stale pid is cleaned.
if command -v flock >/dev/null 2>&1; then
  exec 9>"$LOCK"
  if ! flock -n 9; then
    echo "LOCKED another plant in flight"
    exit 2
  fi
else
  if ! mkdir "$LOCKDIR" 2>/dev/null; then
    old=$(cat "${LOCKDIR}/pid" 2>/dev/null || true)
    if [[ -n "${old}" ]] && kill -0 "${old}" 2>/dev/null; then
      echo "LOCKED another plant in flight pid=${old}"
      exit 2
    fi
    rm -rf "$LOCKDIR"
    if ! mkdir "$LOCKDIR" 2>/dev/null; then
      echo "LOCKED another plant in flight"
      exit 2
    fi
  fi
  echo $$ >"${LOCKDIR}/pid"
  trap 'rm -rf "$LOCKDIR"' EXIT INT TERM
fi

have_running() {
  oci compute instance list --compartment-id "$TEN" --lifecycle-state RUNNING --output json >"$LIST"
  python3 -c '
import json, sys
from pathlib import Path
d = json.loads(Path(sys.argv[1]).read_text())
name = sys.argv[2]
for i in d.get("data") or []:
    if i.get("display-name") == name and i.get("lifecycle-state") == "RUNNING":
        cfg = i.get("shape-config") or {}
        print("FOUND", i.get("shape"), cfg.get("ocpus"), cfg.get("memory-in-gbs"), i.get("fault-domain"), (i.get("id") or "")[:52])
        raise SystemExit(0)
print("NONE")
raise SystemExit(1)
' "$LIST" "$NAME"
}

launch_one() {
  local ocpu="$1" mem="$2"
  local tag="${ocpu}_${mem}"
  local out="${WORKDIR}/launch_${tag}.json"
  local err="${WORKDIR}/launch_${tag}.err"
  local ts
  ts=$(date -u +%FT%TZ)
  : >"$out"
  set +e
  oci compute instance launch \
    --availability-domain "$AD" \
    --compartment-id "$TEN" \
    --shape VM.Standard.A1.Flex \
    --shape-config "{\"ocpus\":${ocpu},\"memoryInGBs\":${mem}}" \
    --display-name "$NAME" \
    --subnet-id "$SUBNET" \
    --assign-public-ip true \
    --image-id "$IMAGE" \
    --ssh-authorized-keys-file "$KEY" \
    --user-data-file "$UDATA" \
    --boot-volume-size-in-gbs 50 \
    --freeform-tags '{"role":"always-free-survivor","arch":"arm64"}' \
    --output json >"$out" 2>"$err"
  local launch_rc=$?
  # stay +e-off: `return 2` under set -e aborts the script and skips the 1/6 foothold
  if [[ $launch_rc -eq 0 && -s "$out" ]]; then
    python3 -c '
import json, sys
from pathlib import Path
d = json.loads(Path(sys.argv[1]).read_text())
data = d.get("data") or d
print("LAUNCHED", data.get("lifecycle-state"), data.get("shape"), (data.get("id") or "")[:52])
Path("/tmp/ampere_id.txt").write_text(data.get("id") or "")
' "$out"
    return 0
  fi
  local body
  body=$(cat "$err" 2>/dev/null || true)
  if grep -qiE 'Out of host capacity|Out of capacity|TooManyRequests|Too many requests' <<<"$body"; then
    echo "RETRYABLE ocpu=${ocpu} mem=${mem} ts=${ts}"
    echo "$body" | python3 -c 'import sys,re; t=sys.stdin.read(); m=re.search(r"\"(code|message)\":\s*\"([^\"]+)\"", t); print("why", m.group(0) if m else t[:180].replace("\n"," "))'
    return 2
  fi
  echo "HARD_FAIL ocpu=${ocpu} mem=${mem} ts=${ts}"
  echo "$body" | head -c 1200
  return 1
}

echo "PLANT_TRY ts=$(date -u +%FT%TZ)"
set +e
have_running
hr=$?
set -e
if [[ $hr -eq 0 ]]; then
  echo "ALREADY_RUNNING"
  exit 0
fi

set +e
launch_one 2 12
rc=$?
set -e
if [[ $rc -eq 0 ]]; then
  exit 0
fi
if [[ $rc -eq 1 ]]; then
  exit 1
fi

set +e
launch_one 1 6
rc=$?
set -e
exit "$rc"
