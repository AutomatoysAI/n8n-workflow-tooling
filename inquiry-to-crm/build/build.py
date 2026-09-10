"""Writes Inquiry-to-CRM.json.

This script is the source of truth. Edit it and re-run it:

    python build/build.py

Do not hand-edit the JSON - the next run overwrites it. If the workflow is ever
changed inside n8n and re-exported, this script and that file have diverged and
one of them has to win.

Demo-mode rules (see ../../BUILD-RULES.md): built-in n8n nodes only, no Code nodes,
fewest nodes that still tell the story, and n8n's own pinned data instead of a
hand-built demo toggle.

The lookup table is derived from the customer list rather than written by hand -
one row per identifier, which is the shape a CRM search gives you back.
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "sample-inquiries.json")
OUT = os.path.join(ROOT, "Inquiry-to-CRM.json")

d = json.load(open(DATA, encoding="utf-8"))
co = d["company"]

ROLE_BOXES = ["info", "support", "orders", "sales", "admin", "contact", "hello",
              "billing", "help", "enquiries", "accounts", "office"]

nodes = []


def add(name, ntype, tv, params, pos, disabled=False):
    n = {"parameters": params, "id": "e7000000-0000-4000-8000-%012d" % (len(nodes) + 1),
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

Support email and website form submissions arrive through **different front
doors** and are turned into one shape immediately. From there a single matching
engine decides who each one is from.

Six inquiries in: two matched with confidence, two matched but **not trusted
enough to file automatically**, two genuinely new.

Every one of them gets a task, whichever way it went. Nothing is dropped -
which is the actual goal.""",
       (-1980, -420), 460, 320, 4)

sticky("""## A wrong match is worse than no match

File Jane's ticket against Daniel's record and you have put one customer's
order history on another customer's file. Support then answers Jane using
Daniel's orders.

So the system has **three** answers, not two:

- **email or order number** matched - file it
- **phone number only**, or a shared mailbox - a person confirms first
- **nothing matched** - create a lead marked unverified

The middle lane is the whole design. Match too strictly and the CRM fills with
duplicates within a quarter. Match too loosely and you merge two real people.
Living between those two failures is the job.""",
       (-1480, -420), 500, 360, 3)

sticky("""## Why four nodes are greyed out

Everything that writes - to the CRM, to the task list, to Slack - is
**disabled on purpose**. You can run the whole thing against a real inbox,
read every verdict, and leave nothing behind.

The two sources and the customer lookup have **pinned data**, so it runs with
no accounts connected at all.

**Note there is no AI here.** Identity matching is arithmetic, and arithmetic
should be deterministic - the same inquiry has to reach the same customer
every time. The AI belongs one step later, drafting the reply.""",
       (-960, -420), 460, 320, 6)

# ------------------------------------------------------------------ 1. trigger
t = add("Run the Demo", "n8n-nodes-base.manualTrigger", 1, {}, (-1960, 100))

# ------------------------------------------------------------------ 2. two front doors
n_mail = add("Support Inbox", "n8n-nodes-base.gmail", 2.1, {
    "resource": "message", "operation": "getAll", "returnAll": True,
    "filters": {"q": "to:" + co["support_inbox"] + " is:unread"},
    "options": {},
}, (-1760, -20))

n_form = add("Website Support Form", "n8n-nodes-base.googleSheets", 4.5, {
    "documentId": {"__rl": True, "value": "YOUR_GOOGLE_SHEET_ID_HERE", "mode": "id"},
    "sheetName": {"__rl": True, "value": "Form Responses", "mode": "name"},
    "options": {},
}, (-1760, 220))

# Both front doors are turned into the same shape here, and only here. A new
# source - the trade-in form, a text message, a phone log - is one more node
# into this same point, not a second copy of everything downstream.
n_from_mail = add("Read the Email as an Inquiry", "n8n-nodes-base.set", 3.4, sets([
    ("inquiry_id", "string", "={{ $json.inquiry_id }}"),
    ("source", "string", "Support email"),
    ("received_at", "string", "={{ $json.date }}"),
    ("name", "string", "={{ $json.name }}"),
    ("email", "string", "={{ $json.from }}"),
    ("phone", "string", "={{ $json.phone }}"),
    ("order_number", "string", "={{ $json.order_number }}"),
    ("subject", "string", "={{ $json.subject }}"),
    ("message", "string", "={{ $json.text }}"),
], include_others=False), (-1540, -20))

