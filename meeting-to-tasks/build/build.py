"""Writes Meeting-Notes-to-Tasks.json.

This script is the source of truth. Edit it and re-run it:

    python build/build.py

Do not hand-edit the JSON - the next run overwrites it. If the workflow is ever
changed inside n8n and re-exported, this script and that file have diverged and
one of them has to win.

Demo-mode rules (see ../../BUILD-RULES.md): built-in n8n nodes only, no Code nodes,
fewest nodes that still tell the story, n8n's own pinned data instead of a
hand-built demo toggle, and OpenAI for every AI step.
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "sample-meetings.json")
OUT = os.path.join(ROOT, "Meeting-Notes-to-Tasks.json")

d = json.load(open(DATA, encoding="utf-8"))
co = d["consultancy"]

nodes = []


def add(name, ntype, tv, params, pos, disabled=False):
    n = {"parameters": params, "id": "e6000000-0000-4000-8000-%012d" % (len(nodes) + 1),
         "name": name, "type": ntype, "typeVersion": tv, "position": list(pos)}
    if disabled:
        n["disabled"] = True
    nodes.append(n)
    return name


def sticky(content, pos, w, h, color=7):
    add("Note " + str(len([n for n in nodes if n["type"].endswith("stickyNote")]) + 1),
        "n8n-nodes-base.stickyNote", 1,
        {"content": content, "height": h, "width": w, "color": color}, pos)


def cond(cid, left, op_type, op, right=None):
    return {"id": cid, "leftValue": left, "rightValue": "" if right is None else right,
            "operator": {"type": op_type, "operation": op}}


def rule(conditions, label, combinator="and"):
    return {"conditions": {
        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose",
                    "version": 2},
        "conditions": conditions, "combinator": combinator},
        "renameOutput": True, "outputKey": label}


# ------------------------------------------------------------------ sticky notes
sticky("""## What this does

Meeting notes go in. Every commitment somebody actually made comes out,
checked line by line against that client's signed agreement.

**In the agreement** becomes a Trello card. **Outside it** becomes a drafted
change-order email instead of unpaid work. **Genuinely ambiguous** goes to you,
because guessing is the one thing this must not do.

Two meetings in. Six commitments found, two passing remarks correctly ignored.""",
       (-1580, -420), 460, 300, 4)

sticky("""## The one that pays for the system

In the Ridgeline notes, Tom asks whether Harbourline can "also take on the
packaging redesign".

On a call that gets a *"sure, let me look at it"*. Three weeks later it is
fifteen hours of unbilled design work and an awkward conversation.

The agreement excludes **"visual identity, packaging, and any design
production"** by name. The system quotes that clause back, and drafts the
note the same afternoon - while it is still an easy conversation.

**Scope creep is not caught by discipline. It is caught the same day or
not at all.**""",
       (-1080, -420), 480, 340, 3)

sticky("""## Why four nodes are greyed out

`Create the Trello Card`, `Draft the Email to the Client`,
`Flag It for the Consultant` and `Log Every Commitment` are **disabled on
purpose**.

Nothing here writes to a board, an inbox or a spreadsheet until you connect
the account and switch the node on. You can run the whole thing, read every
verdict, and change your mind - with no trace left in a client's system.

