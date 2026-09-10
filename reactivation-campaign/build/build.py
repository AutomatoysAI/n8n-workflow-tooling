"""Writes Reactivation-Campaign.json.

This script is the source of truth. Edit it and re-run it:

    python build/build.py

Do not hand-edit the JSON - the next run overwrites it. If the workflow is ever
changed inside n8n and re-exported, this script and that file have diverged and
one of them has to win.

Demo-mode rules (see ../../BUILD-RULES.md): built-in n8n nodes only, no Code nodes,
fewest nodes that still tell the story, and n8n's own pinned data instead of a
hand-built demo toggle.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "sample-customers.json")
OUT = os.path.join(ROOT, "Reactivation-Campaign.json")

d = json.load(open(DATA, encoding="utf-8"))
biz = d["business"]
RUN_DATE = d["today"]

nodes = []


def add(name, ntype, tv, params, pos, disabled=False):
    n = {"parameters": params, "id": "e5000000-0000-4000-8000-%012d" % (len(nodes) + 1),
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


# ------------------------------------------------------------------ sticky notes
sticky("""## What this does

A customer list goes in. People you must not or should not contact are taken
out - **with the reason showing on the canvas**. Whoever is left gets a message
written from their own service history, and a person approves it.

**The money is in the suppression list, not the copy.** Anyone can write "we
miss you". Not texting the wrong people is the job.

Ten customers in. Five contacted, five left alone.""",
       (-1560, -400), 460, 300, 4)

sticky("""## Why the SMS node is greyed out

**Text messages are not email.** A marketing text needs prior express written
consent (TCPA - $500 to $1,500 per message), the number has to be registered
with the carriers (A2P 10DLC), STOP has to work, and 8am-9pm is the recipient's
local time, not yours.

Email is far more permissive: CAN-SPAM lets you contact past customers, with an
unsubscribe link and a postal address.

So the Twilio node is **disabled on purpose**. Two things before anyone enables
it: the business can show you its consent records, and 10DLC registration is
done. Building the sender takes ten minutes. Knowing not to fire it is the part
worth paying for.""",
       (-1060, -400), 480, 340, 3)

sticky("""## Running it

`Customer List` and both writing steps have **pinned data**, so the whole thing
runs with no accounts connected. Unpin a node to make it call out for real.

