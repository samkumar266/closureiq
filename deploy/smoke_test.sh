#!/usr/bin/env bash
# Smoke test for demo steps 4 and 5 (approve -> package -> deliveries -> fast-forward escalation).
#
# Usage: deploy/smoke_test.sh [base_url]      (default http://127.0.0.1:8000)
#
# WARNING: this WRITES to the target: it evaluates the first facility, approves
# (or, if the posture is normal operations, overrides to closure with actor
# "smoke-test"), acknowledges one delivery and moves the simulated clock.
# Run it against a local or fresh instance, not the demo database right before
# the pitch. It puts the clock back to system mode at the end.
#
# Needs: bash, curl, python3. Checks status codes and JSON field names against docs/contract.md.
set -u
BASE="${1:-http://127.0.0.1:8000}"
API="$BASE/api"
PASS=0
FAIL=0
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

ok()   { echo "PASS  $1"; PASS=$((PASS + 1)); }
bad()  { echo "FAIL  $1"; FAIL=$((FAIL + 1)); }

# call METHOD PATH [JSON_BODY] -> sets CODE, body in $TMP/body
call() {
  local method="$1" path="$2" body="${3:-}"
  if [ -n "$body" ]; then
    CODE=$(curl -s -o "$TMP/body" -w '%{http_code}' -X "$method" -H 'Content-Type: application/json' -d "$body" "$API$path")
  else
    CODE=$(curl -s -o "$TMP/body" -w '%{http_code}' -X "$method" "$API$path")
  fi
}

# expect_code LABEL CODE...
expect_code() {
  local label="$1"; shift
  for c in "$@"; do [ "$CODE" = "$c" ] && { ok "$label (HTTP $CODE)"; return 0; }; done
  bad "$label (HTTP $CODE, wanted $*): $(head -c 300 "$TMP/body")"; return 1
}

# py EXPR -> evaluates a python expression with `d` = parsed body; prints the result
py() { python3 -c "import json,sys; d=json.load(open('$TMP/body')); print($1)"; }

