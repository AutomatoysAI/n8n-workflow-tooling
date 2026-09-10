"""Writes Shipment-Exception-Watch.json.

This script is the source of truth. Edit it and re-run it:

    python build/build.py

Do not hand-edit the JSON - the next run overwrites it. If the workflow is ever
changed inside n8n and re-exported, this script and that file have diverged and
one of them has to win.

Demo-mode rules (see ../../BUILD-RULES.md): built-in n8n nodes only, no Code nodes,
fewest nodes that still tell the story, n8n's own pinned data instead of a
hand-built demo toggle, and OpenAI for the one AI step.

What makes this demo different from everything else in the library:

Every other workflow here reacts to something ARRIVING - an email lands, a form
is submitted, a schedule fires and pulls today's figures. A parcel that has
stopped moving sends nothing. There is no event. The only way to notice it is to
know what the shipment looked like yesterday and compare, so this is the first
workflow in the library that keeps a record of its own previous run and reads it
back the next morning.

The second idea: three outcomes, not two. A shipment that has gone quiet is
usually ambiguous rather than clearly broken - a long-haul leg is silent for
days by design. A monitor with only "fine" and "alarm" cries wolf inside a week
and the team stops reading it, which is how these systems quietly die. So there
is a third lane that says a person should look.

The third: when the courier feed returns nothing for an order it reported on
yesterday, that is not a stuck parcel, it is a broken pipe - and it goes to
operations as plain arithmetic without a model anywhere near it.
"""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "sample-shipments.json")
OUT = os.path.join(ROOT, "Shipment-Exception-Watch.json")

d = json.load(open(DATA, encoding="utf-8"))
b = d["brand"]

# Every date comparison is made against this one fixed moment rather than the
# clock, so the pinned demo tells the same story in six months' time. IN
# PRODUCTION THIS BECOMES $now - it is one string, in one place, and the sticky
# note on the canvas says so out loud.
NOW = b["as_of"]

nodes = []


def add(name, ntype, tv, params, pos, disabled=False):
    n = {"parameters": params, "id": "b7000000-0000-4000-8000-%012d" % (len(nodes) + 1),
         "name": name, "type": ntype, "typeVersion": tv, "position": list(pos)}
    if disabled:
        n["disabled"] = True
    nodes.append(n)
    return name


def sticky(content, pos, w, h, color=7):
    add("Note " + str(len([n for n in nodes if n["type"].endswith("stickyNote")]) + 1),
        "n8n-nodes-base.stickyNote", 1,
        {"content": content, "height": h, "width": w, "color": color}, pos)


def sets(assignments, include_others=True):
    return {"includeOtherFields": include_others,
            "assignments": {"assignments": [
                {"id": "a%d" % i, "name": n, "type": t, "value": v}
                for i, (n, t, v) in enumerate(assignments, 1)]},
            "options": {}}


def route(pairs):
    """A Switch where every rule is 'lane equals <this>'."""
    return {"rules": {"values": [
        {"conditions": {
            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose",
                        "version": 2},
            "conditions": [{"id": "s%d" % i, "leftValue": "={{ $json.lane }}",
                            "rightValue": lane,
                            "operator": {"type": "string", "operation": "equals"}}],
            "combinator": "and"},
         "renameOutput": True, "outputKey": label}
        for i, (lane, label) in enumerate(pairs, 1)]},
        "options": {"fallbackOutput": "extra",
                    "renameFallbackOutput": "Moving normally - say nothing"}}


# ------------------------------------------------------------------ sticky notes
sticky("""## What this does

Every weekday at 8am it takes the orders that are paid but not yet delivered,
asks the courier where each one is, and **compares that against what it wrote
down yesterday**.

Eleven orders are pinned here and they end in five different places.

Three are moving normally and are never mentioned again. Three are stuck. One
was invoiced at nearly three times the quoted rate. Two are ambiguous, so a
person looks rather than an alarm firing. And two are orders the courier
reported on yesterday and returned **nothing at all** for this morning.

One message at 8am. Not eleven alerts.""",
       (-2500, -760), 440, 380, 4)

