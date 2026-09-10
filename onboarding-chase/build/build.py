"""Writes Onboarding-Chase.json.

This script is the source of truth. Edit it and re-run it:

    python build/build.py

Do not hand-edit the JSON - the next run overwrites it. If the workflow is ever
changed inside n8n and re-exported, this script and that file have diverged and
one of them has to win.

Demo-mode rules (see ../../BUILD-RULES.md): built-in n8n nodes only, no Code nodes,
fewest nodes that still tell the story, n8n's own pinned data instead of a
hand-built demo toggle, and OpenAI for every AI step.

The chase policy is written twice on purpose - once as an n8n expression that
runs on the canvas, and once in Python at the bottom of this file, which checks
all eight sample clients land where the README says they do.
"""
import json, os, re, datetime, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "sample-onboardings.json")
OUT = os.path.join(ROOT, "Onboarding-Chase.json")

d = json.load(open(DATA, encoding="utf-8"))
pr = d["practice"]
RUN = d["today"]
ITEMS = d["required_items"]

# The whole policy, in the two numbers it turns on.
GAP = 3       # minimum days between nudges
LADDER = 3    # nudges before a person takes over

nodes = []


def add(name, ntype, tv, params, pos, disabled=False):
    n = {"parameters": params, "id": "e8000000-0000-4000-8000-%012d" % (len(nodes) + 1),
         "name": name, "type": ntype, "typeVersion": tv, "position": list(pos)}
    if disabled:
        n["disabled"] = True
    nodes.append(n)
    return name


def sticky(content, pos, w, h, color=7):
    add("Note " + str(len([n for n in nodes if n["type"].endswith("stickyNote")]) + 1),
        "n8n-nodes-base.stickyNote", 1,
        {"content": content, "height": h, "width": w, "color": color}, pos)


def cond(cid, left, op_type, op, right=None, single=False):
    c = {"id": cid, "leftValue": left, "rightValue": "" if right is None else right,
         "operator": {"type": op_type, "operation": op}}
    if single:
        c["operator"]["singleValue"] = True
    return c


def rule(conditions, label, combinator="and"):
    return {"conditions": {
        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose",
                    "version": 2},
        "conditions": conditions, "combinator": combinator},
        "renameOutput": True, "outputKey": label}


def sets(assignments, include_others=True):
    return {"includeOtherFields": include_others,
            "assignments": {"assignments": [
                {"id": "a%d" % i, "name": n, "type": t, "value": v}
                for i, (n, t, v) in enumerate(assignments, 1)]},
            "options": {}}


# ------------------------------------------------------------------ sticky notes
sticky("""## What this does

Eight new clients owe the practice paperwork. Every weekday morning this looks
at where each one stands and decides **one thing per client**: nudge them, leave
them alone, or hand them to a person.

It runs again tomorrow and decides again. **Nothing waits inside the workflow.**

Today: three nudged, one closed off, one escalated, three deliberately left
alone - and every one of those decisions is written down.""",
       (-1900, -460), 460, 300, 4)

sticky("""## Why there is no Wait node

The obvious build is: send the request, **Wait** three days, send a reminder,
**Wait** four more. One tidy line on the canvas.

It is a trap. That execution sits open for a fortnight, and any n8n restart,
upgrade or crash silently loses every pending chase. Nobody finds out until a
client says they were never contacted - and by then there is no record of what
happened, which in a regulated practice is worse than the missed chase.

**The workflow stays stateless. The tracker is what is stateful.** A schedule
re-reads the truth every morning and decides fresh. It survives a restart
because there is nothing in flight to lose.

The weekend rule is not a node either - it is the cron expression on the
trigger, `0 9 * * 1-5`.""",
       (-1400, -460), 500, 380, 3)

sticky("""## Evidence, not status

`Record What Happened` is **append-only**. Nothing in it is ever updated,
because a row that can be edited is not evidence.

Note what gets recorded: **the decisions not to act.** "Considered, not chased,
because they replied yesterday" is a row. A silent gap in the log looks
identical to nobody bothering, and that is the difference between an activity
log and something a supervisory body will accept.

A status field tells you where you are. An audit trail tells you how you got
there. Only the second one survives an inspection.

**Four nodes are greyed out** - nothing sends, closes or records until you
switch them on.""",
       (-880, -460), 470, 360, 6)

