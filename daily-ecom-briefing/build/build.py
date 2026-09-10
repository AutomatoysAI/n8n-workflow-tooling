"""Writes Daily-Ecom-Briefing.json.

This script is the source of truth. Edit it and re-run it:

    python build/build.py

Do not hand-edit the JSON - the next run overwrites it. If the workflow is ever
changed inside n8n and re-exported, this script and that file have diverged and
one of them has to win.

Demo-mode rules (see ../../BUILD-RULES.md): built-in n8n nodes only, no Code nodes,
fewest nodes that still tell the story, n8n's own pinned data instead of a
hand-built demo toggle, and OpenAI for the one AI step.

What this demo is actually about: three systems will never agree on yesterday's
revenue, and the job is deciding which one is the truth and explaining the rest.
The reconciliation is arithmetic and stays arithmetic - the AI only ever writes
about numbers that have already been agreed.
"""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "sample-days.json")
OUT = os.path.join(ROOT, "Daily-Ecom-Briefing.json")

d = json.load(open(DATA, encoding="utf-8"))
co = d["company"]
TOL = co["tolerance_pct"]

nodes = []


def add(name, ntype, tv, params, pos, disabled=False):
    n = {"parameters": params, "id": "c4000000-0000-4000-8000-%012d" % (len(nodes) + 1),
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


def merge_on(field):
    return {"mode": "combine", "combineBy": "combineByFields",
            "fieldsToMatchString": field, "joinMode": "enrichInput1", "options": {}}


# ------------------------------------------------------------------ sticky notes
sticky("""## What this does

Runs at 7am. Pulls yesterday from **three systems that do not agree with each
other**, works out which number is the truth, and writes the CEO a short note in
plain English.

Two days are pinned here. **One reconciles and sends. One does not, and is held
for a person instead** - because a briefing built on numbers nobody has checked
is worse than no briefing.

No dashboard. The CEO does not want to log into anything at 7am; they want to
know whether yesterday was fine.""",
       (-1900, -560), 440, 320, 4)

sticky("""## Shopify and the books will never match

This is the part every dashboard project gets wrong, and it is the whole reason
this workflow exists.

Shopify says **$15,405**. QuickBooks says **$15,155**. Both are right.

The $250 difference is a **gift card**. Redeeming a gift card is not new
revenue - the money was already booked on the day the card was *sold*. Counting
it again would be counting it twice. So the two systems disagree, and the
disagreement is **correct**.

Refunds, tax, shipping, discounts and the timezone the day is cut on all do the
same thing. A CEO dashboard that shows three numbers for "sales yesterday" is
dead inside a week, and no amount of AI on top of it fixes that.

**So the system picks a number of record - the books - explains every dollar of
the difference, and refuses to publish anything it cannot explain.**

The second day is that refusal: a $1,560 gap with nothing to account for it.
It does not guess, and it does not quietly average. It asks Finance.""",
       (-1430, -560), 520, 460, 3)

sticky("""## Two things worth saying on the call

**Meta's revenue number is a claim, not an accounting fact.** The platform is
marking its own homework - it counts a sale as its own if the buyer saw an ad
within the attribution window, and Klaviyo will claim the same sale on the same
day. Add every channel's attributed revenue together and you get more revenue
than the business actually made. So ROAS here is **blended**: real money in,
divided by real money out. Meta's figure is shown, and labelled as Meta's.

**Everything that sends is greyed out** - the CEO email, the Finance alert, and
the history log. It runs end to end and leaves nothing behind.

**The AI never sees an unreconciled number.** It writes about figures that have
already been agreed by the arithmetic upstream. That ordering is the design.""",
       (-890, -560), 460, 400, 6)

# ------------------------------------------------------------------ 1. triggers
sched = add("Every Morning at 7am", "n8n-nodes-base.scheduleTrigger", 1.2, {
    "rule": {"interval": [{"field": "cronExpression", "expression": "0 7 * * *"}]},
}, (-1880, 60))

manual = add("Run the Demo", "n8n-nodes-base.manualTrigger", 1, {}, (-1880, 260))

# ------------------------------------------------------------------ 2. three systems
n_shop = add("Shopify Orders", "n8n-nodes-base.shopify", 1, {
    "resource": "order", "operation": "getAll", "returnAll": True,
    "options": {"createdAtMin": "={{ $now.minus({ days: 1 }).toISODate() }}"},
}, (-1660, -100))

# QuickBooks' own node cannot fetch a Profit and Loss report, so this is a plain
# HTTP Request against the reports endpoint. Built-in node either way.
n_books = add("Booked Revenue (QuickBooks)", "n8n-nodes-base.httpRequest", 4.2, {
    "url": "https://quickbooks.api.intuit.com/v3/company/YOUR_REALM_ID/reports/ProfitAndLoss",
    "authentication": "predefinedCredentialType",
    "nodeCredentialType": "quickBooksOAuth2Api",
    "sendQuery": True,
    "queryParameters": {"parameters": [
        {"name": "start_date", "value": "={{ $now.minus({ days: 1 }).toISODate() }}"},
        {"name": "end_date", "value": "={{ $now.minus({ days: 1 }).toISODate() }}"},
    ]},
    "options": {},
}, (-1660, 140))

n_meta = add("Meta Ads Spend", "n8n-nodes-base.facebookGraphApi", 1, {
    "hostUrl": "graph.facebook.com",
    "httpRequestMethod": "GET",
    "graphApiVersion": "v21.0",
    "node": "act_YOUR_AD_ACCOUNT_ID",
    "edge": "insights",
    "options": {},
}, (-1660, 380))

# ------------------------------------------------------------------ 3. totals
# Summarize, not a Code node. Group by day, add up the columns that matter.
n_sum = add("Total Up Shopify", "n8n-nodes-base.summarize", 1.1, {
    "fieldsToSummarize": {"values": [
        {"aggregation": "sum", "field": "total_price"},
        {"aggregation": "sum", "field": "refund_amount"},
        {"aggregation": "sum", "field": "tax"},
        {"aggregation": "sum", "field": "shipping"},
        {"aggregation": "sum", "field": "gift_card"},
        {"aggregation": "count", "field": "order_number"},
    ]},
    "fieldsToSplitBy": "date",
    "options": {},
}, (-1420, -100))

n_m1 = add("Match the Books to Shopify", "n8n-nodes-base.merge", 3, merge_on("date"),
           (-1200, 0))
n_m2 = add("Add the Ad Spend", "n8n-nodes-base.merge", 3, merge_on("date"), (-980, 140))

# ------------------------------------------------------------------ 4. the arithmetic
S_NET = ("($json.sum_total_price - $json.sum_refund_amount - $json.sum_tax"
         " - $json.sum_shipping)")
GAP = "(%s - $json.booked_net_revenue)" % S_NET
UNEX = "Math.abs(%s - $json.sum_gift_card)" % GAP
PCT = "(Math.round((%s / %s) * 1000) / 10)" % (UNEX, S_NET)


def money(expr):
    return "={{ Math.round((%s) * 100) / 100 }}" % expr


# No AI in here. Which number is the truth is arithmetic, and arithmetic has to
# give the same answer twice. The AI writes the note, and only ever about
# figures this node has already agreed.
n_rec = add("Reconcile the Numbers", "n8n-nodes-base.set", 3.4, sets([
    ("orders", "number", "={{ $json.count_order_number }}"),
    ("gross_sales", "number", money("$json.sum_total_price")),
    ("refunds", "number", money("$json.sum_refund_amount")),
    ("shopify_net", "number", money(S_NET)),
    ("books_net", "number", money("$json.booked_net_revenue")),
    ("gap", "number", money(GAP)),
    ("explained_by_gift_cards", "number", money("$json.sum_gift_card")),
    ("unexplained", "number", money(UNEX)),
    ("unexplained_pct", "number", "={{ %s }}" % PCT),
    # The books win. Shopify is a shop, not a ledger - it does not know about a
    # gift card sold in June, and it is not what the accountant files.
    ("number_of_record", "number", money("$json.booked_net_revenue")),
    ("aov", "number", money("$json.booked_net_revenue / $json.count_order_number")),
    ("ad_spend", "number", money("$json.spend")),
    ("blended_roas", "number", money("$json.booked_net_revenue / $json.spend")),
    ("meta_claimed_revenue", "number", money("$json.attributed_revenue")),
    ("meta_claim_pct", "number",
     "={{ Math.round(($json.attributed_revenue / $json.booked_net_revenue) * 1000) / 10 }}"),
    ("reconciliation_note", "string",
     "={{ %s === 0 ? ('Shopify and the books differ by $' + %s + ', which is exactly the "
     "gift cards redeemed. A redeemed gift card is not new revenue - it was booked when the "
     "card was sold.') : ('Shopify and the books differ by $' + %s + '. Gift cards account "
     "for $' + $json.sum_gift_card + '. $' + %s + ' is unaccounted for.') }}"
     % (UNEX, GAP, GAP, UNEX)),
]), (-760, 140))

n_if = add("Do the Numbers Agree?", "n8n-nodes-base.if", 2.2, {
    "conditions": {
        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose",
                    "version": 2},
        "conditions": [{"id": "g1", "leftValue": "={{ $json.unexplained_pct }}",
                        "rightValue": TOL,
                        "operator": {"type": "number", "operation": "lte"}}],
        "combinator": "and",
    },
    "looseTypeValidation": True, "options": {},
}, (-520, 140))

