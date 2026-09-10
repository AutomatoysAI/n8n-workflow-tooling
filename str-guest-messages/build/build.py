"""Writes STR-Guest-Message-Assistant.json.

This script is the source of truth. Edit it and re-run it:

    python build/build.py

Do not hand-edit the JSON - the next run overwrites it.

Demo-mode rules (see ../../BUILD-RULES.md): built-in n8n nodes only, no Code nodes,
fewest nodes that still tell the story, n8n's own pinned data instead of a
hand-built demo toggle.

The isolation - one property's information, never another's - is a Merge node
here rather than a filter written in JavaScript. Two streams go in, they are
matched on property_id, and only the matching guide comes out the other side.
That is the same guarantee, drawn on the canvas where a client can see it.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "sample-data.json")
OUT = os.path.join(ROOT, "STR-Guest-Message-Assistant.json")

d = json.load(open(DATA, encoding="utf-8"))
company = d["company"]

nodes = []


def add(name, ntype, tv, params, pos):
    nodes.append({"parameters": params, "id": "f6000000-0000-4000-8000-%012d" % (len(nodes) + 1),
                  "name": name, "type": ntype, "typeVersion": tv, "position": list(pos)})
    return name


def sticky(content, pos, w, h, color=7):
    n = len([x for x in nodes if x["type"].endswith("stickyNote")]) + 1
    add("Note %d" % n, "n8n-nodes-base.stickyNote", 1,
        {"content": content, "height": h, "width": w, "color": color}, pos)


# ------------------------------------------------------------------ sticky notes
sticky("""## What this does

A guest sends a message. The system works out which booking it belongs to, pulls
**that property's guide and no other**, then either drafts a reply or hands the
message to a person.

Seven messages, three properties. Three get drafted, four go to a human.

Nothing here sends anything to a guest. Email is drafted for someone to approve.""",
       (-1720, -420), 460, 280, 4)

sticky("""## The isolation is a node, not a promise

**Attach the Guide for That Property** is a Merge. Guest messages come in one
side, property guides the other, and they are matched on `property_id`.

The guide for a property the guest has not booked is never attached, so the AI
is never given it. There is nothing to refuse and nothing to talk around.

The naive build puts every property in one searchable pile and asks the AI
nicely to use the right one. That is a **request**. This is a **join**.

Watch MSG-2 and MSG-7 to see it hold.""",
       (-1220, -420), 470, 300, 3)

sticky("""## Running it, and what is deliberately missing

The three source nodes and the reply writer have **pinned data**, so this runs
with no accounts connected. Unpin a node to make it call out for real; the AI
nodes need an OpenAI credential.

**Demo scope.** A production build adds a deterministic policy layer after the
classifier - so the model can ask for a human but can never authorise itself to
skip one - plus a check that every fact in a reply really came from the attached
guide. Both are worth building when a client is paying. Both would be noise on a
one-screen demo.""",
       (-740, -420), 470, 300, 6)

# ------------------------------------------------------------------ sources
t = add("Run the Demo", "n8n-nodes-base.manualTrigger", 1, {}, (-1700, 60))

n_msgs = add("Get New Guest Messages (PMS)", "n8n-nodes-base.httpRequest", 4.2, {
    "url": "https://public.api.hospitable.com/v2/messages",
    "options": {},
}, (-1480, 60))

n_bookings = add("Get the Bookings (PMS)", "n8n-nodes-base.httpRequest", 4.2, {
    "url": "https://public.api.hospitable.com/v2/reservations",
    "options": {},
}, (-1480, 280))

n_guides = add("Property Guides (Notion)", "n8n-nodes-base.notion", 2.2, {
    "resource": "databasePage",
    "operation": "getAll",
    "databaseId": {"__rl": True, "value": "YOUR_NOTION_DATABASE_ID", "mode": "id"},
    "returnAll": True,
    "options": {},
}, (-1480, 480))

# ------------------------------------------------------------------ the two joins
n_join_booking = add("Match the Booking", "n8n-nodes-base.merge", 3, {
    "mode": "combine",
    "combineBy": "combineByFields",
    "fieldsToMatchString": "booking_ref",
    "joinMode": "enrichInput1",
    "options": {},
}, (-1240, 140))

n_join_guide = add("Attach the Guide for That Property", "n8n-nodes-base.merge", 3, {
    "mode": "combine",
    "combineBy": "combineByFields",
    "fieldsToMatchString": "property_id",
    "joinMode": "enrichInput1",
    "options": {},
}, (-1000, 260))

# ------------------------------------------------------------------ the AI
n_model = add("OpenAI Chat Model", "@n8n/n8n-nodes-langchain.lmChatOpenAi", 1.2, {
    "model": {"__rl": True, "value": "gpt-4.1-mini", "mode": "list",
              "cachedResultName": "gpt-4.1-mini"},
    "options": {"temperature": 0.2},
}, (-620, 480))

CLASSIFY_INPUT = """=Property: {{ $json.name }}
Guest: {{ $json.guest_name }}, booked {{ $json.check_in }} to {{ $json.check_out }}

