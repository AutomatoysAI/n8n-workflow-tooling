"""Writes Lead-Qualification.json.

This script is the source of truth. Edit it and re-run it:

    python build/build.py

Do not hand-edit the JSON - the next run overwrites it. If the workflow is ever
changed inside n8n and re-exported, this script and that file have diverged and
one of them has to win.

Demo-mode rules (see ../../BUILD-RULES.md): built-in n8n nodes only, no Code nodes,
fewest nodes that still tell the story, n8n's own pinned data instead of a
hand-built demo toggle, and OpenAI for the two AI steps.

What this demo is about, in two sentences. The dropdowns on the form decide how
big a job is; the message decides whether it is a job at all - and only the
second of those needs a model. Then: a lead that arrives while the CRM is down
has to end up somewhere a person will look, which is the bullet in the posting
everybody else skips.

What is and is not verified here. The extraction runs against OpenAI at
execution time, so its output is not deterministic and cannot be checked from
Python. The sample file carries what a correct read returns, and the checks
below run the deciding logic against that - so the half that decides what
happens to a lead is verified, and the half that reads the message is not.
"""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "sample-leads.json")
OUT = os.path.join(ROOT, "Lead-Qualification.json")

d = json.load(open(DATA, encoding="utf-8"))
co = d["company"]
AREA = co["service_area"]
BIG = co["big_budgets"]
SOON = co["soon_timelines"]

# The two enquiry types that are actually somebody wanting to buy something.
SELLING = ["new_project", "existing_customer"]

# What happens after each verdict. One place, so the log and the README agree.
NEXT = {
    "Hot": "Told sales, and a reply drafted for Ade to check",
    "Warm": "Acknowledgement sent, no sales ping",
    "Not a fit": "Logged only - nobody was contacted",
    "Needs a person": "Held - a person decides",
    "Spam": "Dropped before it reached the model",
}

nodes = []


def add(name, ntype, tv, params, pos, disabled=False, extra=None):
    n = {"parameters": params, "id": "f1000000-0000-4000-8000-%012d" % (len(nodes) + 1),
         "name": name, "type": ntype, "typeVersion": tv, "position": list(pos)}
    if disabled:
        n["disabled"] = True
    if extra:
        n.update(extra)
    nodes.append(n)
    return name


def sticky(content, pos, w, h, color=7):
    add("Note " + str(len([n for n in nodes if n["type"].endswith("stickyNote")]) + 1),
        "n8n-nodes-base.stickyNote", 1,
        {"content": content, "height": h, "width": w, "color": color}, pos)


def sets(assignments, include_others=False):
    return {"includeOtherFields": include_others,
            "assignments": {"assignments": [
                {"id": "a%d" % i, "name": n, "type": t, "value": v}
                for i, (n, t, v) in enumerate(assignments, 1)]},
            "options": {}}


def cond(left, right, op="equals", typ="string", cid="g1"):
    return {"id": cid, "leftValue": left, "rightValue": right,
            "operator": {"type": typ, "operation": op}}


def conds(items):
    return {"options": {"caseSensitive": True, "leftValue": "",
                        "typeValidation": "loose", "version": 2},
            "conditions": items, "combinator": "and"}


# ---------------------------------------------------------------- expressions
# Written once here so the canvas and the checks at the bottom cannot drift.
FORM = "$('Read the Form as a Lead').item.json"
SCORE = "$('Score the Lead').item.json"
OUT_ = "($json.output || {})"
TYPE = "(%s.enquiry_type || 'other')" % OUT_

JS_SELLING = "%s.includes(%s)" % (json.dumps(SELLING), TYPE)
JS_AREA = "%s.includes(%s.region)" % (json.dumps(AREA), FORM)
JS_BIG = "%s.includes(%s.budget_band)" % (json.dumps(BIG), FORM)
JS_SOON = "%s.includes(%s.timeline)" % (json.dumps(SOON), FORM)

