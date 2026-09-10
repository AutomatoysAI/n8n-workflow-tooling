"""Writes Agency-Monthly-Report.json.

This script is the source of truth. Edit it and re-run it:

    python build/build.py

Do not hand-edit the JSON - the next run overwrites it. If the workflow is ever
changed inside n8n and re-exported, this script and that file have diverged and
one of them has to win.

Demo-mode rules (see ../../BUILD-RULES.md): built-in n8n nodes only, no Code nodes,
fewest nodes that still tell the story, n8n's own pinned data instead of a
hand-built demo toggle, and OpenAI for the one AI step.

What this demo is actually about, and what makes it different from
daily-ecom-briefing next door: an ad platform that breaks does not go missing,
it returns zeros. A month of zeros looks exactly like a terrible month, and a
reporting system that cannot tell those two things apart will email a client
"LinkedIn delivered no enquiries in August, down 100%" when the truth is that
nobody was watching the connector. So the last thing checked before anything is
written is whether a channel that spent money last month reports exactly
nothing this month - and if it does, no report is written and no client-facing
page is updated.

The second idea: two versions of every report, and only one of them uses AI.
The metrics-only version clients can open at any time is a sheet that refreshes.
It costs nothing per view and it cannot be wrong about anything the numbers do
not already say.
"""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "sample-clients.json")
OUT = os.path.join(ROOT, "Agency-Monthly-Report.json")

d = json.load(open(DATA, encoding="utf-8"))
ag = d["agency"]

nodes = []


def add(name, ntype, tv, params, pos, disabled=False):
    n = {"parameters": params, "id": "a7000000-0000-4000-8000-%012d" % (len(nodes) + 1),
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


def cond(left, op_type, op, right, cid="c1"):
    return {"conditions": {
        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose",
                    "version": 2},
        "conditions": [{"id": cid, "leftValue": left, "rightValue": right,
                        "operator": {"type": op_type, "operation": op}}],
        "combinator": "and"},
        "looseTypeValidation": True, "options": {}}


# ------------------------------------------------------------------ sticky notes
sticky("""## What this does

Runs on the 3rd of the month. Takes one client at a time, pulls that client's
SEO and paid channels together, works out every comparison **with arithmetic**,
and only then asks a model to write the commentary.

**Two clients are pinned here, and they end differently.**

Northbridge Dental has a complete month and gets a written report drafted for
the account manager to approve.

Halloran Legal does not. Its LinkedIn Ads row came back with every single figure
at zero - after spending $3,240 the month before. **Nothing is written for them
and nothing is published**, because that is a broken connector, not a bad month.

One workflow, every client. The roster sheet is the only thing that changes.""",
       (-2380, -700), 460, 380, 4)

sticky("""## The zero that is not a zero

This is the failure that makes automated reporting dangerous, and it is why the
check sits where it does.

**When an ad platform connection breaks, it does not return an error. It returns
zeros.** A revoked token, an expired refresh, a client who removed agency
access, a rename inside Business Manager - all of them come back as a clean,
well-formed month in which nothing happened.

Zero spend, zero impressions, zero conversions is indistinguishable from a
genuinely terrible month, and a model handed that row will write a fluent,
confident paragraph about a 100% decline. That paragraph goes to the client. The
client asks what happened. Nobody knows, because nobody was watching the pipe.

**So the rule is arithmetic, not judgement: a channel that spent money last
month and reports exactly nothing this month is treated as broken until a person
says otherwise.** No report. No update to the client-facing numbers. A message
to whoever owns the account.

It costs one IF node, and it is the difference between a reporting system that
runs unattended and one that only *looks* like it does.""",
       (-1880, -700), 500, 440, 3)