# ------------------------------------------------------------------ 5. the briefing
n_model = add("OpenAI Chat Model", "@n8n/n8n-nodes-langchain.lmChatOpenAi", 1.2, {
    "model": {"__rl": True, "value": "gpt-4.1-mini", "mode": "list",
              "cachedResultName": "gpt-4.1-mini"},
    "options": {"temperature": 0.2, "maxTokens": 500},
}, (-280, 280))

BRIEF = """=Write %s, the CEO of %s, a short morning note about yesterday's trading.

DATE: {{ $json.date }}
REVENUE (the number of record, from the books): ${{ $json.number_of_record }}
ORDERS: {{ $json.orders }}
AVERAGE ORDER VALUE: ${{ $json.aov }}
GROSS SALES IN SHOPIFY: ${{ $json.gross_sales }}
REFUNDS: ${{ $json.refunds }}
RECONCILIATION: {{ $json.reconciliation_note }}
AD SPEND (Meta): ${{ $json.ad_spend }}
BLENDED ROAS (revenue of record / ad spend): {{ $json.blended_roas }}
META SAYS IT DROVE: ${{ $json.meta_claimed_revenue }} ({{ $json.meta_claim_pct }}%% of revenue)

Rules:
- **Revenue is the number of record and nothing else.** Never quote the Shopify gross as
  revenue, and never add Meta's attributed figure to anything.
- **Meta's number is a claim, not an accounting fact.** If you mention it, say whose claim
  it is. The platform counts a sale as its own if the buyer saw an ad within its window,
  and other channels claim the same sales, so these figures overlap and cannot be summed.
- Mention the reconciliation in one sentence, in plain words. Renata is not an accountant
  and should not have to be.
- **Never state a fact that is not listed above.** No comparison to last week, last month
  or target - you have not been given them, and an invented trend is worse than no trend.
- No recommendations. This is a status note, not advice.
- Four sentences or fewer. No greeting, no sign-off, no bullet points, no exclamation
  marks. Plain sentences a person reads standing up.

Return the note only.""" % (co["ceo"], co["name"])