# The whole verdict, in the order the reasons are checked.
JS_TIER = ("!(%s) ? 'Not a fit' : (!(%s) ? 'Needs a person' : ((%s && %s) ? 'Hot' : 'Warm'))"
           % (JS_SELLING, JS_AREA, JS_BIG, JS_SOON))

JS_WHY = (
    "!(%s)"
    " ? ('The message is ' + (%s === 'job_application' ? 'a job application'"
    " : (%s === 'supplier_or_pitch' ? 'somebody selling to us' : 'not an enquiry'))"
    " + ', whatever the form says.')"
    " : (!(%s)"
    " ? ('A real project worth having, but ' + %s.region + ' is outside the service area.')"
    " : ((%s && %s)"
    " ? ((%s === 'existing_customer' ? 'Existing customer, ' : 'New enquiry, ')"
    " + %s.budget_band + ', wants it ' + %s.timeline + '.')"
    " : 'A real enquiry, but no budget or date attached to it yet.'))"
    % (JS_SELLING, TYPE, TYPE, JS_AREA, FORM, JS_BIG, JS_SOON, TYPE, FORM, FORM))

JS_NEXT = "(%s)[$json.tier]" % json.dumps(NEXT)

# ------------------------------------------------------------------ sticky notes
sticky("""## What this does

Seven website enquiries off one contact form on one morning.

**Two are hot** and sales hears about them within the minute. **One is warm** and
gets an acknowledgement, not a phone call. **Two are not a fit** - one is an
agency selling to us, one is somebody after a job. **One needs a person to
decide.** **One never reaches the model at all.**

Every one of the seven ends up on a list, including the ones nothing was done
about. A lead that quietly evaporates is the failure this whole design is built
against - and the bottom of the canvas is the half that catches the ones that
evaporate for a reason nobody predicted.""",
       (-2360, -560), 440, 340, 4)

sticky("""## The dropdowns say how big. The message says whether it is real.

This is the sentence to open the interview with, because it is where most
versions of this workflow go wrong in both directions.

**Budget and timeline are dropdowns.** They do not need a model - a model that
reads "Over £50,000" correctly 97 times out of 100 misfiles three leads in every
hundred, and nobody notices for a month. So `Score the Lead` is a Set node doing
arithmetic on the form's own fields, and it is right every time.

**The free-text box does need a model, and L-03 is why.** An agency selling lead
generation ticked *Over £50,000* and *Within a month*, because that is how you
get attention. Every number on that form says drop everything. Only the words
say it is a pitch. Arithmetic alone would have put a salesperson on the phone to
a salesperson.

**So the model categorises and never scores.** It answers one question - what
kind of message is this - and hands back the words it read that from. A Set node
and a Switch decide what happens. That ordering is the design, and it is the
thing to defend when they ask.""",
       (-1890, -560), 520, 460, 3)

sticky("""## Sales is told before the CRM is written to

Look at the order on the Hot lane: **notify, draft, then write the record.**
That is deliberate and it is worth saying out loud.

If the CRM is unreachable at 4pm on a Friday, the version that writes first
never gets as far as the notification, and the best lead of the week sits in a
failed execution nobody opens until Monday. This way the rep already has it.

**In exchange the Slack message cannot carry a link to the record** - it carries
the enquiry itself, which is what the rep actually needs to make the call.""",
       (-1350, -560), 420, 300, 6)

sticky("""## Two ways a run breaks, and they are not the same failure

**One lead fails.** `Create or Update the Contact` is set to try three times, and
then to send that lead out of its **second output** instead of stopping. The
other six carry on. You still have the lead, so the log gets the name and the
email and somebody can re-run it.

**The whole run dies.** `When the Whole Run Fails` catches anything else -
including the things nobody predicted. Look at what n8n hands it: the workflow,
the node, the message, and a link. **And no trace of whose lead it was.** That is
why the log row says *open the execution* - a person gets there in thirty
seconds, which is thirty seconds better than never knowing.

**The point of both, in one line for the client:** they find out from the log,
not from the customer.

**The setup step everybody misses:** an Error Trigger does nothing until a
workflow is pointed at it. After importing, open **Settings → Error Workflow**
on this workflow and choose *this same workflow*. Skip that and the bottom half
of this canvas is decoration.""",
       (-900, -560), 500, 480, 5)