sticky("""## Two versions, and only one of them uses AI

The client asked for a full monthly report with written insights, plus a
metrics-only version they can look at any time during the month.

**The metrics-only version never touches a model.** It is a sheet that
refreshes - one row per channel, the same numbers the arithmetic already
agreed. It costs nothing per view, there is no draft to approve, and it cannot
say anything the figures do not already say.

**The full version is the one with the commentary**, and it is drafted for the
account manager rather than sent. A human approves anything that reaches a
client.

## Why the commentary is specific rather than generic

The model is never asked to find the trend. **Every comparison is computed
before it is handed over** - month on month, against the same month last year,
against target, cost per conversion then and now - and the channels arrive
*already sorted with the biggest mover first*.

Give a model raw figures and you get "traffic increased, which is positive."
Give it "bookings down 30.9% on flat spend, cost per booking up from $32.06 to
$45.53" and the sentence writes itself. The prompt then forbids it from
calculating anything new or naming a channel that is not in the table.

**Everything that sends or writes is greyed out.** It runs end to end and leaves
nothing behind.""",
       (-1340, -700), 520, 480, 6)

# ------------------------------------------------------------------ 1. triggers
sched = add("Monthly, on the 3rd", "n8n-nodes-base.scheduleTrigger", 1.2, {
    "rule": {"interval": [{"field": "cronExpression", "expression": "0 6 3 * *"}]},
}, (-2360, 60))

manual = add("Run the Demo", "n8n-nodes-base.manualTrigger", 1, {}, (-2360, 260))

# ------------------------------------------------------------------ 2. the roster
# The whole "reusable template across our client base" requirement lives here.
# Adding a client is a row, not a workflow change. Which channels they run, what
# a conversion is called, who approves the report - all of it is data.
n_roster = add("Client Roster", "n8n-nodes-base.googleSheets", 4.5, {
    "documentId": {"__rl": True, "value": "YOUR_ROSTER_SHEET_ID", "mode": "id"},
    "sheetName": {"__rl": True, "value": "Clients", "mode": "name"},
    "options": {},
}, (-2140, 160))

n_loop = add("One Client at a Time", "n8n-nodes-base.splitInBatches", 3, {
    "batchSize": 1, "options": {},
}, (-1920, 160))

# ------------------------------------------------------------------ 3. two sources
# Porter already pulls Google, Meta and LinkedIn into a warehouse for this
# agency. Keeping it means no Google Ads developer token, no Meta app review and
# no LinkedIn Marketing Developer Platform application - see README.
n_ads = add("Ad Channels (via Porter)", "n8n-nodes-base.googleSheets", 4.5, {
    "documentId": {"__rl": True, "value": "YOUR_PORTER_EXPORT_SHEET_ID", "mode": "id"},
    "sheetName": {"__rl": True, "value": "Monthly by channel", "mode": "name"},
    "options": {},
}, (-1700, 40))

# Search Console has no built-in n8n node, so this is a plain HTTP Request
# against its own API. Free, and not something Porter carries.
n_seo = add("SEO (Search Console)", "n8n-nodes-base.httpRequest", 4.2, {
    "url": "https://searchconsole.googleapis.com/webmasters/v3/sites/YOUR_SITE/searchAnalytics/query",
    "method": "POST",
    "authentication": "predefinedCredentialType",
    "nodeCredentialType": "googleApi",
    "sendBody": True,
    "specifyBody": "json",
    "jsonBody": ("={\n  \"startDate\": \"{{ $now.minus({ months: 1 }).startOf('month')"
                 ".toISODate() }}\",\n  \"endDate\": \"{{ $now.minus({ months: 1 })"
                 ".endOf('month').toISODate() }}\",\n  \"dimensions\": [\"date\"]\n}"),
    "options": {},
}, (-1700, 300))

n_all = add("All Channels Together", "n8n-nodes-base.merge", 3, {
    "mode": "append", "numberInputs": 2, "options": {},
}, (-1480, 160))

# The roster row drives the loop, so this is how one client's rows are picked out
# of a sheet holding every client's.
n_mine = add("Just This Client", "n8n-nodes-base.filter", 2.2, cond(
    "={{ $json.client }}", "string", "equals",
    "={{ $('One Client at a Time').first().json.client }}"), (-1260, 160))

