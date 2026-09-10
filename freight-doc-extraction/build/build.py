"""Writes Freight-Doc-Extraction.json.

This script is the source of truth. Edit it and re-run it:

    python build/build.py

Do not hand-edit the JSON - the next run overwrites it. If the workflow is ever
changed inside n8n and re-exported, this script and that file have diverged and
one of them has to win.

Demo-mode rules (see ../../BUILD-RULES.md): built-in n8n nodes only, no Code nodes,
fewest nodes that still tell the story, n8n's own pinned data instead of a
hand-built demo toggle, and OpenAI for both AI steps.

What this demo is about: a model asked for an invoice number will always return
something invoice-number-shaped, including when the field is missing or the scan
cut it off. So every value has to arrive with the exact words it was read from,
and a value without those words is treated as invented. Then the document is
made to check itself - the charges have to add up to the total it prints.

What is and is not verified here: the extraction runs at execution time, so its
output is not deterministic and cannot be checked from Python. The sample file
carries what a correct read returns, and the checks below run the deciding logic
against that. So the half that decides what happens to a document is verified.
The half that reads it is not.
"""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "sample-documents.json")
OUT = os.path.join(ROOT, "Freight-Doc-Extraction.json")

d = json.load(open(DATA, encoding="utf-8"))
ca = d["carrier"]
TOL = ca["money_tolerance"]

# label, key - the fields a rate confirmation is useless without.
REQUIRED = [
    ("Load number", "load_number"),
    ("Broker", "broker_name"),
    ("Broker MC number", "broker_mc"),
    ("Pickup date", "pickup_date"),
    ("Delivery date", "delivery_date"),
    ("Total rate", "total_rate"),
]

nodes = []