THE PROPERTY GUIDE - THIS PROPERTY ONLY
{{ JSON.stringify($json.facts, null, 2) }}

THE GUEST'S MESSAGE
{{ $json.body }}"""

n_classify = add("Can We Answer This?", "@n8n/n8n-nodes-langchain.textClassifier", 1, {
    "inputText": CLASSIFY_INPUT,
    "categories": {"categories": [
        {"category": "Answer it",
         "description": "The property guide above contains the information needed to answer this "
                        "message, and the message is a straightforward question about the stay - "
                        "access, wifi, check-in or check-out times, house rules, appliances, "
                        "parking, rubbish. Nothing about money, nothing upsetting, nothing urgent."},
        {"category": "A person handles it",
         "description": "Anything about money, refunds, cancellations or changing a booking; any "
                        "complaint; anything that sounds like a safety problem such as gas, fire, "
                        "flooding, or a guest who cannot get in; anything angry or distressed."},
        {"category": "Not in the guide",
         "description": "A reasonable question that the property guide above simply does not "
                        "answer, or a question about a different property from the one in this "
                        "booking. Do not guess - if the guide does not say it, this is the "
                        "category."},
    ]},
    "options": {"fallback": "other"},
}, (-760, 260))

REPLY_PROMPT = """=You write guest messages for """ + company["name"] + """, a short-term rental manager.

Answer the guest using ONLY the property guide below. You have not been given any other property's information. If something is not in the guide, do not invent it.

PROPERTY: {{ $json.name }}
GUEST: {{ $json.guest_name }}
DATES: {{ $json.check_in }} to {{ $json.check_out }}

THE PROPERTY GUIDE - THIS PROPERTY ONLY
{{ JSON.stringify($json.facts, null, 2) }}

THE GUEST'S MESSAGE
{{ $json.body }}

HOW TO WRITE IT
Warm, short, plain. Use the guest's first name. Give the answer in the first line or two - guests are usually standing in a doorway holding a bag. Contractions are fine. No exclamation marks, no "I hope this finds you well", no marketing language.

If the answer is no, say so kindly and directly, and offer the next best thing if there is one.

