"""Writes Ask-Our-Documents.json.

This script is the source of truth. Edit it and re-run it:

    python build/build.py

Do not hand-edit the JSON - the next run overwrites it. If the workflow is ever
changed inside n8n and re-exported, this script and that file have diverged and
one of them has to win.

Demo-mode rules (see ../../BUILD-RULES.md): built-in n8n nodes only, no Code nodes,
fewest nodes that still tell the story, n8n's own pinned data instead of a
hand-built demo toggle, and OpenAI for every AI step.

This is the one demo built around n8n's AI Agent node rather than a fixed chain.
The agent picks which tools to call; the Switch after it decides what happens to
the answer, which is the only part that is guaranteed.
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "sample-company.json")
OUT = os.path.join(ROOT, "Ask-Our-Documents.json")

d = json.load(open(DATA, encoding="utf-8"))
co = d["company"]

nodes = []


def add(name, ntype, tv, params, pos, disabled=False):
    n = {"parameters": params, "id": "e9000000-0000-4000-8000-%012d" % (len(nodes) + 1),
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


def sheet(name_, tab, extra=None, tool_desc=None, pos=(0, 0)):
    params = {
        "documentId": {"__rl": True, "value": "YOUR_GOOGLE_SHEET_ID_HERE", "mode": "id"},
        "sheetName": {"__rl": True, "value": tab, "mode": "name"},
        "options": {},
    }
    if extra:
        params.update(extra)
    if tool_desc:
        params["descriptionType"] = "manual"
        params["toolDescription"] = tool_desc
        return add(name_, "n8n-nodes-base.googleSheetsTool", 4.5, params, pos)
    return add(name_, "n8n-nodes-base.googleSheets", 4.5, params, pos)


# ------------------------------------------------------------------ sticky notes
sticky("""## What this does

Somebody on the team asks a question. The assistant looks the answer up in the
studio's **own** documents, answers, and **names the file it came from**.

When the handbook does not cover it, it says so and points at a person. It does
not fall back on what it happens to know.

Four questions in: two answered and sourced, one honest "I don't know", and one
where the model answered from general knowledge and **got stopped**.""",
       (-1720, -460), 460, 300, 4)

sticky("""## Nothing here is "trained on your business"

Clients ask for an AI trained on their company. What actually works is
**looking it up** - the assistant reads the current documents every time it is
asked, and cites them.

That sounds like less. It is much more:

- A wrong answer is fixed by **editing a document**, not retraining anything
- It reads today's prices, not the prices as of the day it was built
- It can tell you where an answer came from

Style is the one thing worth teaching by example. **Facts by lookup, voice by
example.** Neither of them is training.""",
       (-1220, -460), 480, 340, 3)

sticky("""## The agent chooses. The wiring decides.

`Ask the Assistant` is an **AI Agent** - it is handed three tools and picks
which to use. Question 2 needs two of them, and nobody wired that route.

That is the point of an agent, and also the risk: the path is not predictable,
so it cannot be the thing that keeps you safe.

So every answer has to end with a **SOURCE** line, and `Did It Cite a Source?`
checks it. **An answer with no source is treated as a refusal**, even when it
is a good answer - see question 4. The prompt makes a request; the Switch is
what enforces it.""",
       (-700, -460), 490, 340, 6)

# ------------------------------------------------------------------ the flow
t = add("Run the Demo", "n8n-nodes-base.manualTrigger", 1, {}, (-1700, 120))

n_questions = sheet("Questions from the Team", "Questions", pos=(-1480, 120))

SYSTEM = """You are the in-house assistant for %s, %s. You answer questions from staff.

Answer ONLY from the tools you have been given. You have the staff handbook, the client
records, and the studio calendar. If the answer is not in them, you do not know it.

Every reply ends with a line in exactly this form:
SOURCE: <the handbook section, or the record, that the answer came from>
or, when you could not find it:
SOURCE: none

Rules that matter more than being helpful:
- Never answer from your own general knowledge. Employment law, common practice and what other
  companies usually do are all off limits, however confident you are. This studio's rules are
  whatever its handbook says, and nothing else.
- If the handbook does not cover it, say so plainly, say who to ask, and stop. That is a good
  answer, not a failure.
- Never guess a price, a date, a person's name or a policy. Never soften a rule to be helpful.
- Use more than one tool when the question needs it. A question about a client's pricing usually
  needs the policy and the client record.