def add(name, ntype, tv, params, pos, disabled=False):
    n = {"parameters": params, "id": "d5000000-0000-4000-8000-%012d" % (len(nodes) + 1),
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


def f(key):
    """One extracted field, defensively - a missing field must not throw."""
    return "($json.output.%s || {})" % key


def num(key):
    """A money value as a number. Documents print 1,640.00 and $1,640.00."""
    return "Number(String(%s.value || 0).replace(/[^0-9.\\-]/g, '') || 0)" % f(key)


# ------------------------------------------------------------------ sticky notes
sticky("""## What this does

Five documents off the load desk inbox, already turned into text. Each one is
read, and then **checked before anything is believed**.

**Two file themselves. Three stop**, each for a different reason: one adds up
wrong, one is missing fields the scanner cut off, and one is a proof of delivery
that turned up where a rate confirmation was expected.

Every document is logged either way, filed or held. A document that vanishes
quietly is the failure this whole design is built against.""",
       (-1980, -600), 440, 320, 4)

sticky("""## The model will always give you an answer

This is the thing to say first on the call, because it is the failure everybody
else's version has.

Ask a language model for a broker's MC number and it will return something
MC-number-shaped **even when the document does not contain one**. It is not
lying; it is doing what it was asked. A confident wrong number that flows
straight into dispatch is far worse than a blank one, because nobody goes
looking for it.

**So every value has to come back with the exact words it was read from.** If
the model cannot quote the document, it did not read it there - and the value is
treated as invented no matter how plausible it looks.

**Then the document is made to check itself.** Linehaul plus fuel plus
accessorials has to equal the total the document prints. One of the five has a
transposed digit - the charges come to **$3,797.50** and the document says
**$3,779.50**. Every field on it looks perfectly reasonable. Only the arithmetic
catches it, and a person skimming forty of these on a Monday would not.

**None of that judgement is the model's.** It reads; a Set node and an IF
decide. That ordering is the design.""",
       (-1510, -600), 520, 500, 3)

sticky("""## Three practical notes

**Everything that writes is greyed out** - filing the load, the review ping, and
the log. It runs end to end and leaves nothing behind.

**The reader on the left is the swap point.** Documents arrive by email here.
Dropbox, Drive, an SFTP folder or a portal download is one different node in
front, and nothing to the right of it changes.

**Text quality is the real-world variable, not the prompt.** A clean PDF carries
its text inside it and Extract from File just reads it. A photographed or faxed
page carries nothing and needs OCR first, and OCR is where accuracy is actually
won or lost. Worth pricing separately, and worth asking for a sample of the
*worst* document a client has before quoting anything.""",
       (-950, -600), 460, 400, 6)

# ------------------------------------------------------------------ 1. in
t = add("Run the Demo", "n8n-nodes-base.manualTrigger", 1, {}, (-1960, 120))

n_read = add("Read the PDF Text", "n8n-nodes-base.extractFromFile", 1, {
    "operation": "pdf",
    "binaryPropertyName": "attachment_0",
    "options": {},
}, (-1740, 120))

# ------------------------------------------------------------------ 2. what is it
n_model = add("OpenAI Chat Model", "@n8n/n8n-nodes-langchain.lmChatOpenAi", 1.2, {
    "model": {"__rl": True, "value": "gpt-4.1-mini", "mode": "list",
              "cachedResultName": "gpt-4.1-mini"},
    "options": {"temperature": 0, "maxTokens": 1200},
}, (-1300, 400))

# Sorting the post before opening it. A proof of delivery run through a rate
# confirmation prompt produces a full set of confident, wrong fields.
n_class = add("What Kind of Document?", "@n8n/n8n-nodes-langchain.textClassifier", 1, {
    "inputText": "={{ $json.text }}",
    "categories": {"categories": [
        {"category": "Rate confirmation",
         "description": "A broker's offer of a specific load to a carrier. Names a load "
                        "number, a pickup and a delivery, and a rate the carrier is being "
                        "paid. Sometimes headed Rate Confirmation, Load Confirmation or "
                        "Carrier Confirmation."},
        {"category": "Proof of delivery",
         "description": "Evidence a load already arrived - a signed bill of lading, a "
                        "delivery receipt, a POD. Names who received it and when, and "
                        "carries no rate."},
    ]},
    "options": {"fallback": "other"},
}, (-1520, 120))

# ------------------------------------------------------------------ 3. read it
EXTRACT = """=Read this rate confirmation and return the fields below.

**Every field has two parts: the value, and `quote` - the exact run of text you read it
from, copied character for character out of the document.**

- If a field is not in the document, return an empty value AND an empty quote. An empty
  field is a correct answer and costs nothing. A field you filled in from what usually
  appears on documents like this costs a dispatcher a phone call, or worse, does not.
- Never tidy, correct, complete or reformat a quote. It has to be findable in the text
  with a search box.
- Money: digits and a decimal point only. 1,640.00 becomes 1640.00. No currency symbol.
- Dates: YYYY-MM-DD. These documents are US-format, so 09/04/2026 is 4 September 2026.
  If a date is blank or cut off, leave it empty - do not infer it from the other date.
- accessorials is every extra charge added together - lumper, detention, tarp, layover.
  If there are none, return 0.00 and quote the line that says so.
- Do not compute anything. If the charges do not add up to the total, return both exactly
  as printed. Something downstream is looking for precisely that.

DOCUMENT:
{{ $json.text }}"""

SCHEMA = json.dumps({
    "load_number": {"value": "MFB-88214", "quote": "RATE CONFIRMATION - LOAD MFB-88214"},
    "broker_name": {"value": "Meridian Freight Brokers Inc",
                    "quote": "MERIDIAN FREIGHT BROKERS INC"},
    "broker_mc": {"value": "812445", "quote": "MC# 812445"},
    "pickup_date": {"value": "2026-09-03", "quote": "DATE: 09/03/2026  0800-1400"},
    "delivery_date": {"value": "2026-09-04", "quote": "DATE: 09/04/2026  0700-1200"},
    "linehaul": {"value": "2450.00", "quote": "Linehaul .................. 2,450.00"},
    "fuel_surcharge": {"value": "385.00",
                       "quote": "Fuel Surcharge ............   385.00"},
    "accessorials": {"value": "0.00", "quote": "Accessorials ..............     0.00"},
    "total_rate": {"value": "2835.00", "quote": "TOTAL RATE ................ 2,835.00 USD"},
}, indent=2)

n_pull = add("Pull Out the Fields", "@n8n/n8n-nodes-langchain.informationExtractor", 1, {
    "text": EXTRACT, "schemaType": "fromJson", "jsonSchemaExample": SCHEMA, "options": {},
}, (-1280, 120))

# ------------------------------------------------------------------ 4. check it
# Built once in Python so the two lists can never drift apart.
PAIRS = ", ".join("['%s', %s.value, %s.quote]" % (lab, f(k), f(k))
                  for lab, k in REQUIRED)
MISSING = ("[%s].filter(x => !x[1] || String(x[1]).trim() === '')"
           ".map(x => x[0]).join(', ')" % PAIRS)
UNQUOTED = ("[%s].filter(x => x[1] && String(x[1]).trim() !== ''"
            " && (!x[2] || String(x[2]).trim() === '')).map(x => x[0]).join(', ')" % PAIRS)
PARTS = "(%s + %s + %s)" % (num("linehaul"), num("fuel_surcharge"), num("accessorials"))
GAP = "Math.round(Math.abs(%s - %s) * 100) / 100" % (PARTS, num("total_rate"))

n_check = add("Check the Extraction", "n8n-nodes-base.set", 3.4, sets([
    ("load_number", "string", "={{ %s.value }}" % f("load_number")),
    ("broker_name", "string", "={{ %s.value }}" % f("broker_name")),
    ("broker_mc", "string", "={{ %s.value }}" % f("broker_mc")),
    ("pickup_date", "string", "={{ %s.value }}" % f("pickup_date")),
    ("delivery_date", "string", "={{ %s.value }}" % f("delivery_date")),
    ("total_rate", "number", "={{ %s }}" % num("total_rate")),
    ("charges_add_up_to", "number", "={{ Math.round(%s * 100) / 100 }}" % PARTS),
    ("missing_fields", "string", "={{ %s }}" % MISSING),
    # A value the model could not quote is a value the model supplied itself.
    ("unquoted_fields", "string", "={{ %s }}" % UNQUOTED),
    ("money_gap", "number", "={{ %s }}" % GAP),
    ("review_reason", "string",
     "={{ (%s) ? ('Missing: ' + (%s) + '.')"
     " : ((%s) ? ('Not quoted from the document, so not trusted: ' + (%s) + '.')"
     " : ((%s > %s) ? ('The charges add to $' + (Math.round(%s * 100) / 100).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })"
     " + ' but the document says $' + (%s).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' - a $' + (%s).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })"
     " + ' difference.') : '')) }}"
     % (MISSING, MISSING, UNQUOTED, UNQUOTED, GAP, TOL, PARTS, num("total_rate"), GAP)),
], include_others=False), (-1040, 120))

n_safe = add("Safe to File?", "n8n-nodes-base.if", 2.2, {
    "conditions": {
        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose",
                    "version": 2},
        "conditions": [{"id": "s1", "leftValue": "={{ $json.review_reason }}",
                        "rightValue": "",
                        "operator": {"type": "string", "operation": "empty",
                                     "singleValue": True}}],
        "combinator": "and",
    },
    "looseTypeValidation": True, "options": {},
}, (-800, 120))