# ------------------------------------------------------------------ 4. the arithmetic
# No AI in here, and that is deliberate. Every comparison a model might get
# wrong is computed here instead, where it gives the same answer twice. The
# model is handed conclusions, not raw figures.


def pct(now, before):
    return ("={{ $json.%s > 0 ? Math.round((($json.%s - $json.%s) / $json.%s) * 1000) / 10"
            " : 0 }}" % (before, now, before, before))


CPA = "($json.spend > 0 && $json.conversions > 0 ? $json.spend / $json.conversions : 0)"
CPA_P = ("($json.spend_prev > 0 && $json.conversions_prev > 0 ?"
         " $json.spend_prev / $json.conversions_prev : 0)")

n_calc = add("Work Out the Comparisons", "n8n-nodes-base.set", 3.4, sets([
    ("conversions_mom_pct", "number", pct("conversions", "conversions_prev")),
    ("conversions_yoy_pct", "number", pct("conversions", "conversions_last_year")),
    ("spend_mom_pct", "number", pct("spend", "spend_prev")),
    ("vs_target_pct", "number", pct("conversions", "target_conversions")),
    ("cpa", "number", "={{ Math.round((" + CPA + ") * 100) / 100 }}"),
    ("cpa_prev", "number", "={{ Math.round((" + CPA_P + ") * 100) / 100 }}"),
    ("cpa_change_pct", "number",
     "={{ (" + CPA_P + ") > 0 ? Math.round((((" + CPA + ") - (" + CPA_P + ")) / ("
     + CPA_P + ")) * 1000) / 10 : 0 }}"),
    ("ctr", "number",
     "={{ $json.impressions > 0 ? Math.round(($json.clicks / $json.impressions) * 10000)"
     " / 100 : 0 }}"),
    ("ctr_prev", "number",
     "={{ $json.impressions_prev > 0 ? Math.round(($json.clicks_prev /"
     " $json.impressions_prev) * 10000) / 100 : 0 }}"),
    # The one that decides whether a person gets involved. Spent money last
    # month, reports nothing at all this month - that is a pipe, not a market.
    ("looks_broken", "boolean",
     "={{ $json.spend_prev > 0 && $json.spend == 0 && $json.impressions == 0 }}"),
    # Sorted on next, so the model always opens with whatever moved most.
    ("movement", "number",
     "={{ Math.abs($json.conversions_prev > 0 ? Math.round((($json.conversions -"
     " $json.conversions_prev) / $json.conversions_prev) * 1000) / 10 : 0) }}"),
]), (-1040, 160))

n_sort = add("Biggest Movers First", "n8n-nodes-base.sort", 1, {
    "sortFieldsUi": {"sortField": [{"fieldName": "movement", "order": "descending"}]},
    "options": {},
}, (-820, 160))

n_bundle = add("Bundle Into One Report", "n8n-nodes-base.aggregate", 1, {
    "aggregate": "aggregateAllItemData", "destinationFieldName": "channels", "options": {},
}, (-600, 160))

# ------------------------------------------------------------------ 5. the table
R = "$('One Client at a Time').first().json."
CH = "$json.channels"

# Built with plain string concatenation rather than a JavaScript template
# literal, so nothing inside it can be mistaken for n8n's own {{ }} delimiters.
TABLE = ("={{ " + CH + ".map(c => c.channel"
         " + '  |  spend ' + c.spend + ' (last month ' + c.spend_prev"
         " + ', ' + c.spend_mom_pct + '%)'"
         " + '  |  ' + " + R + "conversion_name + 's ' + c.conversions"
         " + ' (last month ' + c.conversions_prev + ', ' + c.conversions_mom_pct + '%)'"
         " + '  |  vs target ' + c.vs_target_pct + '%'"
         " + '  |  same month last year ' + c.conversions_last_year"
         " + ' (' + c.conversions_yoy_pct + '%)'"
         " + '  |  cost per ' + " + R + "conversion_name + ' ' + c.cpa"
         " + ' (was ' + c.cpa_prev + ', ' + c.cpa_change_pct + '%)'"
         " + '  |  click-through ' + c.ctr + '% (was ' + c.ctr_prev + '%)'"
         ").join('\\n') }}")