Dates are measured from a fixed run date of """ + RUN_DATE + """ so the demo always
tells the same story. Swap `DateTime.fromISO('""" + RUN_DATE + """')` for `$now` in
*How Long Since We Saw Them* to run it against real dates.""",
       (-560, -400), 440, 260, 6)

# ------------------------------------------------------------------ 1. trigger
t = add("Run the Demo", "n8n-nodes-base.manualTrigger", 1, {}, (-1540, 60))

# ------------------------------------------------------------------ 2. the list
n_list = add("Customer List", "n8n-nodes-base.googleSheets", 4.5, {
    "documentId": {"__rl": True, "value": "YOUR_GOOGLE_SHEET_ID_HERE", "mode": "id"},
    "sheetName": {"__rl": True, "value": "Customers", "mode": "name"},
    "options": {},
}, (-1340, 60))

# ------------------------------------------------------------------ 3. dates
since = ("Math.round(DateTime.fromISO('" + RUN_DATE +
         "').diff(DateTime.fromISO($json.last_service_date), 'days').days)")
months = ("Math.round(DateTime.fromISO('" + RUN_DATE +
          "').diff(DateTime.fromISO($json.last_service_date), 'months').months)")
contact = ("$json.last_contacted_at ? Math.round(DateTime.fromISO('" + RUN_DATE +
           "').diff(DateTime.fromISO($json.last_contacted_at), 'days').days) : 9999")

n_dates = add("How Long Since We Saw Them", "n8n-nodes-base.set", 3.4, {
    "includeOtherFields": True,
    "assignments": {"assignments": [
        {"id": "a1", "name": "days_since_service", "type": "number", "value": "={{ " + since + " }}"},
        {"id": "a2", "name": "months_since_service", "type": "number", "value": "={{ " + months + " }}"},
        {"id": "a3", "name": "days_since_contact", "type": "number", "value": "={{ " + contact + " }}"},
    ]},
    "options": {},
}, (-1140, 60))

# ------------------------------------------------------------------ 4. suppression
n_suppress = add("Who Do We Leave Alone?", "n8n-nodes-base.switch", 3.2, {
    "rules": {"values": [
        rule([cond("s1", "={{ $json.do_not_contact }}", "boolean", "true", single=True)],
             "On the do-not-contact list"),
        rule([cond("s2", "={{ $json.marketing_opt_out }}", "boolean", "true", single=True)],
             "Opted out of marketing"),
        rule([cond("s3", "={{ $json.email }}", "string", "empty", single=True),
              cond("s4", "={{ $json.phone }}", "string", "empty", single=True)],
             "No phone or email on record"),
        rule([cond("s5", "={{ $json.days_since_service }}", "number", "lt", 180)],
             "Came in recently - not dormant"),
        rule([cond("s6", "={{ $json.days_since_contact }}", "number", "lt", 30)],
             "Contacted in the last 30 days"),
    ]},
    "options": {"fallbackOutput": "extra", "renameFallbackOutput": "Worth contacting"},
}, (-900, 60))

n_left = add("Left Alone", "n8n-nodes-base.noOp", 1, {}, (-660, 320))

# ------------------------------------------------------------------ 5. channel
n_channel = add("Text, or Email?", "n8n-nodes-base.switch", 3.2, {
    "rules": {"values": [
        rule([cond("c1", "={{ $json.sms_consent }}", "boolean", "true", single=True),
              cond("c2", "={{ $json.phone_type }}", "string", "equals", "mobile"),
              cond("c3", "={{ $json.days_since_service }}", "number", "lte", 730)],
             "Text - written consent on file"),
    ]},
    "options": {"fallbackOutput": "extra", "renameFallbackOutput": "Email - no consent to text"},
}, (-660, 60))

# ------------------------------------------------------------------ 6. writing
n_model = add("OpenAI Chat Model", "@n8n/n8n-nodes-langchain.lmChatOpenAi", 1.2, {
    "model": {"__rl": True, "value": "gpt-4.1-mini", "mode": "list",
              "cachedResultName": "gpt-4.1-mini"},
    "options": {"temperature": 0.4},
}, (-360, 320))

COMMON = ("""Write one reactivation message for a past customer of {biz}, using only the facts below.

first_name: {{{{ $json.first_name }}}}
vehicle: {{{{ $json.vehicle }}}}
last_service_type: {{{{ $json.last_service_type }}}}
months_since: {{{{ $json.months_since_service }}}}
offer (use exactly, do not improve): {offer}

Reference the specific thing they last had done and roughly how long ago - that is what makes it
worth reading. State the offer once. Give one easy next step.

Never invent a discount, price, deadline, service or anything about their vehicle. No exclamation
marks, no "we miss you", no marketing adjectives. Write like the shop owner would.""")

n_sms = add("Write the Text Message", "@n8n/n8n-nodes-langchain.chainLlm", 1.4, {
    "promptType": "define",
    "text": "=" + COMMON.format(biz=biz["name"], offer=biz["offer"]) + """

THIS ONE IS A TEXT MESSAGE.
Under 300 characters in total. Open with the business name so they know who it is.
End with exactly: Reply STOP to opt out
Return the message only - no subject line, no notes.""",
    "messages": {"messageValues": []},
}, (-400, -60))

n_email = add("Write the Email", "@n8n/n8n-nodes-langchain.chainLlm", 1.4, {
    "promptType": "define",
    "text": "=" + COMMON.format(biz=biz["name"], offer=biz["offer"]) + """