n_brief = add("Write the Briefing", "@n8n/n8n-nodes-langchain.chainLlm", 1.4, {
    "promptType": "define", "text": BRIEF, "messages": {"messageValues": []},
}, (-280, 40))

R = "Reconcile the Numbers"


def r(field):
    return "$('" + R + "').item.json." + field


n_mail = add("Email the CEO", "n8n-nodes-base.gmail", 2.1, {
    "sendTo": co["ceo_email"],
    "subject": "={{ 'Yesterday: $' + " + r("number_of_record") + " + ' across ' + "
               + r("orders") + " + ' orders' }}",
    "message": "={{ $json.text }}",
    "options": {},
}, (-40, 40), disabled=True)

# The gap day never reaches the CEO. It reaches the person who can explain it.
n_hold = add("Hold It and Ask Finance", "n8n-nodes-base.slack", 2.3, {
    "select": "channel",
    "channelId": {"__rl": True, "value": co["finance_channel"], "mode": "name"},
    "text": ("=*No briefing sent for {{ $json.date }}* - the numbers do not reconcile.\n"
             "Shopify nets *${{ $json.shopify_net }}*, the books say "
             "*${{ $json.books_net }}*.\n"
             "Gift cards explain ${{ $json.explained_by_gift_cards }}. "
             "*${{ $json.unexplained }} ({{ $json.unexplained_pct }}%) is unaccounted "
             "for*, against a " + str(TOL) + "% tolerance.\n"
             "{{ $json.orders }} orders. Usual suspects: a channel that has not settled, "
             "a failed sync, or a day cut on a different timezone.\n"
             "<@" + co["finance_owner"] + "> - nothing has gone to Renata."),
    "otherOptions": {},
}, (-40, 320), disabled=True)