# ------------------------------------------------------------------ 1. the lead arrives
t = add("Run the Demo", "n8n-nodes-base.manualTrigger", 1, {}, (-2340, 160))

n_form = add("Website Form Submissions", "n8n-nodes-base.googleSheets", 4.5, {
    "documentId": {"__rl": True, "value": "YOUR_GOOGLE_SHEET_ID_HERE", "mode": "id"},
    "sheetName": {"__rl": True, "value": "Form Submissions", "mode": "name"},
    "options": {},
}, (-2120, 160))

# The production front door. Disabled so the demo runs from pinned data, and
# left on the canvas because it is the honest answer to "how does it get in?".
t_hook = add("Live Form Webhook", "n8n-nodes-base.webhook", 2, {
    "httpMethod": "POST",
    "path": "latchford-enquiry",
    "responseMode": "onReceived",
    "options": {},
}, (-2120, 380), disabled=True,
    extra={"webhookId": "f1000000-0000-4000-8000-0000000000aa"})

n_read = add("Read the Form as a Lead", "n8n-nodes-base.set", 3.4, sets([
    ("lead_id", "string", "={{ $json.id }}"),
    ("submitted_at", "string", "={{ $json.submitted_at }}"),
    ("source_page", "string", "={{ $json.source_page }}"),
    ("name", "string", "={{ ($json.name || '').trim() }}"),
    ("email", "string", "={{ ($json.email || '').trim().toLowerCase() }}"),
    ("phone", "string", "={{ $json.phone }}"),
    ("company", "string", "={{ $json.company }}"),
    ("region", "string", "={{ $json.region }}"),
    ("budget_band", "string", "={{ $json.budget_band }}"),
    ("timeline", "string", "={{ $json.timeline }}"),
    ("message", "string", "={{ $json.message }}"),
    # The hidden field. A person never sees it, so a person never fills it in.
    ("honeypot", "string", "={{ ($json.website || '').trim() }}"),
    ("email_looks_real", "string",
     "={{ /^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$/.test(($json.email || '').trim()) ? 'yes' : 'no' }}"),
    # Set here so a dropped submission still reaches the log with a shape the
    # log understands. Everything that gets past the gate overwrites these.
    ("enquiry_type", "string", ""),
    ("wants", "string", ""),
    ("evidence", "string", ""),
    ("tier", "string", "Spam"),
    ("why", "string",
     "={{ ($json.website || '').trim() !== ''"
     " ? 'The hidden field was filled in, so a person did not type this.'"
     " : 'The email address is not a working shape.' }}"),
]), (-1880, 160))

# ------------------------------------------------------------------ 2. the free gate
# Deliberately narrow: two facts, no guessing. A spam filter that guesses costs
# real leads, and this one costs an OpenAI call.
n_gate = add("Spam, or a Real Person?", "n8n-nodes-base.if", 2.2, {
    "conditions": conds([
        cond("={{ $json.honeypot }}", "", "equals", "string", "g1"),
        cond("={{ $json.email_looks_real }}", "yes", "equals", "string", "g2"),
    ]),
    "looseTypeValidation": True,
    "options": {},
}, (-1650, 160))

# ------------------------------------------------------------------ 3. read the message
n_model = add("OpenAI Chat Model", "@n8n/n8n-nodes-langchain.lmChatOpenAi", 1.2, {
    "model": {"__rl": True, "value": "gpt-4.1-mini", "mode": "list",
              "cachedResultName": "gpt-4.1-mini"},
    "options": {"temperature": 0, "maxTokens": 600},
}, (-1420, 420))