# keys LABEL PY_OBJECT_EXPR key1 key2 ... -> checks the object has exactly these keys (order ignored)
keys() {
  local label="$1" expr="$2"; shift 2
  local want="$*"
  local missing
  missing=$(python3 -c "
import json
d=json.load(open('$TMP/body'))
o=$expr
want=set('$want'.split())
have=set(o)
print(' '.join(sorted(want-have)) + ('' if want>=have else ' | extra: ' + ' '.join(sorted(have-want))))
" 2>&1)
  if [ -z "$missing" ]; then ok "$label fields"; else bad "$label fields: missing $missing"; fi
}

echo "Smoke test against $API"

# --- health and facilities
call GET /health
expect_code "GET /health" 200 && keys "health" "d" ok data_mode clock last_poll_at

call GET /facilities
expect_code "GET /facilities" 200 || { echo "Cannot continue."; exit 1; }
FACILITY=$(py "(d if isinstance(d, list) else d.get('facilities', []))[0]['facility_id']")
echo "      facility: $FACILITY"

# --- a fresh evaluation
call POST "/facilities/$FACILITY/evaluate"
if expect_code "POST evaluate" 200 503; then
  if [ "$CODE" = "200" ]; then EVAL=$(py "d['evaluation_id']"); POSTURE=$(py "d['posture']")
  else EVAL=$(py "d['error']['detail']['evaluation_id']"); POSTURE=$(curl -s "$API/evaluations/$EVAL" | python3 -c "import json,sys; print(json.load(sys.stdin)['posture'])"); fi
else
  echo "Cannot continue."; exit 1
fi
echo "      evaluation: $EVAL  posture: $POSTURE"

# --- step 4: package preview
call GET "/evaluations/$EVAL/package-preview?posture=closure"
if expect_code "GET package-preview" 200; then
  keys "preview" "d" notification_id evaluation_id approval_id standing_policy preview ack_deadline next_update package deliveries escalation
  [ "$(py "d['preview'] is True and d['notification_id'] is None and d['approval_id'] is None")" = "True" ] \
    && ok "preview is true with null ids" || bad "preview flags"
  [ "$(py "all(set(r) == (set(['employee_id','included','group','reason','message_id','channel_plan']) if r['included'] else set(['employee_id','included','group','reason'])) for r in d['package']['recipients'])")" = "True" ] \
    && ok "recipient fields" || bad "recipient fields"
  [ "$(py "all(set(['id','group','text']) <= set(m) for m in d['package']['messages'])")" = "True" ] \
    && ok "message fields" || bad "message fields"
fi

# --- step 4: approve (override to closure if the live posture is normal, so there are recipients)
if [ "$POSTURE" = "normal_operations" ]; then
  ACTION=override; BODY='{"actor":"smoke-test","posture":"closure","reason":"smoke test: force recipients"}'
else
  ACTION=approve; BODY='{"actor":"smoke-test"}'
fi
call POST "/evaluations/$EVAL/$ACTION" "$BODY"
if expect_code "POST $ACTION" 200; then
  keys "approve response" "d" approval notification_id
  keys "approval" "d['approval']" id evaluation_id action final_posture actor reason acted_at_wall
  NTF=$(py "d['notification_id']")
  echo "      notification: $NTF"
else
  echo "Cannot continue."; exit 1
fi

call POST "/evaluations/$EVAL/approve" '{"actor":"smoke-test"}'
expect_code "second approve is refused" 409 && \
  { [ "$(py "d['error']['code']")" = "already_decided" ] && ok "409 code already_decided" || bad "409 code"; }

# --- step 5: deliveries appear once sim time moves past their send delays
NOW_SIM=$(curl -s "$API/clock" | python3 -c "import json,sys; print(json.load(sys.stdin)['now_sim'])")
plus() { python3 -c "from datetime import datetime,timedelta; print((datetime.fromisoformat('$1'.replace('Z','+00:00'))+timedelta(minutes=$2)).isoformat())"; }
call POST /clock "{\"mode\":\"simulated\",\"speed\":1,\"set_to\":\"$(plus "$NOW_SIM" 2)\"}"
expect_code "POST /clock (+2 min)" 200 && keys "clock" "d" mode now_sim now_wall speed

call GET "/notifications/$NTF"
if expect_code "GET notification" 200; then
  keys "notification" "d" notification_id evaluation_id approval_id standing_policy preview ack_deadline next_update package deliveries escalation
  [ "$(py "len(d['deliveries']) > 0")" = "True" ] && ok "deliveries exist ($(py "len(d['deliveries'])"))" || bad "no deliveries"
  [ "$(py "all(set(x) == set(['delivery_id','recipient_id','channel','real','status','status_at_wall']) for x in d['deliveries'])")" = "True" ] \
    && ok "delivery fields" || bad "delivery fields"
  [ "$(py "all((not x['real']) or x['channel'] == 'email' for x in d['deliveries'])")" = "True" ] \
    && ok "real only on email" || bad "a non-email delivery is marked real"
  [ "$(py "all(x['status'] in ('queued','sent','delivered','simulated','failed','acknowledged') for x in d['deliveries'])")" = "True" ] \
    && ok "delivery statuses valid" || bad "unknown delivery status"
  DLV=$(py "next((x['delivery_id'] for x in d['deliveries'] if x['status']=='delivered'), '')")
fi

if [ -n "${DLV:-}" ]; then
  call POST "/deliveries/$DLV/ack" '{}'
  expect_code "POST ack" 200 && \
    { [ "$(py "d['status']")" = "acknowledged" ] && ok "ack status acknowledged" || bad "ack status"; }
else
  bad "no delivered message to acknowledge"
fi

# --- step 5: fast-forward 30 minutes fires the no-acknowledgment escalation
NOW_SIM=$(curl -s "$API/clock" | python3 -c "import json,sys; print(json.load(sys.stdin)['now_sim'])")
call POST /clock "{\"mode\":\"simulated\",\"speed\":1,\"set_to\":\"$(plus "$NOW_SIM" 30)\"}"
expect_code "POST /clock (+30 min)" 200
call GET "/notifications/$NTF"
if expect_code "GET notification after jump" 200; then
  [ "$(py "all(set(e) == set(['step','label','due_sim','fired_at_sim']) for e in d['escalation'])")" = "True" ] \
    && ok "escalation fields" || bad "escalation fields"
  [ "$(py "any(e['step']=='unacknowledged_to_supervisors' and e['fired_at_sim'] for e in d['escalation'])")" = "True" ] \
    && ok "no-acknowledgment escalation fired" || bad "escalation did not fire: $(py "d['escalation']")"
fi

# --- put the clock back
call POST /clock '{"mode":"system","speed":1}'
expect_code "clock back to system" 200

echo
echo "Passed: $PASS  Failed: $FAIL"
[ "$FAIL" -eq 0 ]