The three sources and the three AI steps have **pinned data**, so it runs
with no accounts connected at all. Unpin a node to make it call out for real.""",
       (-580, -420), 440, 300, 6)

# ------------------------------------------------------------------ 1. trigger
t = add("Run the Demo", "n8n-nodes-base.manualTrigger", 1, {}, (-1560, 60))

# ------------------------------------------------------------------ 2. sources
n_meetings = add("Meeting Notes (Google Docs)", "n8n-nodes-base.googleDocs", 2, {
    "operation": "get",
    "documentURL": "YOUR_GOOGLE_DOC_ID_HERE",
    "simple": True,
}, (-1360, -50))

n_scopes = add("Signed Scopes of Work", "n8n-nodes-base.googleSheets", 4.5, {
    "documentId": {"__rl": True, "value": "YOUR_GOOGLE_SHEET_ID_HERE", "mode": "id"},
    "sheetName": {"__rl": True, "value": "Scopes of Work", "mode": "name"},
    "options": {},
}, (-1360, 180))

# ------------------------------------------------------------------ 3. the join
# The scope for this client and no other is attached. A client's agreement is
# never in front of the model while it judges a different client's commitment -
# it was never fetched, so there is nothing to leak.
n_join = add("Attach the Scope for That Client", "n8n-nodes-base.merge", 3, {
    "mode": "combine",
    "combineBy": "combineByFields",
    "fieldsToMatchString": "client_id",
    "joinMode": "enrichInput1",
    "options": {},
}, (-1140, 60))

# ------------------------------------------------------------------ 4. the AI
n_model = add("OpenAI Chat Model", "@n8n/n8n-nodes-langchain.lmChatOpenAi", 1.2, {
    "model": {"__rl": True, "value": "gpt-4.1-mini", "mode": "list",
              "cachedResultName": "gpt-4.1-mini"},
    "options": {"temperature": 0.1},
}, (-600, 380))

EXTRACT = """You are reading the notes from a client meeting. Pull out every commitment
somebody actually made.

A commitment has an owner, and usually a time. "I will send X by Friday" is a commitment.
"We should look at Canada eventually" is not - nobody agreed to anything. An idea raised
and left open is not a commitment, and neither is an observation. Leaving those out is
part of the job: a list that includes every passing remark gets ignored within a week.

owner is "us" when """ + co["name"] + """ owes it, and "client" when the client owes it.
owner_name is the person's name as written in the notes.
due_date: resolve what was said against the meeting date below and return YYYY-MM-DD.
Leave it empty if no time was given. Never invent one.
quote: copy the sentence it came from word for word. Do not tidy it up.

MEETING: {{ $json.title }} ({{ $json.date }})
CLIENT: {{ $json.name }}

NOTES:
{{ $json.notes }}"""

n_extract = add("Pull Out the Commitments",
                "@n8n/n8n-nodes-langchain.informationExtractor", 1, {
                    "text": "=" + EXTRACT,
                    "schemaType": "fromJson",
                    "jsonSchemaExample": json.dumps({"commitments": [{
                        "what": "Send the revised positioning statement",
                        "owner": "us",
                        "owner_name": "Dana",
                        "due_date": "2026-08-28",
                        "quote": "Agreed I would tighten it and send the revised "
                                 "version across by Friday.",
                    }]}, indent=2),
                    "options": {},
                }, (-920, 60))

n_split = add("One Item per Commitment", "n8n-nodes-base.splitOut", 1, {
    "fieldToSplitOut": "output.commitments",
    "options": {},
}, (-700, 60))

# One Set node holds all the plumbing, so every node after it reads plain $json.
n_line_up = add("Line It Up Against the Scope", "n8n-nodes-base.set", 3.4, {
    "includeOtherFields": True,
    "assignments": {"assignments": [
        {"id": "p1", "name": "client_name", "type": "string",
         "value": "={{ $('Attach the Scope for That Client').item.json.name }}"},
        {"id": "p2", "name": "sow_title", "type": "string",
         "value": "={{ $('Attach the Scope for That Client').item.json.sow_title }}"},
        {"id": "p3", "name": "sow_scope", "type": "string",
         "value": "={{ $('Attach the Scope for That Client').item.json.sow_scope }}"},
        {"id": "p4", "name": "sow_excludes", "type": "string",
         "value": "={{ $('Attach the Scope for That Client').item.json.sow_excludes }}"},
        {"id": "p5", "name": "contact_name", "type": "string",
         "value": "={{ $('Attach the Scope for That Client').item.json.contact_name }}"},
        {"id": "p6", "name": "contact_email", "type": "string",
         "value": "={{ $('Attach the Scope for That Client').item.json.contact_email }}"},
        {"id": "p7", "name": "trello_board", "type": "string",
         "value": "={{ $('Attach the Scope for That Client').item.json.trello_board }}"},
        {"id": "p8", "name": "meeting_title", "type": "string",
         "value": "={{ $('Attach the Scope for That Client').item.json.title }}"},
        {"id": "p9", "name": "meeting_date", "type": "string",
         "value": "={{ $('Attach the Scope for That Client').item.json.date }}"},
        {"id": "p10", "name": "meeting_id", "type": "string",
         "value": "={{ $('Attach the Scope for That Client').item.json.meeting_id }}"},
    ]},
    "options": {},
}, (-480, 60))

CHECK = """Decide whether one commitment falls inside a signed agreement.