READ = """=Read this website enquiry and answer one question: what kind of message is it?

enquiry_type must be exactly one of:

- new_project - somebody who wants work doing and is not already a customer. Includes
  asking what something would cost or what a contract would look like.
- existing_customer - already buys from us, and this is about extending, adding a site,
  or changing what they already have.
- supplier_or_pitch - somebody selling something TO us. Agencies, software, recruiters,
  finance, SEO, lead generation. The tell is that the sender is offering, not asking.
- job_application - somebody who wants a job.
- other - anything else, including a message with nothing in it.

**Judge only the words in the message.** The budget and timeline boxes on the form are
filled in by whoever sent it, so a sales pitch can and does tick the biggest budget and
the shortest timeline. Do not let those change your answer. You are not being asked how
valuable the enquiry is - something else works that out.

wants is one plain sentence saying what the sender is after, in their terms.

evidence is the run of words from the message that made you choose that enquiry_type,
copied out of the message exactly. If you cannot find one, the type is other.

ENQUIRY from {{ $json.name }} at {{ $json.company || 'no company given' }}:
{{ $json.message }}"""

SCHEMA = json.dumps({
    "enquiry_type": "new_project",
    "wants": "A replacement quote and an install date for two failed rooftop chillers",
    "evidence": "we need a replacement quote and an install date",
}, indent=2)

n_pull = add("Read What They Are Asking For",
             "@n8n/n8n-nodes-langchain.informationExtractor", 1, {
                 "text": READ, "schemaType": "fromJson",
                 "jsonSchemaExample": SCHEMA, "options": {},
             }, (-1420, 160))

# ------------------------------------------------------------------ 4. arithmetic decides
n_score = add("Score the Lead", "n8n-nodes-base.set", 3.4, sets([
    ("lead_id", "string", "={{ %s.lead_id }}" % FORM),
    ("submitted_at", "string", "={{ %s.submitted_at }}" % FORM),
    ("source_page", "string", "={{ %s.source_page }}" % FORM),
    ("name", "string", "={{ %s.name }}" % FORM),
    ("email", "string", "={{ %s.email }}" % FORM),
    ("phone", "string", "={{ %s.phone }}" % FORM),
    ("company", "string", "={{ %s.company }}" % FORM),
    ("region", "string", "={{ %s.region }}" % FORM),
    ("budget_band", "string", "={{ %s.budget_band }}" % FORM),
    ("timeline", "string", "={{ %s.timeline }}" % FORM),
    ("message", "string", "={{ %s.message }}" % FORM),
    ("enquiry_type", "string", "={{ %s }}" % TYPE),
    ("wants", "string", "={{ %s.wants || '' }}" % OUT_),
    ("evidence", "string", "={{ %s.evidence || '' }}" % OUT_),
    ("in_service_area", "string", "={{ (%s) ? 'yes' : 'no' }}" % JS_AREA),
    ("budget_worth_chasing", "string", "={{ (%s) ? 'yes' : 'no' }}" % JS_BIG),
    ("wants_it_soon", "string", "={{ (%s) ? 'yes' : 'no' }}" % JS_SOON),
    ("tier", "string", "={{ %s }}" % JS_TIER),
    ("why", "string", "={{ %s }}" % JS_WHY),
]), (-1180, 160))

n_switch = add("Where Does It Go?", "n8n-nodes-base.switch", 3.2, {
    "rules": {"values": [
        {"conditions": conds([cond("={{ $json.tier }}", "Hot", "equals", "string", "s1")]),
         "renameOutput": True, "outputKey": "Hot - tell sales now"},
        {"conditions": conds([cond("={{ $json.tier }}", "Warm", "equals", "string", "s2")]),
         "renameOutput": True, "outputKey": "Warm - acknowledge it"},
        {"conditions": conds([cond("={{ $json.tier }}", "Not a fit", "equals", "string", "s3")]),
         "renameOutput": True, "outputKey": "Not a fit - log it only"},
    ]},
    "options": {"fallbackOutput": "extra", "renameFallbackOutput": "Needs a person"},
}, (-940, 160))