sticky("""## Nothing announces itself

This is the sentence to open the call with, because it is what makes shipment
monitoring different from everything else on this canvas.

**A late parcel does not raise an error and does not send a message.** It simply
stops generating scans. The first notification anybody gets is the customer
asking where their coat is, and by then it has been sitting in a customs shed
for a week.

So this workflow cannot wait to be told. It has to notice an **absence**, and
noticing an absence means knowing what yesterday looked like.

That is what `Write Down Today's Position` is for. Every order passes through
it, whether or not it is a problem, and tomorrow morning's run reads it back.
**An order that appeared yesterday and is still here is a worse problem than one
that appeared today**, and the brief says which is which - AL-10361 has been
held by US customs for five mornings running.

Without that stored line there is no such thing as "stopped moving". There is
only a status, and a status looks the same on day one and day nine.""",
       (-2020, -760), 480, 480, 3)

sticky("""## Two rules, and neither of them is a model

**Stuck is arithmetic.** Paid more than the warehouse's own handover window ago
and never handed over; or no scan for four days; or three days past the courier's
own service standard for that lane. Subtraction, with the same answer twice.

**The cost check is arithmetic too.** The 3PL quotes a rate per zone and weight
before the parcel ships, and the courier invoices afterwards. Divide one by the
other. AL-10419 comes back at 2.84 - a boxed coat re-weighed on volume rather
than actual weight, which is the commonest way shipping costs quietly leak.

Ask a model whether GBP 31.80 is reasonable for a 0.8kg parcel to Warrington and
it will answer confidently either way. It has no idea what was quoted.

**The model here writes the message and nothing else.** It never sees the healthy
orders, it never decides a lane, and every figure it is given has already been
worked out. The lane where the courier feed went silent does not reach it at
all - that one goes straight to operations, because the right response to "we
have no idea where six parcels are" is not a well-written paragraph.

**Everything that sends or writes is greyed out.** It runs end to end and leaves
nothing behind.""",
       (-1520, -760), 500, 480, 6)

sticky("""## The third outcome is the one that keeps it alive

A shipment that has gone quiet is usually **ambiguous, not broken**. A long-haul
leg to Australia is silent for three days by design. A weekend adds two.

A monitor with only two answers - fine, or alarm - cries wolf inside a week, and
a team that has learned to ignore the 8am message is worse than no message at
all.

So AL-10402 and AL-10369 go into a **"someone should look"** list rather than an
alert. Same brief, different sentence, no siren.""",
       (-1000, -760), 420, 320, 5)

# ------------------------------------------------------------------ 1. triggers
sched = add("Every Weekday, 8am", "n8n-nodes-base.scheduleTrigger", 1.2, {
    "rule": {"interval": [{"field": "cronExpression", "expression": "0 8 * * 1-5"}]},
}, (-2480, 200))

manual = add("Run the Demo", "n8n-nodes-base.manualTrigger", 1, {}, (-2480, 420))

# ------------------------------------------------------------------ 2. three sources
# Paid, not yet delivered. Everything else is somebody else's problem.
n_orders = add("Open Orders (Shopify)", "n8n-nodes-base.shopify", 1, {
    "resource": "order", "operation": "getAll", "returnAll": True,
    "options": {"status": "open", "financialStatus": "paid",
                "fulfillmentStatus": "any"},
}, (-2240, 20))

# The fulfilment partner's tracking feed. Every 3PL has one and no two look
# alike, so this is a plain HTTP Request rather than a courier-specific node -
# swap the URL and the field names in the next node and it is a different 3PL.
n_track = add("Courier Tracking Today", "n8n-nodes-base.httpRequest", 4.2, {
    "url": "https://api.nordkey.example/v2/shipments",
    "method": "GET",
    "authentication": "genericCredentialType",
    "genericAuthType": "httpHeaderAuth",
    "sendQuery": True,
    "queryParameters": {"parameters": [
        {"name": "status", "value": "in_transit,exception"},
        {"name": "updated_since", "value": NOW[:10]},
    ]},
    "options": {},
}, (-2240, 240))

# Yesterday morning's run wrote this. It is the whole reason the workflow can
# tell "stopped moving" from "moving slowly".
n_snap = add("What We Saw Yesterday", "n8n-nodes-base.googleSheets", 4.5, {
    "documentId": {"__rl": True, "value": "YOUR_LOGISTICS_SHEET_ID", "mode": "id"},
    "sheetName": {"__rl": True, "value": "Yesterday", "mode": "name"},
    "options": {},
}, (-2240, 460))

# ------------------------------------------------------------------ 3. join them up
# enrichInput1 both times, so an order with no courier record SURVIVES instead of
# being dropped. That order is the whole point of the fourth lane - a shipment
# quietly falling out of the join is exactly the failure being watched for.
n_join1 = add("Match Order to Shipment", "n8n-nodes-base.merge", 3, {
    "mode": "combine", "combineBy": "combineByFields",
    "fieldsToMatchString": "order_number", "joinMode": "enrichInput1", "options": {},
}, (-2000, 120))