n_table = add("Build the Numbers Table", "n8n-nodes-base.set", 3.4, sets([
    ("client", "string", "={{ " + R + "client }}"),
    ("client_name", "string", "={{ " + R + "client_name }}"),
    ("goal", "string", "={{ " + R + "goal }}"),
    ("conversion_name", "string", "={{ " + R + "conversion_name }}"),
    ("reader", "string", "={{ " + R + "reader }}"),
    ("currency", "string", "={{ " + R + "currency }}"),
    ("channels_not_run", "string", "={{ " + R + "channels_not_run }}"),
    ("manager_email", "string", "={{ " + R + "manager_email }}"),
    ("account_manager", "string", "={{ " + R + "account_manager }}"),
    ("month_label", "string", ag["month_label"]),
    ("numbers_table", "string", TABLE),
    ("broken_channels", "string",
     "={{ " + CH + ".filter(c => c.looks_broken).map(c => c.channel).join(', ') }}"),
], include_others=False), (-380, 160))

n_check = add("Every Channel Actually Reported?", "n8n-nodes-base.if", 2.2, cond(
    "={{ $json.broken_channels }}", "string", "empty", ""), (-160, 160))

# ------------------------------------------------------------------ 6. version one: no AI
# The version clients open during the month. Numbers only. Nothing here has been
# near a model, so there is nothing to check and nothing to approve.
n_split = add("Back to One Row per Channel", "n8n-nodes-base.splitOut", 1, {
    "fieldToSplitOut": "channels", "options": {},
}, (60, -60))

n_metrics = add("Metrics-Only Report (No AI)", "n8n-nodes-base.googleSheets", 4.5, {
    "operation": "appendOrUpdate",
    "documentId": {"__rl": True, "value": "YOUR_CLIENT_DASHBOARD_SHEET_ID", "mode": "id"},
    "sheetName": {"__rl": True, "value": "Live metrics", "mode": "name"},
    "columns": {"mappingMode": "defineBelow",
                "matchingColumns": ["Client", "Month", "Channel"],
                "value": {
                    "Client": "={{ $('Build the Numbers Table').first().json.client_name }}",
                    "Month": ag["month_label"],
                    "Channel": "={{ $json.channel }}",
                    "Spend": "={{ $json.spend }}",
                    "Impressions": "={{ $json.impressions }}",
                    "Clicks": "={{ $json.clicks }}",
                    "Click-through %": "={{ $json.ctr }}",
                    "Conversions": "={{ $json.conversions }}",
                    "vs last month %": "={{ $json.conversions_mom_pct }}",
                    "vs last year %": "={{ $json.conversions_yoy_pct }}",
                    "vs target %": "={{ $json.vs_target_pct }}",
                    "Cost per conversion": "={{ $json.cpa }}",
                }},
    "options": {},
}, (280, -60), disabled=True)

# ------------------------------------------------------------------ 7. version two
n_model = add("OpenAI Chat Model", "@n8n/n8n-nodes-langchain.lmChatOpenAi", 1.2, {
    "model": {"__rl": True, "value": "gpt-4.1-mini", "mode": "list",
              "cachedResultName": "gpt-4.1-mini"},
    "options": {"temperature": 0.3, "maxTokens": 900},
}, (60, 520))