# ------------------------------------------------------------------ 5. hot lane
n_slack = add("Tell Sales Now", "n8n-nodes-base.slack", 2.3, {
    "select": "channel",
    "channelId": {"__rl": True, "value": co["sales_channel"].lstrip("#"), "mode": "name"},
    "text": "=*{{ $json.name }} at {{ $json.company }}* - {{ $json.budget_band }},"
            " {{ $json.timeline }}\n{{ $json.wants }}\n\n_{{ $json.why }}_\n"
            "{{ $json.email }} · {{ $json.phone }} · from {{ $json.source_page }}",
    "otherOptions": {},
}, (-700, 0), disabled=True)

n_write = add("Write the Reply for Ade", "@n8n/n8n-nodes-langchain.chainLlm", 1.4, {
    "promptType": "define",
    "text": "=Write the first reply to this enquiry, from %s at %s, %s.\n\n"
            "Rules:\n"
            "- Four short paragraphs at most. No greeting longer than one line.\n"
            "- Answer what they actually asked, in their own terms.\n"
            "- **Do not quote a price, a lead time, an install date or a discount.**"
            " You do not have that information and Ade does. Say he will confirm it.\n"
            "- Do not promise anything about availability or engineers.\n"
            "- Ask at most one question, and only if the enquiry cannot move without it.\n"
            "- No marketing language. Plain, quick, useful.\n\n"
            "THEIR ENQUIRY:\n{{ %s.message }}\n\n"
            "WHAT THEY WANT: {{ %s.wants }}"
            % (co["sales_rep"]["name"], co["name"], co["what_they_do"], SCORE, SCORE),
    "messages": {"messageValues": []},
}, (-460, 0))

n_draft = add("Save It as a Draft", "n8n-nodes-base.gmail", 2.1, {
    "resource": "draft",
    "subject": "=Re: your enquiry about {{ %s.wants }}" % SCORE,
    "emailType": "text",
    "message": "={{ $json.text }}",
    "options": {"sendTo": "={{ %s.email }}" % SCORE},
}, (-220, 0), disabled=True)

# ------------------------------------------------------------------ 6. warm lane
# A template, not a model. Nobody reads this one before it goes.
n_ack = add("Send the Acknowledgement", "n8n-nodes-base.gmail", 2.1, {
    "sendTo": "={{ $json.email }}",
    "subject": "=Thanks for getting in touch with %s" % co["name"],
    "emailType": "text",
    "message": "=Hi {{ $json.name.split(' ')[0] }},\n\n"
               "Thanks for your enquiry about {{ $json.source_page.replace('/', '')"
               ".replace(/-/g, ' ') }}. It has reached the right team and"
               " {{ $('Score the Lead').item.json.tier === 'Warm' ? 'someone will come"
               " back to you within two working days' : 'someone will be in touch' }}.\n\n"
               "If it is urgent in the meantime, our breakdown line is open 24 hours.\n\n"
               "%s\n%s" % (co["sales_rep"]["name"], co["name"]),
    "options": {},
}, (-700, 220), disabled=True)

# ------------------------------------------------------------------ 7. the fourth lane
n_look = add("Ask Someone to Take a Look", "n8n-nodes-base.slack", 2.3, {
    "select": "channel",
    "channelId": {"__rl": True, "value": co["sales_channel"].lstrip("#"), "mode": "name"},
    "text": "=*Worth a human decision:* {{ $json.name }} at {{ $json.company }}"
            " - {{ $json.budget_band }}, {{ $json.timeline }}\n{{ $json.wants }}\n\n"
            "_{{ $json.why }}_\nNothing has been written to the CRM and nothing has"
            " been sent. {{ $json.email }}",
    "otherOptions": {},
}, (-700, 440), disabled=True)