# Written for both lanes, so the history shows the days that failed to reconcile
# as well as the ones that sent. A gap that shows up every Monday is a pattern.
n_log = add("Log the Day", "n8n-nodes-base.googleSheets", 4.5, {
    "operation": "append",
    "documentId": {"__rl": True, "value": "YOUR_GOOGLE_SHEET_ID_HERE", "mode": "id"},
    "sheetName": {"__rl": True, "value": "Daily", "mode": "name"},
    "columns": {"mappingMode": "defineBelow", "value": {
        "Date": "={{ " + r("date") + " }}",
        "Revenue (books)": "={{ " + r("number_of_record") + " }}",
        "Shopify net": "={{ " + r("shopify_net") + " }}",
        "Unexplained": "={{ " + r("unexplained") + " }}",
        "Orders": "={{ " + r("orders") + " }}",
        "AOV": "={{ " + r("aov") + " }}",
        "Ad spend": "={{ " + r("ad_spend") + " }}",
        "Blended ROAS": "={{ " + r("blended_roas") + " }}",
        "Sent": "={{ " + r("unexplained_pct") + " <= %s ? 'Yes' : 'Held' }}" % TOL,
    }},
    "options": {},
}, (200, 140), disabled=True)

# ------------------------------------------------------------------ connections
connections = {}


def wire(src, dst, si=0, di=0, kind="main"):
    c = connections.setdefault(src, {}).setdefault(kind, [])
    while len(c) <= si:
        c.append([])
    c[si].append({"node": dst, "type": kind, "index": di})


for trig in (sched, manual):
    wire(trig, n_shop)
    wire(trig, n_books)
    wire(trig, n_meta)
wire(n_shop, n_sum)
wire(n_sum, n_m1, 0, 0)
wire(n_books, n_m1, 0, 1)
wire(n_m1, n_m2, 0, 0)
wire(n_meta, n_m2, 0, 1)
wire(n_m2, n_rec)
wire(n_rec, n_if)
wire(n_if, n_brief, 0)              # reconciled - write it
wire(n_if, n_hold, 1)               # did not reconcile - ask a person
wire(n_model, n_brief, 0, 0, "ai_languageModel")
wire(n_brief, n_mail)
wire(n_mail, n_log)
wire(n_hold, n_log)                 # both lanes are logged

# ------------------------------------------------------------------ pinned data
pin_data = {
    n_shop: [{"json": o} for o in d["shopify_orders"]],
    n_books: [{"json": b} for b in d["books"]],
    n_meta: [{"json": m} for m in d["meta_ads"]],
}