# ------------------------------------------------------------------ 1. trigger
t = add("Every Weekday Morning", "n8n-nodes-base.scheduleTrigger", 1.2, {
    "rule": {"interval": [{"field": "cronExpression", "expression": "0 9 * * 1-5"}]},
}, (-1880, 120))

n_track = add("Onboarding Tracker", "n8n-nodes-base.googleSheets", 4.5, {
    "documentId": {"__rl": True, "value": "YOUR_GOOGLE_SHEET_ID_HERE", "mode": "id"},
    "sheetName": {"__rl": True, "value": "Onboarding", "mode": "name"},
    "options": {},
}, (-1660, 120))

# ------------------------------------------------------------------ 2. where each one stands
def days_since(field):
    return ("($json.%s ? Math.round(DateTime.fromISO('%s')"
            ".diff(DateTime.fromISO($json.%s), 'days').days) : 9999)" % (field, RUN, field))


PAIRS = "[" + ", ".join("[%s, $json.%s]" % (json.dumps(label), key)
                        for key, label in ITEMS) + "]"

n_stand = add("Work Out Where Each One Stands", "n8n-nodes-base.set", 3.4, sets([
    ("outstanding", "string",
     "={{ %s.filter(i => !i[1]).map(i => i[0]).join(', ') }}" % PAIRS),
    ("outstanding_count", "number", "={{ %s.filter(i => !i[1]).length }}" % PAIRS),
    ("received", "string",
     "={{ %s.filter(i => i[1]).map(i => i[0]).join(', ') }}" % PAIRS),
    ("days_since_request", "number",
     "={{ Math.round(DateTime.fromISO('%s').diff("
     "DateTime.fromISO($json.requested_on), 'days').days) }}" % RUN),
    ("days_since_last_chase", "number", "={{ %s }}" % days_since("last_chased_on")),
    ("days_since_reply", "number", "={{ %s }}" % days_since("last_reply_on")),
    ("chase_number", "number", "={{ $json.chase_count + 1 }}"),
]), (-1440, 120))

# ------------------------------------------------------------------ 3. the policy
# The entire chase policy, readable top to bottom. This is the node to open on
# a call - an accountant can check it without knowing what n8n is.
POLICY = """={{
  $json.outstanding_count === 0                                    ? 'Everything is in'
  : $json.days_since_reply <= 1                                    ? 'They replied yesterday'
  : ($json.chase_count >= %d && $json.days_since_last_chase >= %d) ? 'Three nudges and no answer'
  : $json.days_since_last_chase < %d                               ? 'Too soon since the last nudge'
  : $json.days_since_request < %d                                  ? 'Only just asked'
  :                                                                  'Time for a nudge'
}}""" % (LADDER, GAP, GAP, GAP)

n_policy = add("What Does the Policy Say?", "n8n-nodes-base.set", 3.4, sets([
    ("todays_decision", "string", POLICY),
]), (-1220, 120))

DECISIONS = ["Everything is in", "They replied yesterday", "Three nudges and no answer",
             "Too soon since the last nudge", "Only just asked"]

n_switch = add("What Happens Today?", "n8n-nodes-base.switch", 3.2, {
    "rules": {"values": [
        rule([cond("d%d" % i, "={{ $json.todays_decision }}", "string", "equals", label)],
             label)
        for i, label in enumerate(DECISIONS, 1)
    ]},
    "options": {"fallbackOutput": "extra", "renameFallbackOutput": "Time for a nudge"},
}, (-1000, 120))

# ------------------------------------------------------------------ 4. the lanes
n_close = add("Close the File", "n8n-nodes-base.googleSheets", 4.5, {
    "operation": "appendOrUpdate",
    "documentId": {"__rl": True, "value": "YOUR_GOOGLE_SHEET_ID_HERE", "mode": "id"},
    "sheetName": {"__rl": True, "value": "Onboarding", "mode": "name"},
    "columns": {"mappingMode": "defineBelow", "matchingColumns": ["client_id"], "value": {
        "client_id": "={{ $json.client_id }}",
        "status": "Complete - ready for partner sign-off",
        "completed_on": RUN,
    }},
    "options": {},
}, (-740, -140), disabled=True)

# The three "not today" exits all land here. Doing nothing is still a decision,
# and it still gets written down.
n_hold = add("Nothing to Do Today", "n8n-nodes-base.noOp", 1, {}, (-740, 380))