# ------------------------------------------------------------------ 5. out
n_file = add("File the Load", "n8n-nodes-base.googleSheets", 4.5, {
    "operation": "append",
    "documentId": {"__rl": True, "value": "YOUR_GOOGLE_SHEET_ID_HERE", "mode": "id"},
    "sheetName": {"__rl": True, "value": "Loads", "mode": "name"},
    "columns": {"mappingMode": "defineBelow", "value": {
        "Load": "={{ $json.load_number }}",
        "Broker": "={{ $json.broker_name }}",
        "Broker MC": "={{ $json.broker_mc }}",
        "Pickup": "={{ $json.pickup_date }}",
        "Delivery": "={{ $json.delivery_date }}",
        "Rate": "={{ $json.total_rate }}",
        "Filed": "={{ $now.toISO() }}",
    }},
    "options": {},
}, (-560, -20), disabled=True)

# Everything that stops arrives here - bad arithmetic, missing fields, and the
# wrong kind of document altogether. One queue, because a dispatcher wants one
# place to look, not three.
n_review = add("Send It for Review", "n8n-nodes-base.slack", 2.3, {
    "select": "channel",
    "channelId": {"__rl": True, "value": ca["review_channel"], "mode": "name"},
    "text": ("=*Needs a person* - {{ $('Read the PDF Text').item.json.filename }}\n"
             "{{ $json.review_reason || 'Not a rate confirmation.' }}\n"
             "{{ $json.load_number ? ('Load ' + $json.load_number + ', ' "
             "+ $json.broker_name) : 'From ' + $('Read the PDF Text').item.json.from }}\n"
             "_Nothing has been filed._"),
    "otherOptions": {},
}, (-560, 260), disabled=True)

# Both lanes. A held document that leaves no trace is the same as a lost one.
n_log = add("Log Every Document", "n8n-nodes-base.googleSheets", 4.5, {
    "operation": "append",
    "documentId": {"__rl": True, "value": "YOUR_GOOGLE_SHEET_ID_HERE", "mode": "id"},
    "sheetName": {"__rl": True, "value": "Documents Seen", "mode": "name"},
    "columns": {"mappingMode": "defineBelow", "value": {
        "File": "={{ $('Read the PDF Text').item.json.filename }}",
        "Received": "={{ $('Read the PDF Text').item.json.received_at }}",
        "From": "={{ $('Read the PDF Text').item.json.from }}",
        "Outcome": "={{ $json.review_reason === '' ? 'Filed' : 'Held' }}",
        "Reason": "={{ $json.review_reason || 'Not a rate confirmation.' }}",
    }},
    "options": {},
}, (-320, 120), disabled=True)

# ------------------------------------------------------------------ connections
connections = {}