verdict must be exactly one of: in_scope, out_of_scope, unclear

- in_scope: the agreement covers it. Something the CLIENT owes is in_scope when it is an
  input the covered work depends on - it is not billable, but it blocks us, so it belongs
  on the board.
- out_of_scope: the agreement excludes it by name, or it is plainly new work the agreement
  never contemplated.
- unclear: it could honestly be read either way, or it is partly covered and partly
  excluded. Use this. Saying so is far more useful than a confident guess, because a wrong
  in_scope costs unpaid work and a wrong out_of_scope is an awkward email to a client.

sow_clause: quote the words from the agreement below that decide it, exactly as written.
reason: one or two plain sentences. No hedging, no restating the question.

AGREEMENT: {{ $json.sow_title }}
IN SCOPE: {{ $json.sow_scope }}
EXCLUDED: {{ $json.sow_excludes }}

COMMITMENT: {{ $json.what }}
OWED BY: {{ $json.owner === 'us' ? '""" + co["name"] + """' : $json.owner_name + ' (the client)' }}
FROM THE NOTES: "{{ $json.quote }}\""""

n_check = add("Check It Against the Scope",
              "@n8n/n8n-nodes-langchain.informationExtractor", 1, {
                  "text": "=" + CHECK,
                  "schemaType": "fromJson",
                  "jsonSchemaExample": json.dumps({
                      "verdict": "in_scope",
                      "sow_clause": "One positioning statement and a supporting "
                                    "messaging framework.",
                      "reason": "A revision to the positioning statement, which the "
                                "agreement covers.",
                  }, indent=2),
                  "options": {},
              }, (-260, 60))

# ------------------------------------------------------------------ 5. the routing
# The model gives a verdict. The wiring decides what happens - including the
# fallback, which catches a verdict the model was never supposed to return.
n_switch = add("In Scope, or Not?", "n8n-nodes-base.switch", 3.2, {
    "rules": {"values": [
        rule([cond("v1", "={{ $json.output.verdict }}", "string", "equals", "in_scope")],
             "In the signed scope"),
        rule([cond("v2", "={{ $json.output.verdict }}", "string", "equals", "out_of_scope")],
             "Outside the signed scope"),
        rule([cond("v3", "={{ $json.output.verdict }}", "string", "equals", "unclear")],
             "Could be read both ways"),
    ]},
    "options": {"fallbackOutput": "extra",
                "renameFallbackOutput": "Anything else - a person looks at it"},
}, (-40, 60))

L = "Line It Up Against the Scope"

# ------------------------------------------------------------------ 6. in scope
n_trello = add("Create the Trello Card", "n8n-nodes-base.trello", 1, {
    "resource": "card",
    "listId": "YOUR_TRELLO_LIST_ID_HERE",
    "name": "={{ $('" + L + "').item.json.what }}",
    "description": ("=**Owner:** {{ $('" + L + "').item.json.owner === 'us' ? '"
                    + co["name"] + "' : $('" + L + "').item.json.owner_name "
                    "+ ' (client) - we are blocked until this lands' }}\n"
                    "**From:** {{ $('" + L + "').item.json.meeting_title }} "
                    "({{ $('" + L + "').item.json.meeting_date }})\n\n"
                    "> {{ $('" + L + "').item.json.quote }}\n\n"
                    "**Covered by:** {{ $json.output.sow_clause }}\n"
                    "{{ $json.output.reason }}"),
    "additionalFields": {"due": "={{ $('" + L + "').item.json.due_date }}T17:00:00"},
}, (240, -140), disabled=True)