n_model = add("OpenAI Chat Model", "@n8n/n8n-nodes-langchain.lmChatOpenAi", 1.2, {
    "model": {"__rl": True, "value": "gpt-4.1-mini", "mode": "list",
              "cachedResultName": "gpt-4.1-mini"},
    "options": {"temperature": 0.3},
}, (-700, 420))

n_write = add("Write the Reminder", "@n8n/n8n-nodes-langchain.chainLlm", 1.4, {
    "promptType": "define",
    "text": "=" + """Write one short reminder email to a client of """ + pr["name"] + """ who
still owes us onboarding paperwork.

contact first name: {{ $json.contact_name.split(' ')[0] }}
still outstanding: {{ $json.outstanding }}
already received: {{ $json.received }}
this is reminder number: {{ $json.chase_number }}
days since we first asked: {{ $json.days_since_request }}
upload link: """ + pr["portal"] + """{{ $json.client_id }}
sign off as: {{ $json.account_owner }}

Rules:
- Name every outstanding item, exactly as listed above. Never ask for anything already received,
  and open by thanking them for what has come in when the list is not empty.
- Reminder 1 is light. Reminder 2 notes the delay plainly. Reminder 3 explains the real reason
  we keep asking: we are required to complete client due diligence before any work can begin on
  their affairs, so nothing can move forward until the documents are with us. That is a fact,
  not a threat - write it as one.
- Never invent a deadline, a fee, a penalty or a consequence that was not agreed.
- Offer one easy next step: the upload link, and an invitation to say if something is holding
  it up.
- Under 120 words. No exclamation marks, no chasing language like "urgent" or "final notice".
  Write the way a practice writes to a client it wants to keep.
- Return the body only, with no subject line.""",
    "messages": {"messageValues": []},
}, (-740, 120))

n_send = add("Send the Reminder", "n8n-nodes-base.gmail", 2.1, {
    "sendTo": "={{ $('What Does the Policy Say?').item.json.contact_email }}",
    "subject": "=Outstanding paperwork for your "
               "{{ $('What Does the Policy Say?').item.json.client_name }} onboarding",
    "emailType": "text",
    "message": "={{ $json.text }}",
    "options": {},
}, (-480, 120), disabled=True)

n_escalate = add("Hand It to the Account Owner", "n8n-nodes-base.slack", 2.3, {
    "select": "channel",
    "channelId": {"__rl": True, "value": pr["review_channel"], "mode": "name"},
    "text": ("=*Automatic chasing has stopped* - {{ $json.client_name }} "
             "({{ $json.client_id }})\n"
             "{{ $json.chase_count }} reminders sent, {{ $json.days_since_request }} days "
             "since we first asked, nothing received.\n"
             "Still outstanding: {{ $json.outstanding }}\n"
             "*{{ $json.account_owner }}* - this one needs a phone call."),
    "otherOptions": {},
}, (-740, 620), disabled=True)

# ------------------------------------------------------------------ 5. the evidence
P = "What Does the Policy Say?"


def g(name):
    return "$('" + P + "').item.json." + name


DETAIL = ("={{ " + g("todays_decision") + " === 'Time for a nudge'"
          " ? ('Reminder ' + " + g("chase_number") + " + ' sent to ' + " + g("contact_email") +
          ")"
          " : " + g("todays_decision") + " === 'Everything is in'"
          " ? 'All five items received. File closed for partner sign-off.'"
          " : " + g("todays_decision") + " === 'Three nudges and no answer'"
          " ? ('Chasing stopped after ' + " + g("chase_count") +
          " + ' reminders. Passed to ' + " + g("account_owner") + ")"
          " : ('Considered and not chased: ' + " + g("todays_decision") + ".toLowerCase())"
          " }}")

n_evidence = add("Record What Happened", "n8n-nodes-base.googleSheets", 4.5, {
    "operation": "append",
    "documentId": {"__rl": True, "value": "YOUR_GOOGLE_SHEET_ID_HERE", "mode": "id"},
    "sheetName": {"__rl": True, "value": "Evidence Trail", "mode": "name"},
    "columns": {"mappingMode": "defineBelow", "value": {
        "Timestamp": "={{ $now.toISO() }}",
        "Client": "={{ " + g("client_name") + " }}",
        "Reference": "={{ " + g("client_id") + " }}",
        "Decision": "={{ " + g("todays_decision") + " }}",
        "Detail": DETAIL,
        "Still Outstanding": "={{ " + g("outstanding") + " || 'nothing' }}",
        "Days Since Request": "={{ " + g("days_since_request") + " }}",
        "Reminders Sent": "={{ " + g("chase_count") + " }}",
        "Decided By": "={{ " + g("todays_decision") + " === 'Three nudges and no answer'"
                      " ? ('Rule, then handed to ' + " + g("account_owner") + ")"
                      " : 'Automatic - onboarding chase rule' }}",
    }},
    "options": {},
}, (-220, 120), disabled=True)