n_join2 = add("Add Yesterday's Position", "n8n-nodes-base.merge", 3, {
    "mode": "combine", "combineBy": "combineByFields",
    "fieldsToMatchString": "order_number", "joinMode": "enrichInput1", "options": {},
}, (-1780, 260))

# ------------------------------------------------------------------ 4. the arithmetic
# No AI in here, and that is the point. Every judgement a model could get wrong
# is a subtraction instead. n8n cannot reference a field it is setting in the
# same node, so the expressions below are composed from shared fragments rather
# than chained - the fragment is written once here and reused.


def diff(field):
    return ("Math.floor(DateTime.fromISO('%s').diff(DateTime.fromISO($json.%s),"
            " 'days').days)" % (NOW, field))


D_ORDER = diff("placed_at")
D_TRANSIT = "($json.shipped_at ? %s : -1)" % diff("shipped_at")
D_SCAN = "($json.scan_at ? %s : -1)" % diff("scan_at")
OVERDUE = ("($json.shipped_at ? Math.max(0, %s - $json.service_days) : 0)"
           % diff("shipped_at"))
RATIO = ("($json.quoted_shipping > 0 && $json.invoiced_shipping ?"
         " Math.round(($json.invoiced_shipping / $json.quoted_shipping) * 100) / 100 : 0)")

# The courier told us about this order yesterday and returned nothing today.
# That is a feed, not a parcel.
SILENT = "($json.fulfilled && !$json.scan_at && !!$json.snap_scan_at)"
# Paid, and the warehouse has still not handed it to anybody.
NEVER = "(!$json.fulfilled && %s > $json.handover_days)" % D_ORDER
QUIET = "(!!$json.scan_at && %s >= 4)" % D_SCAN
LATE = "(%s >= 3)" % OVERDUE
STUCK = "(!%s && (%s || %s || %s))" % (SILENT, NEVER, QUIET, LATE)
COSTLY = "(%s >= 1.4)" % RATIO
MAYBE = ("(!%s && !%s && !%s && (%s >= 2 || %s >= 1))"
         % (SILENT, STUCK, COSTLY, D_SCAN, OVERDUE))

LANE = ("={{ %s ? 'Courier silent' : %s ? 'Stuck' : %s ? 'Costs more than quoted'"
        " : %s ? 'Not sure' : 'Moving normally' }}" % (SILENT, STUCK, COSTLY, MAYBE))

WHY = ("={{ %s ? 'The courier reported on this order yesterday and returned no record"
       " at all today.'"
       " : %s ? ('Paid ' + %s + ' days ago and the warehouse has still not handed it to a"
       " courier.')"
       " : %s ? ('No scan for ' + %s + ' days - last seen as ' + $json.scan_status + ' at '"
       " + $json.scan_location + '.')"
       " : %s ? ('Still moving, but ' + %s + ' days past the ' + $json.service_days +"
       " '-day service standard for ' + $json.zone + '.')"
       " : %s ? ('Invoiced ' + $json.invoiced_shipping + ' against a quoted ' +"
       " $json.quoted_shipping + ' - ' + %s + ' times the rate for ' + $json.weight_kg +"
       " 'kg to ' + $json.zone + '.')"
       " : ('Quiet for ' + %s + ' days and ' + %s + ' days past the service standard -"
       " normal on this lane, but worth a look.') }}"
       % (SILENT, NEVER, D_ORDER, QUIET, D_SCAN, LATE, OVERDUE, COSTLY, RATIO,
          D_SCAN, OVERDUE))

n_calc = add("Work Out What Changed", "n8n-nodes-base.set", 3.4, sets([
    ("days_since_order", "number", "={{ %s }}" % D_ORDER),
    ("days_in_transit", "number", "={{ %s }}" % D_TRANSIT),
    ("days_since_scan", "number", "={{ %s }}" % D_SCAN),
    ("days_overdue", "number", "={{ %s }}" % OVERDUE),
    ("cost_ratio", "number", "={{ %s }}" % RATIO),
    # Did the parcel actually move since the last run, or is the status simply
    # the same words it was yesterday? A status alone cannot tell you.
    ("moved_since_yesterday", "boolean",
     "={{ !!$json.scan_at && !!$json.snap_scan_at && $json.scan_at != $json.snap_scan_at }}"),
    ("reported_before", "number", "={{ $json.snap_mornings_reported || 0 }}"),
    ("lane", "string", LANE),
    ("why", "string", WHY),
    ("severity", "number",
     "={{ %s ? 3 : %s ? 2 : %s ? 1 : 0 }}" % (STUCK, COSTLY, MAYBE)),
]), (-1560, 260))