wf = {"name": "Daily Ecom Briefing", "nodes": nodes, "connections": connections,
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

blob = json.dumps(wf).lower()
for banned in ("anthropic", "claude"):
    if banned in blob:
        errors.append("provider leak: '%s' appears in the workflow" % banned)

code_nodes = [n for n in nodes if n["type"] == "n8n-nodes-base.code"]
if code_nodes:
    errors.append("Code nodes present: " + ", ".join(n["name"] for n in code_nodes))

# The rule this demo exists to demonstrate: the number of record comes from the
# books, never from an ad platform's attribution. Checked, not trusted.
rec = [n for n in nodes if n["name"] == n_rec][0]
for asn in rec["parameters"]["assignments"]["assignments"]:
    if asn["name"] == "number_of_record" and "attributed_revenue" in asn["value"]:
        errors.append("number_of_record is derived from ad-platform attribution")

# ---- the same arithmetic, in Python, against the same pinned data.
books = {b["date"]: b for b in d["books"]}
ads = {m["date"]: m for m in d["meta_ads"]}
days = {}
for o in d["shopify_orders"]:
    t = days.setdefault(o["date"], dict(gross=0.0, refunds=0.0, tax=0.0, ship=0.0,
                                        gift=0.0, orders=0))
    t["gross"] += o["total_price"]
    t["refunds"] += o["refund_amount"]
    t["tax"] += o["tax"]
    t["ship"] += o["shipping"]
    t["gift"] += o["gift_card"]
    t["orders"] += 1


def r2(x):
    return round(x + 1e-9, 2)


actual = {}
for day, t in days.items():
    s_net = r2(t["gross"] - t["refunds"] - t["tax"] - t["ship"])
    b_net = books[day]["booked_net_revenue"]
    gap = r2(s_net - b_net)
    unex = r2(abs(gap - t["gift"]))
    pct = round(unex / s_net * 1000) / 10
    actual[day] = {
        "lane": "send" if pct <= TOL else "hold",
        "shopify_net": s_net, "books_net": b_net, "gap": gap,
        "explained_by_gift_cards": r2(t["gift"]), "unexplained": unex,
        "unexplained_pct": pct, "number_of_record": b_net, "orders": t["orders"],
        "blended_roas": r2(b_net / ads[day]["spend"]),
    }

for day, want in d["expected"].items():
    got = actual.get(day)
    if got is None:
        errors.append("no orders pinned for %s" % day)
        continue
    for k, v in want.items():
        if got[k] != v:
            errors.append("%s %s is %r, expected %r" % (day, k, got[k], v))
if set(actual) != set(d["expected"]):
    errors.append("expected block does not cover every day")

# Both lanes must actually be exercised, or the demo only tells half the story.
lanes = sorted({v["lane"] for v in actual.values()})
if lanes != ["hold", "send"]:
    errors.append("the pinned data only exercises: " + ", ".join(lanes))

functional = [n for n in nodes if n["type"] != "n8n-nodes-base.stickyNote"]
print("nodes: %d functional (+%d notes) | Code nodes: %d | pinned: %d | disabled: %d"
      % (len(functional), len(nodes) - len(functional), len(code_nodes), len(pin_data),
         len([n for n in nodes if n.get("disabled")])))
for day in sorted(actual):
    a = actual[day]
    print("  %s  %-4s  shopify %.2f  books %.2f  gap %.2f  unexplained %.2f (%.1f%%)"
          % (day, a["lane"], a["shopify_net"], a["books_net"], a["gap"],
             a["unexplained"], a["unexplained_pct"]))
print("VALIDATION:", "PASS" if not errors else "FAIL")
for e in errors:
    print("  -", e)
import sys
sys.path.insert(0, os.path.dirname(ROOT))
from node_versions import unverified
for line in unverified(OUT):
    print("  unverified:", line)
print("wrote", OUT)