# ------------------------------------------------------------------ 8. the CRM write
# Last on both selling lanes, on purpose - see the note above the canvas.
# Three tries, then the lead leaves by the second output instead of stopping.
n_crm = add("Create or Update the Contact", "n8n-nodes-base.googleSheets", 4.5, {
    "operation": "appendOrUpdate",
    "documentId": {"__rl": True, "value": "YOUR_CRM_SHEET_ID_HERE", "mode": "id"},
    "sheetName": {"__rl": True, "value": "Contacts", "mode": "name"},
    "columns": {
        "mappingMode": "defineBelow",
        "matchingColumns": ["Email"],
        "value": {
            "Email": "={{ %s.email }}" % SCORE,
            "Name": "={{ %s.name }}" % SCORE,
            "Company": "={{ %s.company }}" % SCORE,
            "Phone": "={{ %s.phone }}" % SCORE,
            "Region": "={{ %s.region }}" % SCORE,
            "Lead Status": "={{ %s.tier }}" % SCORE,
            "Budget": "={{ %s.budget_band }}" % SCORE,
            "Timeline": "={{ %s.timeline }}" % SCORE,
            "Wants": "={{ %s.wants }}" % SCORE,
            "Last Enquiry": "={{ %s.submitted_at }}" % SCORE,
            "Owner": co["sales_rep"]["name"],
        },
    },
    "options": {},
}, (20, 100), disabled=True,
    extra={"retryOnFail": True, "maxTries": 3, "waitBetweenTries": 5000,
           "onError": "continueErrorOutput"})

# ------------------------------------------------------------------ 9. the decision log
n_log = add("Record the Outcome", "n8n-nodes-base.googleSheets", 4.5, {
    "operation": "append",
    "documentId": {"__rl": True, "value": "YOUR_CRM_SHEET_ID_HERE", "mode": "id"},
    "sheetName": {"__rl": True, "value": "Lead Log", "mode": "name"},
    "columns": {
        "mappingMode": "defineBelow",
        "value": {
            "Lead ID": "={{ $json.lead_id }}",
            "Received": "={{ $json.submitted_at }}",
            "Name": "={{ $json.name }}",
            "Email": "={{ $json.email }}",
            "Company": "={{ $json.company }}",
            "Region": "={{ $json.region }}",
            "Budget": "={{ $json.budget_band }}",
            "Timeline": "={{ $json.timeline }}",
            "Enquiry Type": "={{ $json.enquiry_type || 'not read' }}",
            "What They Want": "={{ $json.wants }}",
            "Verdict": "={{ $json.tier }}",
            "Why": "={{ $json.why }}",
            "What Happened Next": "={{ %s }}" % JS_NEXT,
        },
    },
    "options": {},
}, (-460, 660), disabled=True)

# ------------------------------------------------------------------ 10. failures
t_err = add("When the Whole Run Fails", "n8n-nodes-base.errorTrigger", 1, {},
            (-2340, 940))

# What n8n hands this node has the run in it and no lead. Say so in the row
# rather than leaving a blank a person has to interpret.
n_broke = add("What Broke?", "n8n-nodes-base.set", 3.4, sets([
    ("failure_kind", "string", "The whole run stopped"),
    ("workflow", "string", "={{ $json.workflow.name }}"),
    ("what_broke", "string", "={{ $json.execution.lastNodeExecuted }}"),
    ("error_message", "string", "={{ $json.execution.error.message }}"),
    ("lead", "string", "Not known from here - open the execution"),
    ("where_to_look", "string", "={{ $json.execution.url }}"),
]), (-2060, 940))

# The other half. This one still has the lead, which is the whole reason the
# second output exists.
n_which = add("Which Lead Failed?", "n8n-nodes-base.set", 3.4, sets([
    ("failure_kind", "string", "One lead failed, the rest carried on"),
    ("workflow", "string", "Lead Qualification"),
    ("what_broke", "string", "Create or Update the Contact"),
    ("error_message", "string", "={{ ($json.error || {}).message || 'no message given' }}"),
    ("lead", "string", "={{ %s.name }} <{{ %s.email }}> - {{ %s.tier }}"
     % (SCORE, SCORE, SCORE)),
    ("where_to_look", "string", "={{ $execution.id ? ('execution ' + $execution.id) : '' }}"),
]), (-1620, 1160))