Never invent prices, times, codes, policies or facilities. Sign off with """ + company["signoff"] + """ and nothing else. Return the message only."""

n_reply = add("Write the Reply", "@n8n/n8n-nodes-langchain.chainLlm", 1.4, {
    "promptType": "define",
    "text": REPLY_PROMPT,
    "messages": {"messageValues": []},
}, (-480, 100))

# ------------------------------------------------------------------ delivery
n_gmail = add("Create the Draft (Human Approves)", "n8n-nodes-base.gmail", 2.1, {
    "resource": "draft",
    "subject": "=Re: your stay at {{ $('Attach the Guide for That Property').item.json.name }}",
    "emailType": "text",
    "message": "={{ $json.text }}",
    "options": {"sendTo": "={{ $('Attach the Guide for That Property').item.json.guest_email }}"},
}, (-240, 100))

n_slack = add("Hand It to a Person", "n8n-nodes-base.slack", 2.3, {
    "select": "channel",
    "channelId": {"__rl": True, "value": company["escalation_channel"], "mode": "name"},
    "text": ("=*{{ $json.name }}* - {{ $json.guest_name }} ({{ $json.booking_ref }})\n"
             "> {{ $json.body }}"),
    "otherOptions": {},
}, (-480, 400))

n_log = add("Log Every Message", "n8n-nodes-base.googleSheets", 4.5, {
    "operation": "appendOrUpdate",
    "documentId": {"__rl": True, "value": "YOUR_GOOGLE_SHEET_ID_HERE", "mode": "id"},
    "sheetName": {"__rl": True, "value": "Guest Messages", "mode": "name"},
    "columns": {"mappingMode": "defineBelow", "matchingColumns": ["Message"], "value": {
        "Message": "={{ $('Attach the Guide for That Property').item.json.message_id }}",
        "Property": "={{ $('Attach the Guide for That Property').item.json.name }}",
        "Guest": "={{ $('Attach the Guide for That Property').item.json.guest_name }}",
        "They Asked": "={{ $('Attach the Guide for That Property').item.json.body }}",
        "Outcome": "={{ $json.text ? 'Draft waiting for approval' : 'Sent to a person' }}",
        "Draft": "={{ $json.text || '' }}",
    }},
    "options": {},
}, (0, 260))

# ------------------------------------------------------------------ connections
connections = {}


def wire(src, dst, si=0, di=0, kind="main"):
    c = connections.setdefault(src, {}).setdefault(kind, [])
    while len(c) <= si:
        c.append([])
    c[si].append({"node": dst, "type": kind, "index": di})


wire(t, n_msgs)
wire(t, n_bookings)
wire(t, n_guides)
wire(n_msgs, n_join_booking, 0, 0)
wire(n_bookings, n_join_booking, 0, 1)
wire(n_join_booking, n_join_guide, 0, 0)
wire(n_guides, n_join_guide, 0, 1)
wire(n_join_guide, n_classify)
wire(n_model, n_classify, 0, 0, "ai_languageModel")
wire(n_model, n_reply, 0, 0, "ai_languageModel")
wire(n_classify, n_reply, 0)        # Answer it
wire(n_classify, n_slack, 1)        # A person handles it
wire(n_classify, n_slack, 2)        # Not in the guide
wire(n_classify, n_slack, 3)        # fallback: anything else
wire(n_reply, n_gmail)
wire(n_gmail, n_log)
wire(n_slack, n_log)

# ------------------------------------------------------------------ pinned data
by_ref = {b["booking_ref"]: b for b in d["bookings"]}

pin_messages = [{"json": {"message_id": m["message_id"], "booking_ref": m["booking_ref"],
                          "received_at": m["received_at"], "body": m["body"]}}
                for m in d["messages"]]

pin_bookings = [{"json": b} for b in d["bookings"]]

pin_guides = [{"json": {"property_id": p["property_id"], "name": p["name"],
                        "address": p["address"], "owner_name": p["owner_name"],
                        "facts": p["facts"]}}
              for p in d["properties"]]

ANSWERABLE = ["MSG-1", "MSG-2", "MSG-3"]
by_msg = {m["message_id"]: m for m in d["messages"]}
pin_replies = [{"json": {"text": by_msg[i]["demo_hint"]["reply"]}} for i in ANSWERABLE]

pin_data = {
    n_msgs: pin_messages,
    n_bookings: pin_bookings,
    n_guides: pin_guides,
    n_reply: pin_replies,
}

wf = {"name": "STR Guest Message Assistant", "nodes": nodes, "connections": connections,
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
reachable.add(n_model)
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