# ------------------------------------------------------------------ connections
connections = {}


def wire(src, dst, si=0, di=0, kind="main"):
    c = connections.setdefault(src, {}).setdefault(kind, [])
    while len(c) <= si:
        c.append([])
    c[si].append({"node": dst, "type": kind, "index": di})


wire(t, n_track)
wire(n_track, n_stand)
wire(n_stand, n_policy)
wire(n_policy, n_switch)
wire(n_switch, n_close, 0)              # Everything is in
wire(n_switch, n_hold, 1)               # They replied yesterday
wire(n_switch, n_escalate, 2)           # Three nudges and no answer
wire(n_switch, n_hold, 3)               # Too soon since the last nudge
wire(n_switch, n_hold, 4)               # Only just asked
wire(n_switch, n_write, 5)              # fallback: time for a nudge
wire(n_model, n_write, 0, 0, "ai_languageModel")
wire(n_write, n_send)
wire(n_close, n_evidence)
wire(n_hold, n_evidence)
wire(n_escalate, n_evidence)
wire(n_send, n_evidence)

# ------------------------------------------------------------------ pinned data
TRACKER_FIELDS = (["client_id", "client_name", "contact_name", "contact_email",
                   "account_owner", "requested_on"] + [k for k, _ in ITEMS] +
                  ["last_chased_on", "chase_count", "last_reply_on"])

pin_data = {
    n_track: [{"json": {k: c[k] for k in TRACKER_FIELDS}} for c in d["clients"]],
    n_write: [{"json": {"text": d["demo_reminders"][c["client_id"]]}}
              for c in d["clients"] if c["expected"] == "Time for a nudge"],
}

wf = {"name": "Onboarding Chase and Evidence", "nodes": nodes, "connections": connections,
      "pinData": pin_data, "settings": {"executionOrder": "v1"},
      "meta": {"instanceId": "automatoys-ai-demo"}, "tags": []}

with open(OUT, "w", encoding="utf-8") as f_out:
    json.dump(wf, f_out, indent=2, ensure_ascii=False)

# ------------------------------------------------------------------ the one check
names = {n["name"] for n in nodes}
errors = []
if len(names) != len(nodes):
    errors.append("duplicate node names")
for src, kinds in connections.items():
    if src not in names:
        errors.append("connection from a node that does not exist: " + src)
    for kind, outs in kinds.items():
        for out in outs:
            for link in out:
                if link["node"] not in names:
                    errors.append("connection to a node that does not exist: " + link["node"])
for pinned in pin_data:
    if pinned not in names:
        errors.append("pinned data for a node that does not exist: " + pinned)

# Every node name referenced inside an expression must be a real node.
# Deliberately naive: it takes whatever sits between $(' and the next quote. An
# apostrophe in a node name breaks that, which is the point - a name needing an
# escape is a name waiting to break something, so it should fail here.
for n in nodes:
    for ref in re.findall(r"\$\('(.*?)'\)", json.dumps(n["parameters"])):
        if ref not in names:
            errors.append("%s refers to a node that does not exist: %r "
                          "(check for an apostrophe in the node name)" % (n["name"], ref))

reachable = {t}
changed = True
while changed:
    changed = False
    for src, kinds in connections.items():
        if src in reachable:
            for outs in kinds.values():
                for out in outs:
                    for link in out:
                        if link["node"] not in reachable:
                            reachable.add(link["node"])
                            changed = True
reachable.add(n_model)  # sub-nodes hang off a root node rather than the main flow
orphans = [n["name"] for n in nodes
           if n["type"] != "n8n-nodes-base.stickyNote" and n["name"] not in reachable]
if orphans:
    errors.append("nothing reaches: " + ", ".join(orphans))

blob = json.dumps(wf).lower()
for banned in ("anthropic", "claude"):
    if banned in blob:
        errors.append("provider leak: '%s' appears in the workflow" % banned)