n_faillog = add("Log It Where Someone Will See It", "n8n-nodes-base.googleSheets", 4.5, {
    "operation": "append",
    "documentId": {"__rl": True, "value": "YOUR_CRM_SHEET_ID_HERE", "mode": "id"},
    "sheetName": {"__rl": True, "value": "Failures", "mode": "name"},
    "columns": {
        "mappingMode": "defineBelow",
        "value": {
            "When": "={{ $now.toISO() }}",
            "Kind": "={{ $json.failure_kind }}",
            "Workflow": "={{ $json.workflow }}",
            "Node": "={{ $json.what_broke }}",
            "Error": "={{ $json.error_message }}",
            "Lead": "={{ $json.lead }}",
            "Where To Look": "={{ $json.where_to_look }}",
        },
    },
    "options": {},
}, (-1360, 940), disabled=True)

n_page = add("Page Whoever Is On", "n8n-nodes-base.slack", 2.3, {
    "select": "channel",
    "channelId": {"__rl": True, "value": co["health_channel"].lstrip("#"), "mode": "name"},
    "text": "=*{{ $json.failure_kind }}* - {{ $json.workflow }}\n"
            "Node: {{ $json.what_broke }}\n{{ $json.error_message }}\n"
            "Lead: {{ $json.lead }}\n{{ $json.where_to_look }}",
    "otherOptions": {},
}, (-1100, 940), disabled=True)

# ------------------------------------------------------------------ connections
connections = {}


def wire(src, dst, si=0, di=0, kind="main"):
    c = connections.setdefault(src, {}).setdefault(kind, [])
    while len(c) <= si:
        c.append([])
    c[si].append({"node": dst, "type": kind, "index": di})


wire(t, n_form)
wire(n_form, n_read)
wire(t_hook, n_read)                     # the production front door, same shape
wire(n_read, n_gate)
wire(n_gate, n_pull, 0)                  # a real person - worth an OpenAI call
wire(n_gate, n_log, 1)                   # a bot - recorded, and nothing else
wire(n_model, n_pull, 0, 0, "ai_languageModel")
wire(n_model, n_write, 0, 0, "ai_languageModel")
wire(n_pull, n_score)
wire(n_score, n_switch)

wire(n_switch, n_slack, 0)               # Hot
wire(n_slack, n_write)
wire(n_write, n_draft)
wire(n_draft, n_crm)

wire(n_switch, n_ack, 1)                 # Warm
wire(n_ack, n_crm)

wire(n_switch, n_look, 3)                # Needs a person - fallback output

# Every lane is recorded, straight off the Switch, so the log row is the verdict
# and not whatever the last API call happened to return.
for i in range(4):
    wire(n_switch, n_log, i)

wire(n_crm, n_which, 1)                  # the CRM node's second output: it failed
wire(n_which, n_faillog)
wire(t_err, n_broke)
wire(n_broke, n_faillog)
wire(n_faillog, n_page)

# ------------------------------------------------------------------ pinned data
FORM_KEYS = ("id", "submitted_at", "source_page", "name", "email", "phone",
             "company", "region", "budget_band", "timeline", "message", "website")
pin_data = {
    n_form: [{"json": {k: lead[k] for k in FORM_KEYS}} for lead in d["leads"]],
    t_err: [{"json": {k: d["failed_execution"][k] for k in ("execution", "workflow")}}],
}