THIS ONE IS AN EMAIL.
Under 120 words. Sign off with the business name.
If they have been gone more than two years, give them an easy way to say they have moved on.
Return the body only - the subject line is added separately.""",
    "messages": {"messageValues": []},
}, (-400, 180))

# ------------------------------------------------------------------ 7. checks
n_check = add("Does the Text Pass?", "n8n-nodes-base.if", 2.2, {
    "conditions": {
        "options": {"caseSensitive": False, "leftValue": "", "typeValidation": "loose",
                    "version": 2},
        "conditions": [
            cond("k1", "={{ $json.text.length }}", "number", "lte", 300),
            cond("k2", "={{ $json.text }}", "string", "contains", "Reply STOP to opt out"),
            cond("k3", "={{ $json.text }}", "string", "notRegex",
                 "\\$(?!30\\b)\\d|\\d+\\s?%"),
        ],
        "combinator": "and",
    },
    "looseTypeValidation": True, "options": {},
}, (-160, -60))

n_held = add("Held for a Human", "n8n-nodes-base.noOp", 1, {}, (80, 60))

# ------------------------------------------------------------------ 8. subject
n_subject = add("Add the Subject Line", "n8n-nodes-base.set", 3.4, {
    "assignments": {"assignments": [
        {"id": "b1", "name": "subject", "type": "string",
         "value": "=Your {{ $('Text, or Email?').item.json.vehicle }} is about due, "
                  "{{ $('Text, or Email?').item.json.first_name }}"},
        {"id": "b2", "name": "body", "type": "string", "value": "={{ $json.text }}"},
        {"id": "b3", "name": "send_to", "type": "string",
         "value": "={{ $('Text, or Email?').item.json.email }}"},
    ]},
    "options": {},
}, (-160, 180))

# ------------------------------------------------------------------ 9. delivery
n_twilio = add("Send the Text", "n8n-nodes-base.twilio", 1, {
    "resource": "sms", "operation": "send",
    "from": biz["sms_from"],
    "to": "={{ $('Text, or Email?').item.json.phone }}",
    "message": "={{ $json.text }}",
    "options": {},
}, (80, -160), disabled=True)

n_gmail = add("Create the Email Draft", "n8n-nodes-base.gmail", 2.1, {
    "resource": "draft",
    "subject": "={{ $json.subject }}",
    "emailType": "text",
    "message": "={{ $json.body }}",
    "options": {"sendTo": "={{ $json.send_to }}"},
}, (80, 180))

# ------------------------------------------------------------------ 10. logs
n_log_out = add("Log Who We Contacted", "n8n-nodes-base.googleSheets", 4.5, {
    "operation": "appendOrUpdate",
    "documentId": {"__rl": True, "value": "YOUR_GOOGLE_SHEET_ID_HERE", "mode": "id"},
    "sheetName": {"__rl": True, "value": "Contacted", "mode": "name"},
    "columns": {"mappingMode": "defineBelow", "matchingColumns": ["Customer"], "value": {
        "Customer": "={{ $('Text, or Email?').item.json.first_name }} "
                    "{{ $('Text, or Email?').item.json.last_name }}",
        "Vehicle": "={{ $('Text, or Email?').item.json.vehicle }}",
        "Months Since Service": "={{ $('Text, or Email?').item.json.months_since_service }}",
        "Lifetime Value": "={{ $('Text, or Email?').item.json.lifetime_value }}",
        "Channel": "={{ $('Text, or Email?').item.json.sms_consent && "
                   "$('Text, or Email?').item.json.phone_type === 'mobile' ? 'SMS' : 'Email' }}",
        "Message": "={{ $json.body || $json.text }}",
    }},
    "options": {},
}, (320, 60))

n_log_left = add("Log Who We Left Alone", "n8n-nodes-base.googleSheets", 4.5, {
    "operation": "appendOrUpdate",
    "documentId": {"__rl": True, "value": "YOUR_GOOGLE_SHEET_ID_HERE", "mode": "id"},
    "sheetName": {"__rl": True, "value": "Left Alone", "mode": "name"},
    "columns": {"mappingMode": "defineBelow", "matchingColumns": ["Customer"], "value": {
        "Customer": "={{ $json.first_name }} {{ $json.last_name }}",
        "Lifetime Value": "={{ $json.lifetime_value }}",
        "Days Since Service": "={{ $json.days_since_service }}",
        "Left Alone Because": "={{ $('Who Do We Leave Alone?').item.json.do_not_contact "
                              "? 'On the do-not-contact list' : $json.marketing_opt_out "
                              "? 'Opted out of marketing' : !$json.email && !$json.phone "
                              "? 'No phone or email on record' : $json.days_since_service < 180 "
                              "? 'Came in recently - not dormant' "
                              ": 'Contacted in the last 30 days' }}",
    }},
    "options": {},
}, (-420, 320))

# ------------------------------------------------------------------ connections
connections = {}


def wire(src, dst, si=0, di=0, kind="main"):
    c = connections.setdefault(src, {}).setdefault(kind, [])
    while len(c) <= si:
        c.append([])
    c[si].append({"node": dst, "type": kind, "index": di})


wire(t, n_list)
wire(n_list, n_dates)
wire(n_dates, n_suppress)
for i in range(5):                       # the five suppression reasons
    wire(n_suppress, n_left, i)
wire(n_suppress, n_channel, 5)           # the fallback: worth contacting
wire(n_left, n_log_left)
wire(n_channel, n_sms, 0)
wire(n_channel, n_email, 1)
wire(n_model, n_sms, 0, 0, "ai_languageModel")
wire(n_model, n_email, 0, 0, "ai_languageModel")
wire(n_sms, n_check)
wire(n_check, n_twilio, 0)
wire(n_check, n_held, 1)
wire(n_twilio, n_log_out)
wire(n_email, n_subject)
wire(n_subject, n_gmail)
wire(n_gmail, n_log_out)

# ------------------------------------------------------------------ pinned data
def pin_customers():
    out = []
    for c in d["customers"]:
        out.append({"json": {k: v for k, v in c.items()
                             if k not in ("_demo_note", "demo_hint")}})
    return out


def pin_text(ids):
    by_id = {c["customer_id"]: c for c in d["customers"]}
    return [{"json": {"text": by_id[i]["demo_hint"]["message"]}} for i in ids]


pin_data = {
    n_list: pin_customers(),
    n_sms: pin_text(["C-1001", "C-1008"]),
    n_email: pin_text(["C-1002", "C-1009", "C-1010"]),
}

wf = {"name": "Reactivation Campaign", "nodes": nodes, "connections": connections,
      "pinData": pin_data, "settings": {"executionOrder": "v1"},
      "meta": {"instanceId": "automatoys-ai-demo"}, "tags": []}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(wf, f, indent=2, ensure_ascii=False)

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
import re
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
reachable.add(n_model)  # sub-nodes hang off a chain rather than the main flow
orphans = [n["name"] for n in nodes
           if n["type"] != "n8n-nodes-base.stickyNote" and n["name"] not in reachable]
if orphans:
    errors.append("nothing reaches: " + ", ".join(orphans))

blob = json.dumps(wf).lower()
for banned in ("anthropic", "claude"):
    if banned in blob:
        errors.append("provider leak: '%s' appears in the workflow" % banned)

functional = [n for n in nodes if n["type"] != "n8n-nodes-base.stickyNote"]
code_nodes = [n for n in functional if n["type"] == "n8n-nodes-base.code"]
print("nodes: %d functional (+%d notes) | Code nodes: %d | pinned: %d"
      % (len(functional), len(nodes) - len(functional), len(code_nodes), len(pin_data)))
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