# Every order passes through here, healthy ones included, because tomorrow's
# comparison needs today's position for all of them. An order that vanishes
# quietly is the failure this whole design exists to prevent.
n_write = add("Write Down Today's Position", "n8n-nodes-base.googleSheets", 4.5, {
    "operation": "appendOrUpdate",
    "documentId": {"__rl": True, "value": "YOUR_LOGISTICS_SHEET_ID", "mode": "id"},
    "sheetName": {"__rl": True, "value": "Yesterday", "mode": "name"},
    "columns": {"mappingMode": "defineBelow", "matchingColumns": ["order_number"],
                "value": {
                    "order_number": "={{ $json.order_number }}",
                    "snap_scan_at": "={{ $json.scan_at }}",
                    "snap_lane": "={{ $json.lane }}",
                    "snap_mornings_reported":
                        "={{ $json.lane == 'Moving normally' ? 0 :"
                        " $json.reported_before + 1 }}",
                }},
    "options": {},
}, (-1340, 260), disabled=True)

n_switch = add("Sort Into Lanes", "n8n-nodes-base.switch", 3.2, route([
    ("Stuck", "Stuck - raise it"),
    ("Costs more than quoted", "Costs more than quoted"),
    ("Not sure", "Not sure - a person looks"),
    ("Courier silent", "Courier told us nothing"),
]), (-1120, 260))

n_fine = add("Moving Normally - Say Nothing", "n8n-nodes-base.noOp", 1, {}, (-880, 620))

# ------------------------------------------------------------------ 5. no model here
# The courier feed returned nothing for orders it reported on yesterday. Nobody
# knows where these parcels are, and a fluent paragraph about it would be worse
# than useless - so this lane never reaches the model.
n_lost = add("Every Order the Courier Lost", "n8n-nodes-base.aggregate", 1, {
    "aggregate": "aggregateAllItemData", "destinationFieldName": "lost", "options": {},
}, (-880, 800))

n_ops = add("Feed Looks Down - Tell Ops", "n8n-nodes-base.slack", 2.3, {
    "select": "channel",
    "channelId": {"__rl": True, "value": b["alerts_channel"], "mode": "name"},
    "text": ("=*" + b["fulfilment_partner"] + " returned no tracking at all for "
             "{{ $json.lost.length }} orders this morning*\n"
             "{{ $json.lost.map(o => o.order_number + '  ' + o.tracking_number + '  ('"
             " + o.destination_country + ', last seen ' + o.snap_scan_at.slice(0, 10)"
             " + ')').join('\\n') }}\n"
             "Every one of these was in yesterday's feed. Orders that disappear from a "
             "tracking feed overnight are usually an expired API key, a rotated password, "
             "or the 3PL closing an account - not lost parcels.\n"
             "*Nothing about these went into the morning brief*, because nobody knows "
             "where they are. " + b["ops_lead"] + " - please check the connection before "
             "chasing the courier."),
    "otherOptions": {},
}, (-660, 800), disabled=True)

# ------------------------------------------------------------------ 6. one brief
n_all = add("Everything Worth Reporting", "n8n-nodes-base.merge", 3, {
    "mode": "append", "numberInputs": 3, "options": {},
}, (-880, 220))

n_sort = add("Worst First", "n8n-nodes-base.sort", 1, {
    "sortFieldsUi": {"sortField": [
        {"fieldName": "severity", "order": "descending"},
        {"fieldName": "reported_before", "order": "descending"},
    ]},
    "options": {},
}, (-660, 220))

n_one = add("One Brief, Not Twelve Alerts", "n8n-nodes-base.aggregate", 1, {
    "aggregate": "aggregateAllItemData", "destinationFieldName": "exceptions", "options": {},
}, (-440, 220))