# ------------------------------------------------------------------ 7. out of scope
n_note = add("Write the Change-Order Note", "@n8n/n8n-nodes-langchain.chainLlm", 1.4, {
    "promptType": "define",
    "text": "=" + """Write a short note to a client about something they asked for that is not
covered by the signed agreement.

client contact: {{ $('""" + L + """').item.json.contact_name }}
what they asked for: {{ $('""" + L + """').item.json.what }}
what they said: "{{ $('""" + L + """').item.json.quote }}"
the agreement: {{ $('""" + L + """').item.json.sow_title }}
the clause it falls outside: {{ $json.output.sow_clause }}
why: {{ $json.output.reason }}

Rules:
- You want the work. This is a scoping note, not a refusal, and it should not read as one.
- Name the specific thing, and say plainly that it sits outside the current agreement.
- Never state a price, a rate, a number of hours, or a delivery date. You do not know them,
  and a number invented here is a number you will be held to.
- Offer one next step: a short call, or a separate estimate.
- Under 120 words. No apologising, no "just", no exclamation marks.
- Sign off as """ + co["owner"] + ", " + co["name"] + """.
- Return the body only, with no subject line.""",
    "messages": {"messageValues": []},
}, (240, 80))

n_gmail = add("Draft the Email to the Client", "n8n-nodes-base.gmail", 2.1, {
    "resource": "draft",
    "subject": "=Following up on one thing from {{ $('" + L + "').item.json.meeting_title }}",
    "emailType": "text",
    "message": "={{ $json.text }}",
    "options": {"sendTo": "={{ $('" + L + "').item.json.contact_email }}"},
}, (480, 80), disabled=True)

# ------------------------------------------------------------------ 8. unclear
n_slack = add("Flag It for the Consultant", "n8n-nodes-base.slack", 2.3, {
    "select": "channel",
    "channelId": {"__rl": True, "value": co["review_channel"], "mode": "name"},
    "text": ("=*Scope call needed* - {{ $('" + L + "').item.json.client_name }}\n"
             "> {{ $('" + L + "').item.json.what }}\n"
             "{{ $json.output.reason }}\n"
             "_{{ $('" + L + "').item.json.meeting_title }}, "
             "{{ $('" + L + "').item.json.meeting_date }}_"),
    "otherOptions": {},
}, (240, 320), disabled=True)

# ------------------------------------------------------------------ 9. the log
n_log = add("Log Every Commitment", "n8n-nodes-base.googleSheets", 4.5, {
    "operation": "appendOrUpdate",
    "documentId": {"__rl": True, "value": "YOUR_GOOGLE_SHEET_ID_HERE", "mode": "id"},
    "sheetName": {"__rl": True, "value": "Commitments", "mode": "name"},
    "columns": {"mappingMode": "defineBelow", "matchingColumns": ["Commitment"], "value": {
        "Client": "={{ $('" + L + "').item.json.client_name }}",
        "Meeting": "={{ $('" + L + "').item.json.meeting_title }} "
                   "({{ $('" + L + "').item.json.meeting_date }})",
        "Commitment": "={{ $('" + L + "').item.json.what }}",
        "Owner": "={{ $('" + L + "').item.json.owner }}",
        "Due": "={{ $('" + L + "').item.json.due_date }}",
        "Verdict": "={{ $('In Scope, or Not?').item.json.output.verdict }}",
        "Clause": "={{ $('In Scope, or Not?').item.json.output.sow_clause }}",
        "Reason": "={{ $('In Scope, or Not?').item.json.output.reason }}",
    }},
    "options": {},
}, (760, 60), disabled=True)

# ------------------------------------------------------------------ connections
connections = {}


def wire(src, dst, si=0, di=0, kind="main"):
    c = connections.setdefault(src, {}).setdefault(kind, [])
    while len(c) <= si:
        c.append([])
    c[si].append({"node": dst, "type": kind, "index": di})


wire(t, n_meetings)
wire(t, n_scopes)
wire(n_meetings, n_join, 0, 0)          # notes into input 1
wire(n_scopes, n_join, 0, 1)            # scopes into input 2, matched on client_id
wire(n_join, n_extract)
wire(n_extract, n_split)
wire(n_split, n_line_up)
wire(n_line_up, n_check)
wire(n_check, n_switch)
wire(n_switch, n_trello, 0)             # in the signed scope
wire(n_switch, n_note, 1)               # outside it
wire(n_switch, n_slack, 2)              # could be read both ways
wire(n_switch, n_slack, 3)              # fallback: an unexpected verdict
wire(n_note, n_gmail)
wire(n_trello, n_log)
wire(n_gmail, n_log)
wire(n_slack, n_log)