- Keep it short. Lead with the answer.""" % (co["name"], co["what"])

n_agent = add("Ask the Assistant", "@n8n/n8n-nodes-langchain.agent", 1.7, {
    "promptType": "define",
    "text": "={{ $json.question }}",
    "options": {"systemMessage": SYSTEM},
}, (-1240, 120))

# ------------------------------------------------------------------ the tools
n_model = add("OpenAI Chat Model", "@n8n/n8n-nodes-langchain.lmChatOpenAi", 1.2, {
    "model": {"__rl": True, "value": "gpt-4.1-mini", "mode": "list",
              "cachedResultName": "gpt-4.1-mini"},
    "options": {"temperature": 0},
}, (-1420, 400))

# One conversation per person, not one for the whole studio.
n_memory = add("Remember the Conversation", "@n8n/n8n-nodes-langchain.memoryBufferWindow", 1.3, {
    "sessionIdType": "customKey",
    "sessionKey": "={{ $json.asked_by }}",
    "contextWindowLength": 10,
}, (-1280, 400))

n_tool_handbook = sheet(
    "Search the Staff Handbook", "Handbook",
    tool_desc="The staff handbook for " + co["name"] + ". One row per policy, with a topic, the "
              "policy text, and the handbook section it comes from. Use this for anything about "
              "how the studio works - leave, expenses, remote days, pricing and discounts, "
              "chasing late payment, onboarding. Quote the source column when you answer.",
    pos=(-1120, 400))

n_tool_clients = sheet(
    "Look Up a Client", "Clients",
    tool_desc="The client records. One row per client, with the account lead, the commercial "
              "arrangement, the renewal date and notes. Use this whenever a question names a "
              "client or asks who looks after something.",
    pos=(-960, 400))

n_tool_calendar = add("Check the Calendar", "n8n-nodes-base.googleCalendarTool", 1.3, {
    "operation": "getAll",
    "calendar": {"__rl": True, "value": "YOUR_CALENDAR_ID_HERE", "mode": "id"},
    "options": {},
    "descriptionType": "manual",
    "toolDescription": "The studio calendar. Use this for questions about when something is "
                       "happening, who is in a meeting, or what is on a given day.",
}, (-800, 400))

# ------------------------------------------------------------------ the guardrail
# The agent is asked to cite. This is what checks that it did. Order matters:
# "SOURCE: none" also contains "SOURCE:", so it has to be tested first.
n_switch = add("Did It Cite a Source?", "n8n-nodes-base.switch", 3.2, {
    "rules": {"values": [
        rule([cond("g1", "={{ $json.output }}", "string", "contains", "SOURCE: none")],
             "It said it does not know"),
        rule([cond("g2", "={{ $json.output }}", "string", "contains", "SOURCE:")],
             "Answered, and named the source"),
    ]},
    "options": {"fallbackOutput": "extra",
                "renameFallbackOutput": "No source given - not trusted"},
}, (-1000, 120))

Q = "Questions from the Team"

n_post = add("Post the Answer to the Team", "n8n-nodes-base.slack", 2.3, {
    "select": "channel",
    "channelId": {"__rl": True, "value": co["answers_channel"], "mode": "name"},
    "text": "=*{{ $('" + Q + "').item.json.asked_by }} asked:* "
            "{{ $('" + Q + "').item.json.question }}\n\n{{ $json.output }}",
    "otherOptions": {},
}, (-740, 0), disabled=True)

n_human = add("Ask a Person Instead", "n8n-nodes-base.slack", 2.3, {
    "select": "channel",
    "channelId": {"__rl": True, "value": co["people_channel"], "mode": "name"},
    "text": "=*The handbook could not answer this one.*\n"
            "{{ $('" + Q + "').item.json.asked_by }} asked: "
            "{{ $('" + Q + "').item.json.question }}\n"
            "_Whoever answers: this is worth adding to the handbook._",
    "otherOptions": {},
}, (-740, 240), disabled=True)

# The log is the product. Every question the documents could not answer is a
# line on the to-do list for the documents.
n_log = add("Log Every Question", "n8n-nodes-base.googleSheets", 4.5, {
    "operation": "append",
    "documentId": {"__rl": True, "value": "YOUR_GOOGLE_SHEET_ID_HERE", "mode": "id"},
    "sheetName": {"__rl": True, "value": "Questions Asked", "mode": "name"},
    "columns": {"mappingMode": "defineBelow", "value": {
        "Asked By": "={{ $('" + Q + "').item.json.asked_by }}",
        "Question": "={{ $('" + Q + "').item.json.question }}",
        "Answer": "={{ $('Did It Cite a Source?').item.json.output }}",
        "Cited": "={{ $('Did It Cite a Source?').item.json.output.includes('SOURCE:') && "
                 "!$('Did It Cite a Source?').item.json.output.includes('SOURCE: none') "
                 "? 'yes' : 'no' }}",
        "Handbook Gap": "={{ $('Did It Cite a Source?').item.json.output.includes('SOURCE:') && "
                        "!$('Did It Cite a Source?').item.json.output.includes('SOURCE: none') "
                        "? '' : 'yes - the documents do not cover this' }}",
    }},
    "options": {},
}, (-480, 120), disabled=True)

# ------------------------------------------------------------------ connections
connections = {}


def wire(src, dst, si=0, di=0, kind="main"):
    c = connections.setdefault(src, {}).setdefault(kind, [])
    while len(c) <= si:
        c.append([])
    c[si].append({"node": dst, "type": kind, "index": di})


wire(t, n_questions)
wire(n_questions, n_agent)
wire(n_agent, n_switch)
wire(n_switch, n_human, 0)              # it said it does not know
wire(n_switch, n_post, 1)               # answered and cited
wire(n_switch, n_human, 2)              # fallback: no source, not trusted
wire(n_post, n_log)
wire(n_human, n_log)

wire(n_model, n_agent, 0, 0, "ai_languageModel")
wire(n_memory, n_agent, 0, 0, "ai_memory")
for tool in (n_tool_handbook, n_tool_clients, n_tool_calendar):
    wire(tool, n_agent, 0, 0, "ai_tool")

# ------------------------------------------------------------------ pinned data
pin_data = {
    n_questions: [{"json": q} for q in d["questions"]],
    n_agent: [{"json": {"output": d["demo_answers"][q["question_id"]]}}
              for q in d["questions"]],
}

wf = {"name": "Ask Our Documents", "nodes": nodes, "connections": connections,
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
for sub in (n_model, n_memory, n_tool_handbook, n_tool_clients, n_tool_calendar):
    reachable.add(sub)  # sub-nodes hang off the agent, not off the main flow
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

# The agent must be handed real tools, or it is a chain wearing a costume.
tool_nodes = [src for src, k in connections.items() if "ai_tool" in k]
if len(tool_nodes) < 3:
    errors.append("the agent has %d tools and the demo needs three - a single-tool agent is "
                  "a lookup with extra steps" % len(tool_nodes))

# ---- the guardrail, run here against the same pinned answers.
SOURCES = {h["source"] for h in d["handbook"]}
lanes, rows = {}, []
for q in d["questions"]:
    out = d["demo_answers"][q["question_id"]]
    if "SOURCE: none" in out:
        lane = "does not know"
    elif "SOURCE:" in out:
        lane = "cited"
    else:
        lane = "no source"
    if lane != q["expected"]:
        errors.append("%s should land in %r but its answer reads as %r"
                      % (q["question_id"], q["expected"], lane))
    lanes[lane] = lanes.get(lane, 0) + 1
    rows.append((q["question_id"], q["asked_by"].split()[0], lane))

    # A cited source has to be a real handbook section. A demo that quotes a
    # section that does not exist is the exact failure the demo claims to stop.
    if lane == "cited":
        line = out.rsplit("SOURCE:", 1)[1].strip()
        if not any(s in line for s in SOURCES):
            errors.append("%s cites %r, which is not a section in the handbook"
                          % (q["question_id"], line))

for lane in ("cited", "does not know", "no source"):
    if lane not in lanes:
        errors.append("no sample question reaches the %r lane" % lane)

# The no-source answer has to actually lack the line, or the demo proves nothing.
no_source = [q for q in d["questions"] if q["expected"] == "no source"]
for q in no_source:
    if "SOURCE" in d["demo_answers"][q["question_id"]]:
        errors.append("%s is meant to have no SOURCE line at all" % q["question_id"])

functional = [n for n in nodes if n["type"] != "n8n-nodes-base.stickyNote"]
print("nodes: %d functional (+%d notes) | Code nodes: %d | pinned: %d | disabled: %d"
      % (len(functional), len(nodes) - len(functional), len(code_nodes), len(pin_data),
         len([n for n in nodes if n.get("disabled")])))
print("agent tools: %d | handbook sections: %d | clients: %d"
      % (len(tool_nodes),
         len(d["handbook"]), len(d["clients"])))
for r in rows:
    print("  %-5s %-8s %s" % r)
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