E = "$json.exceptions"
TABLE = ("={{ " + E + ".map(o => o.lane"
         " + '  |  ' + o.order_number"
         " + '  |  ' + o.customer + ', ' + o.destination_country + ' (' + o.zone + ')'"
         " + '  |  ' + (o.carrier || 'no courier yet') + ' ' + (o.tracking_number ||"
         " 'no tracking number')"
         " + '  |  last scan ' + (o.scan_at ? (o.scan_at.slice(0, 10) + ' - ' +"
         " o.scan_status + ', ' + o.scan_location) : 'never')"
         " + '  |  ' + o.why"
         " + '  |  ' + (o.reported_before > 0 ? ('already reported on ' + o.reported_before"
         " + ' previous mornings') : 'first appeared today')"
         ").join('\\n') }}")

n_table = add("Build the Exception Table", "n8n-nodes-base.set", 3.4, sets([
    ("exception_table", "string", TABLE),
    ("open_orders", "number", "={{ $('Work Out What Changed').all().length }}"),
    ("needing_attention", "number", "={{ " + E + ".length }}"),
    ("repeats", "number", "={{ " + E + ".filter(o => o.reported_before > 0).length }}"),
    ("morning", "string", NOW[:10]),
], include_others=False), (-220, 220))

n_model = add("OpenAI Chat Model", "@n8n/n8n-nodes-langchain.lmChatOpenAi", 1.2, {
    "model": {"__rl": True, "value": "gpt-4.1-mini", "mode": "list",
              "cachedResultName": "gpt-4.1-mini"},
    "options": {"temperature": 0.2, "maxTokens": 700},
}, (0, 440))

PROMPT = ("=You write the 8am logistics message for " + b["name"] + ", an "
          + b["city"] + " fashion label that ships internationally through "
          + b["fulfilment_partner"] + """.

It is the morning of {{ $json.morning }}. There are {{ $json.open_orders }} orders paid and
not yet delivered. {{ $json.needing_attention }} of them need attention, and
{{ $json.repeats }} of those were also reported on a previous morning.

THE ORDERS THAT NEED ATTENTION - already sorted, worst first. Every judgement in this table
was made by arithmetic before you were asked:

{{ $json.exception_table }}

Write a short Slack message for the operations team:

1. One opening line: how many orders are open, how many need attention this morning.
2. The ones marked Stuck, worst first. One line each. Say what the customer would see if
   they looked, and say what to do - chase the warehouse, send the customs paperwork, open a
   case with the courier.
3. Anything marked Costs more than quoted, with the quoted figure and the invoiced figure
   both named.
4. A short closing list of the ones marked Not sure, introduced as worth a look rather than
   as problems.

Rules. These matter more than the writing:
- Every order number, tracking number, date, figure and status must appear in the table
  above. Do not invent a tracking number, a carrier, a delivery date or a customer name.
- Do not guess why something is late. If the table does not say, say what to check.
- An order that has been reported on previous mornings is a worse problem than a new one.
  Say which are repeats and how many mornings.
- Do not mention any order that is not in the table. The ones moving normally are not your
  business and you have not been shown them.
- Plain English. Anyone on the team should be able to act on this without opening anything.
- No greeting, no sign-off, no emoji, no exclamation marks.

Return the message only.""")

n_brief = add("Write the Morning Brief", "@n8n/n8n-nodes-langchain.chainLlm", 1.4, {
    "promptType": "define", "text": PROMPT, "messages": {"messageValues": []},
}, (0, 220))

n_post = add("Morning Brief to Slack", "n8n-nodes-base.slack", 2.3, {
    "select": "channel",
    "channelId": {"__rl": True, "value": b["ops_channel"], "mode": "name"},
    "text": "={{ $json.text }}",
    "otherOptions": {},
}, (220, 220), disabled=True)

# ------------------------------------------------------------------ connections
connections = {}


def wire(src, dst, si=0, di=0, kind="main"):
    c = connections.setdefault(src, {}).setdefault(kind, [])
    while len(c) <= si:
        c.append([])
    c[si].append({"node": dst, "type": kind, "index": di})


for trig in (sched, manual):
    for src in (n_orders, n_track, n_snap):
        wire(trig, src)
wire(n_orders, n_join1, 0, 0)
wire(n_track, n_join1, 0, 1)
wire(n_join1, n_join2, 0, 0)
wire(n_snap, n_join2, 0, 1)
wire(n_join2, n_calc)
wire(n_calc, n_write)
wire(n_write, n_switch)
wire(n_switch, n_all, 0, 0)         # stuck
wire(n_switch, n_all, 1, 1)         # costs more than quoted
wire(n_switch, n_all, 2, 2)         # not sure
wire(n_switch, n_lost, 3)           # courier silent - no model on this lane
wire(n_switch, n_fine, 4)           # fallback
wire(n_lost, n_ops)
wire(n_all, n_sort)
wire(n_sort, n_one)
wire(n_one, n_table)
wire(n_table, n_brief)
wire(n_model, n_brief, 0, 0, "ai_languageModel")
wire(n_brief, n_post)