n_from_form = add("Read the Form as an Inquiry", "n8n-nodes-base.set", 3.4, sets([
    ("inquiry_id", "string", "={{ $json.inquiry_id }}"),
    ("source", "string", "Website form"),
    ("received_at", "string", "={{ $json.submitted_at }}"),
    ("name", "string", "={{ $json.full_name }}"),
    ("email", "string", "={{ $json.email_address }}"),
    ("phone", "string", "={{ $json.phone_number }}"),
    ("order_number", "string", "={{ $json.order_reference }}"),
    ("subject", "string", "={{ $json.topic }}"),
    ("message", "string", "={{ $json.enquiry }}"),
], include_others=False), (-1540, 220))

# ------------------------------------------------------------------ 3. the identifiers
EMAIL = "($json.email || '').trim().toLowerCase()"
PHONE = "($json.phone || '').replace(/\\D/g, '').slice(-10)"
ORDER = "($json.order_number || '').trim().toUpperCase()"
ROLE = "%s.includes(%s.split('@')[0])" % (json.dumps(ROLE_BOXES), EMAIL)

n_clean = add("Clean Up the Identifiers", "n8n-nodes-base.set", 3.4, sets([
    # (555) 555-0142 and +1 555 555 0142 are the same person. No database agrees.
    ("phone_key", "string", "={{ %s }}" % PHONE),
    ("key", "string", "={{ %s || %s }}" % (ORDER, EMAIL)),
    ("matched_on", "string",
     "={{ %s ? 'order number' : (%s ? 'email address' : 'nothing usable') }}" % (ORDER, EMAIL)),
    # info@ and support@ reach a dozen people. They must never file themselves.
    ("is_role_address", "boolean", "={{ %s }}" % ROLE),
]), (-1320, 100))

n_crm = add("Customer Lookup (CRM)", "n8n-nodes-base.googleSheets", 4.5, {
    "documentId": {"__rl": True, "value": "YOUR_GOOGLE_SHEET_ID_HERE", "mode": "id"},
    "sheetName": {"__rl": True, "value": "Customer Identifiers", "mode": "name"},
    "options": {},
}, (-1320, 400))

# ------------------------------------------------------------------ 4. the matching
n_strong = add("Look Up the Strong Identifiers", "n8n-nodes-base.merge", 3, {
    "mode": "combine",
    "combineBy": "combineByFields",
    "fieldsToMatchString": "key",
    "joinMode": "enrichInput1",
    "options": {},
}, (-1100, 100))

n_found = add("Did We Find Them?", "n8n-nodes-base.if", 2.2, {
    "conditions": {
        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose",
                    "version": 2},
        "conditions": [cond("f1", "={{ $json.customer_id }}", "string", "notEmpty",
                            single=True)],
        "combinator": "and",
    },
    "looseTypeValidation": True, "options": {},
}, (-880, 100))

# Only reached when the order number and the email both came up empty.
n_fallback = add("Fall Back to the Phone Number", "n8n-nodes-base.set", 3.4, sets([
    ("key", "string", "={{ $json.phone_key }}"),
    ("matched_on", "string",
     "={{ $json.phone_key ? 'phone number' : 'nothing usable' }}"),
]), (-660, 300))

n_phone = add("Look Up the Phone Number", "n8n-nodes-base.merge", 3, {
    "mode": "combine",
    "combineBy": "combineByFields",
    "fieldsToMatchString": "key",
    "joinMode": "enrichInput1",
    "options": {},
}, (-440, 300))

# ------------------------------------------------------------------ 5. the three lanes
n_switch = add("How Sure Are We?", "n8n-nodes-base.switch", 3.2, {
    "rules": {"values": [
        rule([cond("c1", "={{ $json.customer_id }}", "string", "notEmpty", single=True),
              cond("c2", "={{ $json.is_role_address }}", "boolean", "false", single=True),
              cond("c3", "={{ $json.matched_on }}", "string", "notEquals", "phone number")],
             "Sure enough to file it"),
        rule([cond("c4", "={{ $json.customer_id }}", "string", "notEmpty", single=True)],
             "Matched, but not sure enough"),
    ]},
    "options": {"fallbackOutput": "extra",
                "renameFallbackOutput": "Nobody we know - new lead"},
}, (-200, 100))

S = "How Sure Are We?"


def f(name):
    return "$('" + S + "').item.json." + name


n_attach = add("Attach It to the Customer Record", "n8n-nodes-base.googleSheets", 4.5, {
    "operation": "append",
    "documentId": {"__rl": True, "value": "YOUR_GOOGLE_SHEET_ID_HERE", "mode": "id"},
    "sheetName": {"__rl": True, "value": "Customer Activity", "mode": "name"},
    "columns": {"mappingMode": "defineBelow", "value": {
        "Customer": "={{ $json.customer_id }} - {{ $json.customer_name }}",
        "Inquiry": "={{ $json.inquiry_id }}",
        "Received": "={{ $json.received_at }}",
        "Source": "={{ $json.source }}",
        "Matched On": "={{ $json.matched_on }}",
        "Subject": "={{ $json.subject }}",
        "Message": "={{ $json.message }}",
    }},
    "options": {},
}, (60, -140), disabled=True)