def wire(src, dst, si=0, di=0, kind="main"):
    c = connections.setdefault(src, {}).setdefault(kind, [])
    while len(c) <= si:
        c.append([])
    c[si].append({"node": dst, "type": kind, "index": di})


wire(t, n_read)
wire(n_read, n_class)
wire(n_class, n_pull, 0)            # rate confirmation - read it properly
wire(n_class, n_review, 1)          # proof of delivery - different process
wire(n_class, n_review, 2)          # something else entirely
wire(n_model, n_class, 0, 0, "ai_languageModel")
wire(n_model, n_pull, 0, 0, "ai_languageModel")
wire(n_pull, n_check)
wire(n_check, n_safe)
wire(n_safe, n_file, 0)
wire(n_safe, n_review, 1)
wire(n_file, n_log)
wire(n_review, n_log)

# ------------------------------------------------------------------ pinned data
pin_data = {n_read: [{"json": {k: doc[k] for k in
                               ("id", "filename", "received_at", "from", "text")}}
                     for doc in d["documents"]]}

wf = {"name": "Freight Doc Extraction", "nodes": nodes, "connections": connections,
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
                    errors.append("connection to a node that does not exist: "
                                  + link["node"])
for pinned in pin_data:
    if pinned not in names:
        errors.append("pinned data for a node that does not exist: " + pinned)

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
reachable.add(n_model)
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

# The rule this demo exists for: every required field is checked for a quote as
# well as a value. Miss one out of the list and a field becomes trustable
# without evidence, silently.
for lab, key in REQUIRED:
    if ("%s.quote" % f(key)) not in UNQUOTED:
        errors.append("%s is never checked for a quote" % lab)

# ---- the deciding logic, in Python, against the same documents.
# The extraction itself cannot be checked here - it runs against OpenAI at
# execution time. What is checked is what happens to its answer.
def money(s):
    return round(float(re.sub(r"[^0-9.\-]", "", str(s or "0")) or 0), 2)


actual, reasons = {}, {}
for doc in d["documents"]:
    ex = doc["expected_extraction"]
    if ex is None:                                  # not a rate confirmation
        actual[doc["id"]] = "review"
        reasons[doc["id"]] = "Not a rate confirmation."
        continue
    missing = [lab for lab, k in REQUIRED if not str(ex.get(k, "")).strip()]
    parts = round(money(ex["linehaul"]) + money(ex["fuel_surcharge"])
                  + money(ex["accessorials"]), 2)
    total = money(ex["total_rate"])
    gap = round(abs(parts - total), 2)
    if missing:
        actual[doc["id"]] = "review"
        reasons[doc["id"]] = "Missing: " + ", ".join(missing) + "."
    elif not ex.get("all_quoted", False):
        actual[doc["id"]] = "review"
        reasons[doc["id"]] = "Not quoted from the document, so not trusted."
    elif gap > TOL:
        actual[doc["id"]] = "review"
        reasons[doc["id"]] = ("The charges add to ${:,.2f} but the document says "
                              "${:,.2f} - a ${:,.2f} difference."
                              .format(parts, total, gap))
    else:
        actual[doc["id"]] = "file"
        reasons[doc["id"]] = ""

for doc in d["documents"]:
    if actual[doc["id"]] != doc["expected_lane"]:
        errors.append("%s should be %r but the checks put it in %r"
                      % (doc["id"], doc["expected_lane"], actual[doc["id"]]))
for did, want in d["expected_reasons"].items():
    if reasons.get(did) != want:
        errors.append("%s reason is %r, expected %r" % (did, reasons.get(did), want))

lanes = sorted(set(actual.values()))
if lanes != ["file", "review"]:
    errors.append("the pinned documents only exercise: " + ", ".join(lanes))

functional = [n for n in nodes if n["type"] != "n8n-nodes-base.stickyNote"]
tally = {}
for v in actual.values():
    tally[v] = tally.get(v, 0) + 1

print("nodes: %d functional (+%d notes) | Code nodes: %d | pinned: %d | disabled: %d"
      % (len(functional), len(nodes) - len(functional), len(code_nodes), len(pin_data),
         len([n for n in nodes if n.get("disabled")])))
print("documents: %d  %s" % (len(d["documents"]), tally))
for doc in d["documents"]:
    print("  %-6s %-32s %-6s %s" % (doc["id"], doc["filename"], actual[doc["id"]],
                                    reasons[doc["id"]] or "-"))
print("VALIDATION:", "PASS" if not errors else "FAIL")
for e in errors:
    print("  -", e)
import sys
sys.path.insert(0, os.path.dirname(ROOT))
from node_versions import unverified
for line in unverified(OUT):
    print("  unverified:", line)
print("wrote", OUT)