# ------------------------------------------------------------------ pinned data
pin_data = {
    n_orders: [{"json": o} for o in d["orders"]],
    n_track: [{"json": t} for t in d["tracking"]],
    n_snap: [{"json": s} for s in d["snapshot"]],
}

wf = {"name": "Shipment Exception Watch", "nodes": nodes, "connections": connections,
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

for n in nodes:
    for ref in re.findall(r"\$\('(.*?)'\)", json.dumps(n["parameters"])):
        if ref not in names:
            errors.append("%s refers to a node that does not exist: %r "
                          "(check for an apostrophe in the node name)" % (n["name"], ref))

reachable = {sched, manual}
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
reachable.add(n_model)          # sub-nodes hang off their parent, not a trigger
orphans = [n["name"] for n in nodes
           if n["type"] != "n8n-nodes-base.stickyNote" and n["name"] not in reachable]
if orphans:
    errors.append("nothing reaches: " + ", ".join(orphans))

code_nodes = [n["name"] for n in nodes if n["type"] == "n8n-nodes-base.code"]
if code_nodes:
    errors.append("code nodes present: " + ", ".join(code_nodes))

# ---- does the pinned data actually exercise every lane the canvas draws?
# The same arithmetic as the Set node, in Python, run over the pinned rows. If a
# lane has no example the demo tells an incomplete story in front of a client.
from datetime import datetime

now = datetime.fromisoformat(NOW)
track = {t["order_number"]: t for t in d["tracking"]}
snap = {s["order_number"]: s for s in d["snapshot"]}


def days(value):
    return int((now - datetime.fromisoformat(value)).total_seconds() // 86400)


lanes = {}
for o in d["orders"]:
    t, s = track.get(o["order_number"], {}), snap.get(o["order_number"], {})
    scan_at = t.get("scan_at", "")
    d_order = days(o["placed_at"])
    d_scan = days(scan_at) if scan_at else -1
    overdue = max(0, days(o["shipped_at"]) - o["service_days"]) if o["shipped_at"] else 0
    ratio = (round(t["invoiced_shipping"] / o["quoted_shipping"], 2)
             if o["quoted_shipping"] > 0 and t.get("invoiced_shipping") else 0)
    silent = o["fulfilled"] and not scan_at and bool(s.get("snap_scan_at"))
    stuck = not silent and (
        (not o["fulfilled"] and d_order > o["handover_days"])
        or (bool(scan_at) and d_scan >= 4) or overdue >= 3)
    costly = ratio >= 1.4
    maybe = (not silent and not stuck and not costly
             and (d_scan >= 2 or overdue >= 1))
    lane = ("Courier silent" if silent else "Stuck" if stuck
            else "Costs more than quoted" if costly
            else "Not sure" if maybe else "Moving normally")
    lanes.setdefault(lane, []).append(o["order_number"])

for wanted in ("Moving normally", "Stuck", "Costs more than quoted", "Not sure",
               "Courier silent"):
    if wanted not in lanes:
        errors.append("no pinned order ends up in the '%s' lane" % wanted)
if not any(snap.get(n, {}).get("snap_mornings_reported", 0) > 0
           for n in lanes.get("Stuck", [])):
    errors.append("no stuck order is a repeat from a previous morning - "
                  "the point of keeping yesterday's file is not demonstrated")

functional = [n for n in nodes if n["type"] != "n8n-nodes-base.stickyNote"]
print("nodes: %d functional (+%d notes) | Code nodes: %d | pinned: %d | disabled: %d"
      % (len(functional), len(nodes) - len(functional), len(code_nodes), len(pin_data),
         len([n for n in nodes if n.get("disabled")])))
for lane in sorted(lanes):
    print("  %-24s %s" % (lane, ", ".join(sorted(lanes[lane]))))
print("VALIDATION:", "PASS" if not errors else "FAIL")
for e in errors:
    print("  -", e)

import sys
sys.path.insert(0, os.path.dirname(ROOT))
from node_versions import unverified
for line in unverified(OUT):
    print("  unverified:", line)
print("wrote", OUT)