n_confirm = add("A Person Confirms the Match", "n8n-nodes-base.slack", 2.3, {
    "select": "channel",
    "channelId": {"__rl": True, "value": co["review_channel"], "mode": "name"},
    "text": ("=*Is this the same person?* {{ $json.inquiry_id }} "
             "({{ $json.source }})\n"
             "Came from *{{ $json.email || $json.phone }}*, matched to "
             "*{{ $json.customer_name }}* on {{ $json.matched_on }}.\n"
             "{{ $json.is_role_address ? '_Shared mailbox - could be anyone at that "
             "company._' : '_Phone number only - not proof on its own._' }}\n"
             "> {{ $json.subject }}"),
    "otherOptions": {},
}, (60, 100), disabled=True)

n_lead = add("Create a Lead for Review", "n8n-nodes-base.googleSheets", 4.5, {
    "operation": "append",
    "documentId": {"__rl": True, "value": "YOUR_GOOGLE_SHEET_ID_HERE", "mode": "id"},
    "sheetName": {"__rl": True, "value": "New Leads", "mode": "name"},
    "columns": {"mappingMode": "defineBelow", "value": {
        "Name": "={{ $json.name }}",
        "Email": "={{ $json.email }}",
        "Phone": "={{ $json.phone }}",
        "Source": "={{ $json.source }}",
        "First Contact": "={{ $json.received_at }}",
        "Message": "={{ $json.message }}",
        "Status": "Unverified - needs review",
    }},
    "options": {},
}, (60, 340), disabled=True)

# ------------------------------------------------------------------ 6. the task
# Every lane converges here. An inquiry that could not be identified still
# becomes a task - that is the difference between this and a filing system.
HIGH = "(%s || /damag|urgent|broken|wrong|missing|late/i.test(%s))" % (
    f("order_number"), f("message"))

n_task = add("Build the Task", "n8n-nodes-base.set", 3.4, sets([
    ("task_status", "string", "New"),
    ("priority", "string", "={{ %s ? 'High' : 'Normal' }}" % HIGH),
    ("due_date", "string",
     "={{ DateTime.fromISO(%s).plus({ days: %s ? 1 : 3 }).toFormat('yyyy-MM-dd') }}"
     % (f("received_at"), HIGH)),
    ("assigned_to", "string",
     "={{ %s ? '%s' : '%s' }}" % (f("order_number"), co["orders_owner"],
                                 co["support_owner"])),
    ("internal_note", "string",
     "={{ " + f("customer_id") + " ? ('Matched to ' + " + f("customer_name") +
     " + ' on ' + " + f("matched_on") + " + '.'"
     " + (" + f("matched_on") + " === 'phone number' ? ' A phone number is not proof "
     "of identity - confirm before relying on the history.' : '')"
     " + (" + f("is_role_address") + " ? ' Shared mailbox - confirm which person this "
     "is.' : '')) : 'No matching customer on file. Lead created for review, and the "
     "order number given did not resolve.' }}"),
], include_others=False), (320, 100))

n_create = add("Create the Task", "n8n-nodes-base.googleSheets", 4.5, {
    "operation": "append",
    "documentId": {"__rl": True, "value": "YOUR_GOOGLE_SHEET_ID_HERE", "mode": "id"},
    "sheetName": {"__rl": True, "value": "Tasks", "mode": "name"},
    "columns": {"mappingMode": "defineBelow", "value": {
        "Inquiry": "={{ " + f("inquiry_id") + " }}",
        "Received": "={{ " + f("received_at") + " }}",
        "Source": "={{ " + f("source") + " }}",
        "Customer": "={{ " + f("customer_id") + " ? " + f("customer_id") +
                    " + ' - ' + " + f("customer_name") + " : 'Not identified' }}",
        "Contact Email": "={{ " + f("email") + " }}",
        "Contact Phone": "={{ " + f("phone") + " }}",
        "Order": "={{ " + f("order_number") + " }}",
        "Subject": "={{ " + f("subject") + " }}",
        "Message": "={{ " + f("message") + " }}",
        "Status": "={{ $json.task_status }}",
        "Priority": "={{ $json.priority }}",
        "Due": "={{ $json.due_date }}",
        "Assigned To": "={{ $json.assigned_to }}",
        "Internal Note": "={{ $json.internal_note }}",
    }},
    "options": {},
}, (540, 100), disabled=True)