wf = {"name": "Lead Qualification", "nodes": nodes, "connections": connections,
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

reachable = {t, t_hook, t_err}
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

# ---- the things this demo exists for, checked structurally.
# 1. A dropped submission must never reach the model. If the false branch of the
#    gate ever grows a second wire, that is the check that notices.
spam_lane = [l["node"] for l in connections[n_gate]["main"][1]]
if spam_lane != [n_log]:
    errors.append("the spam branch should reach the log and nothing else, it reaches: "
                  + ", ".join(spam_lane))

# 2. The CRM node has to retry, and then hand the lead on rather than stop.
crm = [n for n in nodes if n["name"] == n_crm][0]
if not crm.get("retryOnFail") or crm.get("maxTries", 0) < 2:
    errors.append("the CRM node does not retry")
if crm.get("onError") != "continueErrorOutput":
    errors.append("the CRM node stops the run instead of using its error output")
if len(connections.get(n_crm, {}).get("main", [])) < 2 or not connections[n_crm]["main"][1]:
    errors.append("the CRM node's error output is not wired to anything")

# 3. Every lane ends up on the decision log, including the ones nothing was done
#    about. Four Switch outputs plus the spam branch.
logged_from = {src for src, kinds in connections.items()
               for out in kinds.get("main", []) for l in out if l["node"] == n_log}
if logged_from != {n_switch, n_gate}:
    errors.append("the log is not fed by both the Switch and the gate")
if len([1 for out in connections[n_switch]["main"] if any(l["node"] == n_log for l in out)]) != 4:
    errors.append("not all four Switch outputs reach the log")

# ---- the deciding logic, in Python, against the same leads.
# The extraction cannot be checked here - it runs against OpenAI at execution
# time. What is checked is what happens to its answer.
def verdict(lead):
    hp = (lead.get("website") or "").strip()
    ok_email = bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", (lead.get("email") or "").strip()))
    if hp or not ok_email:
        return "spam", ("The hidden field was filled in, so a person did not type this."
                        if hp else "The email address is not a working shape.")
    ex = lead["expected_extraction"] or {}
    typ = ex.get("enquiry_type", "other")
    if typ not in SELLING:
        word = {"job_application": "a job application",
                "supplier_or_pitch": "somebody selling to us"}.get(typ, "not an enquiry")
        return "not a fit", "The message is %s, whatever the form says." % word
    if lead["region"] not in AREA:
        return "needs a person", ("A real project worth having, but %s is outside the "
                                  "service area." % lead["region"])
    if lead["budget_band"] in BIG and lead["timeline"] in SOON:
        head = "Existing customer, " if typ == "existing_customer" else "New enquiry, "
        return "hot", "%s%s, wants it %s." % (head, lead["budget_band"], lead["timeline"])
    return "warm", "A real enquiry, but no budget or date attached to it yet."


actual, reasons = {}, {}
for lead in d["leads"]:
    actual[lead["id"]], reasons[lead["id"]] = verdict(lead)

for lead in d["leads"]:
    if actual[lead["id"]] != lead["expected_lane"]:
        errors.append("%s should be %r but the checks put it in %r"
                      % (lead["id"], lead["expected_lane"], actual[lead["id"]]))
for lid, want in d["expected_reasons"].items():
    if reasons.get(lid) != want:
        errors.append("%s reason is %r, expected %r" % (lid, reasons.get(lid), want))

lanes = sorted(set(actual.values()))
if lanes != ["hot", "needs a person", "not a fit", "spam", "warm"]:
    errors.append("the pinned leads only exercise: " + ", ".join(lanes))

# The lead this demo argues for the model with: the form says hot, the words say
# no. If the sample ever loses it, the argument goes with it.
trap = [l for l in d["leads"]
        if l["budget_band"] in BIG and l["timeline"] in SOON
        and (l["expected_extraction"] or {}).get("enquiry_type") == "supplier_or_pitch"]
if not trap:
    errors.append("no lead left where the dropdowns say Hot and the message says pitch")

functional = [n for n in nodes if n["type"] != "n8n-nodes-base.stickyNote"]
tally = {}
for v in actual.values():
    tally[v] = tally.get(v, 0) + 1

print("nodes: %d functional (+%d notes) | Code nodes: %d | pinned: %d | disabled: %d"
      % (len(functional), len(nodes) - len(functional), len(code_nodes), len(pin_data),
         len([n for n in nodes if n.get("disabled")])))
print("leads: %d  %s" % (len(d["leads"]), tally))
for lead in d["leads"]:
    print("  %-5s %-22s %-15s %s" % (lead["id"], lead["name"][:22],
                                     actual[lead["id"]], reasons[lead["id"]]))
print("VALIDATION:", "PASS" if not errors else "FAIL")
for e in errors:
    print("  -", e)
import sys
sys.path.insert(0, os.path.dirname(ROOT))
from node_versions import unverified
for line in unverified(OUT):
    print("  unverified:", line)
print("wrote", OUT)