code_nodes = [n for n in nodes if n["type"] == "n8n-nodes-base.code"]
if code_nodes:
    errors.append("Code nodes present: " + ", ".join(n["name"] for n in code_nodes))

# ---- the same policy, run here in Python against the same pinned data.
# Every named exit of the Switch has to be reachable, and every client has to
# land where sample-onboardings.json says it does.
run = datetime.date.fromisoformat(RUN)
if run.weekday() >= 5:
    errors.append("the fixed run date %s is a weekend, and the trigger only runs "
                  "Monday to Friday" % RUN)


def gap(value):
    return 9999 if not value else (run - datetime.date.fromisoformat(value)).days


tally, rows = {}, []
for c in d["clients"]:
    missing = [label for key, label in ITEMS if not c[key]]
    since_req = gap(c["requested_on"])
    since_chase = gap(c["last_chased_on"])
    since_reply = gap(c["last_reply_on"])
    if not missing:
        got = "Everything is in"
    elif since_reply <= 1:
        got = "They replied yesterday"
    elif c["chase_count"] >= LADDER and since_chase >= GAP:
        got = "Three nudges and no answer"
    elif since_chase < GAP:
        got = "Too soon since the last nudge"
    elif since_req < GAP:
        got = "Only just asked"
    else:
        got = "Time for a nudge"
    if got != c["expected"]:
        errors.append("%s should be %r but the dates make it %r"
                      % (c["client_id"], c["expected"], got))
    tally[got] = tally.get(got, 0) + 1
    rows.append((c["client_id"], since_req, c["chase_count"], len(missing), got))

for label in DECISIONS + ["Time for a nudge"]:
    if label not in tally:
        errors.append("no sample client reaches the %r exit" % label)

# A reminder is pinned for every client being nudged, and for nobody else.
nudged = {c["client_id"] for c in d["clients"] if c["expected"] == "Time for a nudge"}
if set(d["demo_reminders"]) != nudged:
    errors.append("pinned reminders %s do not match the clients being nudged %s"
                  % (sorted(d["demo_reminders"]), sorted(nudged)))
# The reminder has to name every outstanding item - "please send your documents"
# to someone who has sent four of five is how a cooperative client is lost. And
# the sentence doing the asking must not contain anything already on file.
ASKING = re.compile(r"still need|outstanding|last thing|we need", re.I)
for c in d["clients"]:
    if c["client_id"] not in nudged:
        continue
    body = d["demo_reminders"][c["client_id"]]
    # Split on sentence ends only - a colon separates "we still need three
    # things:" from the list itself, and the list is the part that matters.
    asks = [x for x in re.split(r"(?<=[.!?])\s+", body) if ASKING.search(x)]
    if not asks:
        errors.append("%s reminder never actually asks for anything" % c["client_id"])
        continue
    ask = " ".join(asks).lower()
    for key, label in ITEMS:
        if not c[key] and label.lower() not in ask:
            errors.append("%s reminder does not name the outstanding %r"
                          % (c["client_id"], label))
        if c[key] and label.lower() in ask:
            errors.append("%s asks for %r in the same breath as the outstanding "
                          "items, and it is already on file" % (c["client_id"], label))

functional = [n for n in nodes if n["type"] != "n8n-nodes-base.stickyNote"]
print("nodes: %d functional (+%d notes) | Code nodes: %d | pinned: %d | disabled: %d"
      % (len(functional), len(nodes) - len(functional), len(code_nodes), len(pin_data),
         len([n for n in nodes if n.get("disabled")])))
print("run date %s (%s) | clients: %d" % (RUN, run.strftime("%A"), len(d["clients"])))
print("%-8s %5s %7s %8s  %s" % ("client", "days", "chased", "missing", "decision"))
for r in rows:
    print("%-8s %5d %7d %8d  %s" % r)
print("VALIDATION:", "PASS" if not errors else "FAIL")
for e in errors:
    print("  -", e)
# ---- which node versions has no other demo confirmed? See ../node_versions.py.
sys.path.insert(0, os.path.dirname(ROOT))
from node_versions import unverified                                   # noqa: E402
unconfirmed = unverified(OUT)
if unconfirmed:
    print("node versions no other demo uses - open these first on import:")
    for v in unconfirmed:
        print("   ", v)

print("wrote", OUT)