for root in (n_extract, n_check, n_note):
    wire(n_model, root, 0, 0, "ai_languageModel")

# ------------------------------------------------------------------ pinned data
COMMITMENT_FIELDS = ("what", "owner", "owner_name", "due_date", "quote")
VERDICT_FIELDS = ("verdict", "sow_clause", "reason")

hints = d["demo_hint"]
ordered = [c for m in d["meetings"] for c in hints[m["meeting_id"]]]

# What the model writes for the packaging request. Pinned so the demo runs with
# no OpenAI key; it is generated output, which is why it lives with the
# generator rather than in sample-meetings.json.
CHANGE_ORDER_DRAFT = (
    "Hi Kate,\n\n"
    "One thing to flag from Thursday. Tom asked whether we could take on the packaging "
    "redesign for the Q1 line. We would like to - it is the natural next step once the "
    "positioning lands, and we would be starting from a running start.\n\n"
    "It does sit outside our current agreement, though. That one covers positioning and "
    "messaging, and specifically excludes packaging and design production, so it needs to "
    "be set up as its own piece of work rather than folded into this one.\n\n"
    "Happy to put together an outline and an estimate, or to talk it through on a call "
    "next week if that is easier. Whichever you prefer.\n\n"
    "Dana\n"
    "Harbourline Consulting"
)

pin_data = {
    n_meetings: [{"json": m} for m in d["meetings"]],
    n_scopes: [{"json": c} for c in d["clients"]],
    n_extract: [
        {"json": {"output": {"commitments": [
            {k: c[k] for k in COMMITMENT_FIELDS} for c in hints[m["meeting_id"]]
        ]}}}
        for m in d["meetings"]
    ],
    n_check: [{"json": {"output": {k: c[k] for k in VERDICT_FIELDS}}} for c in ordered],
    n_note: [{"json": {"text": CHANGE_ORDER_DRAFT}}],
}

wf = {"name": "Meeting Notes to Tasks", "nodes": nodes, "connections": connections,
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

# The two pinned AI steps have to line up, or the demo tells a story the canvas
# does not: one verdict per commitment, in the order Split Out produces them.
n_commitments = sum(len(v) for v in hints.values())
if len(pin_data[n_check]) != n_commitments:
    errors.append("pinned verdicts (%d) do not match pinned commitments (%d)"
                  % (len(pin_data[n_check]), n_commitments))
for c in ordered:
    if c["verdict"] not in ("in_scope", "out_of_scope", "unclear"):
        errors.append("unknown verdict in the sample data: %r" % c["verdict"])
    if c["quote"] not in next(m["notes"] for m in d["meetings"]
                              if c in hints[m["meeting_id"]]):
        errors.append("quote is not in the meeting notes verbatim: %r" % c["what"])
# Every in-scope commitment reaches the Trello node, which maps a due date.
for c in ordered:
    if c["verdict"] == "in_scope" and not c["due_date"]:
        errors.append("in-scope commitment with no due date would break the "
                      "Trello card: %r" % c["what"])

functional = [n for n in nodes if n["type"] != "n8n-nodes-base.stickyNote"]
code_nodes = [n for n in functional if n["type"] == "n8n-nodes-base.code"]
if code_nodes:
    errors.append("Code nodes present: " + ", ".join(n["name"] for n in code_nodes))

by_verdict = {}
for c in ordered:
    by_verdict[c["verdict"]] = by_verdict.get(c["verdict"], 0) + 1

print("nodes: %d functional (+%d notes) | Code nodes: %d | pinned: %d | disabled: %d"
      % (len(functional), len(nodes) - len(functional), len(code_nodes), len(pin_data),
         len([n for n in nodes if n.get("disabled")])))
print("commitments: %d  %s" % (n_commitments, by_verdict))
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