PROMPT = ("=You write the monthly performance commentary for {{ $json.client_name }}, a"
          " client of " + ag["name"] + """.

What they are paying for: {{ $json.goal }}. One conversion here is one {{ $json.conversion_name }}.
Reporting month: {{ $json.month_label }}. All money is in {{ $json.currency }}.
Who reads this: their {{ $json.reader }}.

THE NUMBERS - already checked, already compared, and sorted with the biggest change first:

{{ $json.numbers_table }}

Write four short paragraphs, no headings:

1. What happened. Open with the channel at the top of the table - it moved most, so it is
   the story. Say what changed and by how much, quoting the figure.
2. The number that needs attention. Name the single worst one and say what it costs them in
   ordinary terms. A rising cost per {{ $json.conversion_name }} means they are paying more
   money for the same result.
3. What is working. The best number, quoted the same way.
4. What we are doing about it. One or two concrete next steps that follow from the numbers
   above, not general advice.

Rules. These matter more than the writing:
- Every number you write must already appear in the table above. Do not calculate anything
  new, do not add channels together, do not convert currencies, do not round differently.
- Only write about the channels in the table. If a channel is not listed, this client does
  not run it, and mentioning it is an error.
- No industry benchmarks, no averages, no "typical for the sector". You have not been given
  any and you cannot know them.
- Where the numbers do not tell you why something moved, say what to check instead of
  guessing. "Click-through fell while impressions rose, which usually points at creative
  fatigue - worth checking when those ad sets last had new images" is useful. "This is
  likely seasonal" is not.
- Plain English. The reader runs a business, not a marketing team. Any term that is not
  ordinary English gets explained in the same sentence.
- No greeting, no sign-off, no bullet points, no exclamation marks.

Return the commentary only.""")

n_write = add("Write the Insights", "@n8n/n8n-nodes-langchain.chainLlm", 1.4, {
    "promptType": "define", "text": PROMPT, "messages": {"messageValues": []},
}, (60, 280))

# Cheap catch for the commonest hallucination in agency reporting: a model told
# it is writing for a marketing agency helpfully writes a LinkedIn paragraph for
# a client who has never run LinkedIn.
T = "$('Build the Numbers Table').first().json."
n_scope = add("Only the Channels We Gave It?", "n8n-nodes-base.if", 2.2, cond(
    "={{ " + T + "channels_not_run.split(', ').filter(c => c.length > 0 &&"
    " $json.text.includes(c)).length }}",
    "number", "equals", 0), (280, 280))

# ------------------------------------------------------------------ 8. a person decides
n_draft = add("Full Report - Draft for Approval", "n8n-nodes-base.gmail", 2.1, {
    "resource": "draft",
    "subject": "={{ " + T + "client_name }} - " + ag["month_label"] + " report",
    "emailType": "text",
    "message": "={{ $json.text }}\n\n---\n\n{{ " + T + "numbers_table }}",
    "options": {"sendTo": "={{ " + T + "manager_email }}"},
}, (500, 280), disabled=True)

# One destination for both ways this can stop: a channel that did not report,
# and a draft that wrote about something it was never given.
n_hold = add("Held for a Person", "n8n-nodes-base.slack", 2.3, {
    "select": "channel",
    "channelId": {"__rl": True, "value": ag["review_channel"], "mode": "name"},
    "text": ("=*No " + ag["month_label"] + " report for {{ " + T + "client_name }}*\n"
             "{{ " + T + "broken_channels ? ('*' + " + T + "broken_channels + '* spent "
             "money last month and reported nothing at all this month - zero spend, zero "
             "impressions. That is a broken connection until someone confirms otherwise, "
             "so no commentary was written and the client-facing numbers were not "
             "updated.') : ('The draft mentioned a channel this client does not run. Held "
             "rather than sent.') }}\n"
             "Usual causes: a revoked token, an expired refresh, or agency access removed "
             "inside the ad account.\n"
             "{{ " + T + "account_manager }} - nothing has gone to the client."),
    "otherOptions": {},
}, (500, 560), disabled=True)