# ------------------------------------------------------------------ connections
connections = {}


def wire(src, dst, si=0, di=0, kind="main"):
    c = connections.setdefault(src, {}).setdefault(kind, [])
    while len(c) <= si:
        c.append([])
    c[si].append({"node": dst, "type": kind, "index": di})


wire(t, n_mail)
wire(t, n_form)
wire(t, n_crm)
wire(n_mail, n_from_mail)
wire(n_form, n_from_form)
wire(n_from_mail, n_clean)              # both front doors, one shape
wire(n_from_form, n_clean)
wire(n_clean, n_strong, 0, 0)
wire(n_crm, n_strong, 0, 1)             # the lookup feeds both attempts
wire(n_crm, n_phone, 0, 1)
wire(n_strong, n_found)
wire(n_found, n_switch, 0)              # found on a strong identifier
wire(n_found, n_fallback, 1)            # not found - try the phone
wire(n_fallback, n_phone, 0, 0)
wire(n_phone, n_switch)
wire(n_switch, n_attach, 0)
wire(n_switch, n_confirm, 1)
wire(n_switch, n_lead, 2)
wire(n_attach, n_task)
wire(n_confirm, n_task)
wire(n_lead, n_task)
wire(n_task, n_create)

# ------------------------------------------------------------------ pinned data
# One row per identifier, which is the shape a CRM search hands back. Derived
# from the customer list so the two can never drift apart.
def digits(s):
    return re.sub(r"\D", "", s)[-10:]


lookup = []
for c in d["customers"]:
    base = {k: c[k] for k in ("customer_id", "customer_name", "customer_email",
                             "customer_phone", "customer_since")}
    lookup.append(dict(base, key=c["customer_email"].lower(), key_type="email"))
    lookup.append(dict(base, key=digits(c["customer_phone"]), key_type="phone"))
    for o in c["orders"]:
        lookup.append(dict(base, key=o.upper(), key_type="order"))

pin_data = {
    n_mail: [{"json": m} for m in d["emails"]],
    n_form: [{"json": s} for s in d["form_submissions"]],
    n_crm: [{"json": r} for r in lookup],
}

wf = {"name": "Inquiry to CRM", "nodes": nodes, "connections": connections,
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

# ---- the matching is run here too, in Python, against the same pinned data.
# If the demo tells a different story from the README, this is where it shows.
by_key = {}
for r in lookup:
    by_key.setdefault(r["key"], []).append(r)

for k, rows in by_key.items():
    if len({r["customer_id"] for r in rows}) > 1:
        errors.append("identifier %r points at more than one customer, which would "
                      "duplicate the inquiry through the merge" % k)

inquiries = ([dict(m, _email=m["from"], _phone=m["phone"], _order=m["order_number"])
              for m in d["emails"]] +
             [dict(s, _email=s["email_address"], _phone=s["phone_number"],
                   _order=s["order_reference"]) for s in d["form_submissions"]])

actual = {}
for q in inquiries:
    email, order = q["_email"].strip().lower(), q["_order"].strip().upper()
    role = email.split("@")[0] in ROLE_BOXES
    key, basis = (order, "order number") if order else \
                 ((email, "email address") if email else ("", "nothing usable"))
    hit = by_key.get(key)
    if not hit:
        key, basis = digits(q["_phone"]), "phone number"
        hit = by_key.get(key) if key else None
    if hit and not role and basis != "phone number":
        actual[q["inquiry_id"]] = "confident"
    elif hit:
        actual[q["inquiry_id"]] = "possible"
    else:
        actual[q["inquiry_id"]] = "no_match"

for iid, want in d["expected"].items():
    got = actual.get(iid)
    if got != want:
        errors.append("%s should land in %r but the identifiers put it in %r"
                      % (iid, want, got))
if set(actual) != set(d["expected"]):
    errors.append("expected block does not cover every inquiry")

functional = [n for n in nodes if n["type"] != "n8n-nodes-base.stickyNote"]
tally = {}
for v in actual.values():
    tally[v] = tally.get(v, 0) + 1

print("nodes: %d functional (+%d notes) | Code nodes: %d | pinned: %d | disabled: %d"
      % (len(functional), len(nodes) - len(functional), len(code_nodes), len(pin_data),
         len([n for n in nodes if n.get("disabled")])))
print("lookup rows: %d for %d customers | inquiries: %d  %s"
      % (len(lookup), len(d["customers"]), len(inquiries), tally))
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