# Written for every outcome, so the months that did not report are as visible as
# the ones that did. A client that shows up here twice has a pipe problem.
n_log = add("Log Every Report", "n8n-nodes-base.googleSheets", 4.5, {
    "operation": "append",
    "documentId": {"__rl": True, "value": "YOUR_ROSTER_SHEET_ID", "mode": "id"},
    "sheetName": {"__rl": True, "value": "Report log", "mode": "name"},
    "columns": {"mappingMode": "defineBelow", "value": {
        "Month": ag["month_label"],
        "Client": "={{ " + T + "client_name }}",
        "Outcome": "={{ " + T + "broken_channels ? 'Held - channel reported nothing' :"
                   " 'Drafted for approval' }}",
        "Channels not reporting": "={{ " + T + "broken_channels }}",
        "Approver": "={{ " + T + "account_manager }}",
    }},
    "options": {},
}, (720, 420), disabled=True)

# ------------------------------------------------------------------ connections
connections = {}


def wire(src, dst, si=0, di=0, kind="main"):
    c = connections.setdefault(src, {}).setdefault(kind, [])
    while len(c) <= si:
        c.append([])
    c[si].append({"node": dst, "type": kind, "index": di})


for trig in (sched, manual):
    wire(trig, n_roster)
wire(n_roster, n_loop)
wire(n_loop, n_ads, 1)              # output 1 is the loop; output 0 is "done"
wire(n_loop, n_seo, 1)
wire(n_ads, n_all, 0, 0)
wire(n_seo, n_all, 0, 1)
wire(n_all, n_mine)
wire(n_mine, n_calc)
wire(n_calc, n_sort)
wire(n_sort, n_bundle)
wire(n_bundle, n_table)
wire(n_table, n_check)
wire(n_check, n_split, 0)           # complete month - publish the numbers
wire(n_check, n_write, 0)           # and write the commentary
wire(n_check, n_hold, 1)            # a channel reported nothing - nobody sees anything
wire(n_split, n_metrics)
wire(n_model, n_write, 0, 0, "ai_languageModel")
wire(n_write, n_scope)
wire(n_scope, n_draft, 0)
wire(n_scope, n_hold, 1)            # wrote about a channel it was not given
wire(n_draft, n_log)
wire(n_hold, n_log)
wire(n_log, n_loop)                 # next client

# ------------------------------------------------------------------ pinned data
pin_data = {
    n_roster: [{"json": c} for c in d["roster"]],
    n_ads: [{"json": r} for r in d["ad_channels"]],
    n_seo: [{"json": r} for r in d["seo"]],
}

wf = {"name": "Agency Monthly Report", "nodes": nodes, "connections": connections,
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

# ------------------------------------- the pinned data has to reach both endings
rows = d["ad_channels"] + d["seo"]
outcome = {}
for c in d["roster"]:
    mine = [r for r in rows if r["client"] == c["client"]]
    if not mine:
        errors.append("no channel rows pinned for " + c["client"])
        continue
    broken = [r["channel"] for r in mine
              if r["spend_prev"] > 0 and r["spend"] == 0 and r["impressions"] == 0]
    outcome[c["client_name"]] = ("held - " + ", ".join(broken)) if broken else "report"
    for r in mine:
        if r["channel"] in c["channels_not_run"].split(", "):
            errors.append("%s has a row for %s, which the roster says they do not run"
                          % (c["client"], r["channel"]))
lanes = sorted({o.split(" - ")[0] for o in outcome.values()})
if lanes != ["held", "report"]:
    errors.append("the pinned data only exercises: " + ", ".join(lanes))

functional = [n for n in nodes if n["type"] != "n8n-nodes-base.stickyNote"]
print("nodes: %d functional (+%d notes) | Code nodes: %d | pinned: %d | disabled: %d"
      % (len(functional), len(nodes) - len(functional), len(code_nodes), len(pin_data),
         len([n for n in nodes if n.get("disabled")])))
for name in sorted(outcome):
    print("  %-20s %s" % (name, outcome[name]))
print("VALIDATION:", "PASS" if not errors else "FAIL")
for e in errors:
    print("  -", e)

import sys
sys.path.insert(0, os.path.dirname(ROOT))
from node_versions import unverified
for line in unverified(OUT):
    print("  unverified:", line)
print("wrote", OUT)
