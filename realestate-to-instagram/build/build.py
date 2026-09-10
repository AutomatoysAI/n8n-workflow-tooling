"""Writes Real-Estate-to-Instagram.json.

This script is the source of truth. Edit it and re-run it:

    python build/build.py

Do not hand-edit the JSON - the next run overwrites it. If the workflow is ever
changed inside n8n and re-exported, this script and that file have diverged and
one of them has to win.

Demo-mode rules (see ../../BUILD-RULES.md): built-in n8n nodes only, no Code nodes,
fewest nodes that still tell the story, n8n's own pinned data instead of a
hand-built demo toggle, and OpenAI for the one AI step.

The thing this demo is actually about: qualifying and publishing are two
different questions. A sale can clear the price threshold and still not be ours
to put on a public feed. The publishing-rights arithmetic is deliberately
deterministic - no AI anywhere near it.
"""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "sample-properties.json")
OUT = os.path.join(ROOT, "Real-Estate-to-Instagram.json")

d = json.load(open(DATA, encoding="utf-8"))
ag = d["agency"]
BROK = ag["brokerage"]
SOLD_MIN = ag["sold_threshold"]
LIST_MIN = ag["listing_threshold"]

nodes = []


def add(name, ntype, tv, params, pos, disabled=False):
    n = {"parameters": params, "id": "b3000000-0000-4000-8000-%012d" % (len(nodes) + 1),
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


def supabase(table, fields=None):
    if fields is None:
        return {"operation": "getAll", "returnAll": True,
                "tableId": {"__rl": True, "value": table, "mode": "name"},
                "options": {}}
    return {"tableId": {"__rl": True, "value": table, "mode": "name"},
            "fieldsUi": {"fieldValues": [{"fieldId": k, "fieldValue": v}
                                         for k, v in fields]}}


# ------------------------------------------------------------------ sticky notes
sticky("""## What this does

A licensed Toronto MLS feed comes in on the left. Six properties. Each one is
asked two separate questions - **is it notable enough to post**, and **are we
allowed to post it** - and those are not the same question.

Out the other end: **two full posts, two market notes, two skipped.**

Every skip is written down with its reason. A content system that silently
drops things is a content system nobody trusts by month three.""",
       (-2040, -560), 440, 300, 4)

sticky("""## Qualifying and publishing are different questions

Toronto sold prices are not public record. They live in the MLS, and the feed
that carries them - **VOW**, the sold-data tier - says the data may only be
shown behind a login, to a registered consumer, and **may not be monetised**. A
public Instagram post of someone else's sale is the exact thing that rule exists
to stop.

**And the photos are a second, separate problem.** Listing photos belong to the
listing brokerage or the photographer they hired - not to the board, and not to
whoever holds the data feed. Putting another brokerage's photo into your branded
template is a copyright claim, and they will see the post.

So there are **three** answers, not two:

- **We listed it** - our photos, our seller, our sale. Post it in full.
- **We were in the deal, or it is genuine market news** - post a **market
  note**: neighbourhood, price band, our own artwork. No borrowed photo, no
  street address.
- **Neither** - do not post, and log why.

The middle lane is the whole design, and it is the answer to the client's
screening question.""",
       (-1570, -560), 520, 460, 3)

sticky("""## Two things worth saying out loud

**Everything that writes or publishes is greyed out on purpose** - the approval
ping, both Instagram calls, and all three database writes. You can run the whole
thing against a real feed, read every verdict, and leave nothing behind.

**Dedupe is keyed on the address, not the MLS number.** This is the gotcha that
bites everyone: when a property is taken off the market and re-listed it gets a
**brand new MLS number**. Dedupe on that and the same house goes out three times
over one spring, which is precisely the failure the client asked to avoid.

**The feed node is the swap point.** Which source belongs there depends entirely
on what the client is licensed for - see `data-sources.md`. Everything to the
right of it is unchanged either way.""",
       (-1010, -560), 460, 380, 6)

# ------------------------------------------------------------------ 1. sources
t = add("Run the Demo", "n8n-nodes-base.manualTrigger", 1, {}, (-2020, 100))

n_feed = add("Property Feed (Licensed MLS)", "n8n-nodes-base.httpRequest", 4.2, {
    "url": "https://api.repliers.io/listings",
    "sendQuery": True,
    "queryParameters": {"parameters": [
        {"name": "city", "value": ag["city"]},
        {"name": "minPrice", "value": str(SOLD_MIN)},
        {"name": "status", "value": "A,U"},
        {"name": "resultsPerPage", "value": "100"},
    ]},
    "options": {},
}, (-1800, -40))

# The register of what has already gone out. Supabase because the posting asked
# for it; read once here, written twice at the far end.
n_reg = add("Already Published (Database)", "n8n-nodes-base.supabase", 1,
            supabase("published_posts"), (-1800, 260))

# ------------------------------------------------------------------ 2. normalise
n_read = add("Read the Property", "n8n-nodes-base.set", 3.4, sets([
    # Unit and street, uppercased, punctuation stripped. NOT the MLS number - a
    # re-listed property gets a new one, and the dedupe would sail straight past.
    ("property_key", "string",
     r"={{ (($json.address || '') + ' ' + ($json.unit || '')).toUpperCase()"
     r".replace(/[^A-Z0-9 ]/g, '').replace(/\s+/g, ' ').trim() }}"),
    ("price", "number",
     "={{ $json.status === 'Sold' ? $json.sold_price : $json.list_price }}"),
    ("headline_date", "string", "={{ $json.sold_date || $json.list_date }}"),
    ("we_listed_it", "boolean",
     "={{ $json.listing_brokerage === %s }}" % json.dumps(BROK)),
    ("we_repped_the_buyer", "boolean",
     "={{ $json.buyer_brokerage === %s }}" % json.dumps(BROK)),
]), (-1580, -40))

n_check = add("Check the Register", "n8n-nodes-base.merge", 3, {
    "mode": "combine",
    "combineBy": "combineByFields",
    "fieldsToMatchString": "property_key",
    "joinMode": "enrichInput1",
    "options": {},
}, (-1360, 100))

# ------------------------------------------------------------------ 3. the arithmetic
QUALIFIES = ("$json.city === %s && (($json.status === 'Sold' && $json.price >= %d)"
             " || ($json.status === 'New Listing' && $json.price >= %d))"
             % (json.dumps(ag["city"]), SOLD_MIN, LIST_MIN))
OURS = "($json.we_listed_it || $json.we_repped_the_buyer)"
EXACT = r"'$' + ($json.price / 1000000).toFixed(2).replace(/\.?0+$/, '') + 'M'"
BAND = ("'$' + ((Math.floor($json.price / 500000) * 500000) / 1000000).toFixed(1)"
        " + 'M-$' + ((Math.floor($json.price / 500000) * 500000 + 500000) / 1000000)"
        ".toFixed(1) + 'M'")

# No AI in here on purpose. Whether a property may be published is a rule, and a
# rule has to give the same answer twice. An LLM that is 97% right is a cease
# and desist every thirty-third post.
n_allow = add("What Are We Allowed to Publish?", "n8n-nodes-base.set", 3.4, sets([
    ("qualifies", "boolean", "={{ %s }}" % QUALIFIES),
    ("already_published", "boolean", "={{ !!$json.posted_at }}"),
    ("we_own_the_photos", "boolean", "={{ $json.we_listed_it }}"),
    ("price_is_ours_to_show", "boolean", "={{ %s }}" % OURS),
    ("price_display", "string", "={{ %s ? %s : %s }}" % (OURS, EXACT, BAND)),
    ("our_role", "string",
     "={{ $json.we_listed_it ? 'Listing brokerage' : ($json.we_repped_the_buyer"
     " ? 'Buyer representation' : 'Not our transaction') }}"),
    ("skip_reason", "string",
     "={{ $json.posted_at ? ('Already published on ' + $json.posted_at)"
     " : ($json.city !== %s ? 'Outside Toronto'"
     " : ((%s) ? '' : 'Under the threshold')) }}"
     % (json.dumps(ag["city"]), QUALIFIES)),
]), (-1140, 100))

n_switch = add("Does It Qualify?", "n8n-nodes-base.switch", 3.2, {
    "rules": {"values": [
        rule([cond("q1", "={{ $json.qualifies }}", "boolean", "true", single=True),
              cond("q2", "={{ $json.already_published }}", "boolean", "false",
                   single=True),
              cond("q3", "={{ $json.we_own_the_photos }}", "boolean", "true",
                   single=True)],
             "Ours - post it in full"),
        rule([cond("q4", "={{ $json.qualifies }}", "boolean", "true", single=True),
              cond("q5", "={{ $json.already_published }}", "boolean", "false",
                   single=True)],
             "Not ours - market note only"),
    ]},
    "options": {"fallbackOutput": "extra",
                "renameFallbackOutput": "Skip - and log why"},
}, (-900, 100))

# ------------------------------------------------------------------ 4. the two posts
# Both lanes set the same field names. That is what lets one caption writer and
# one graphic renderer serve both without a branch downstream.
n_full = add("Build the Full Post", "n8n-nodes-base.set", 3.4, sets([
    ("post_kind", "string", "Full post"),
    ("image_source", "string", "={{ $json.photo_url }}"),
    ("badge", "string",
     "={{ $json.status === 'Sold' ? 'SOLD' : 'JUST LISTED' }}"),
    ("headline", "string",
     "={{ $json.address + ($json.unit ? ' ' + $json.unit : '') }}"),
    ("credit_line", "string",
     "={{ 'Listed by ' + $json.listing_agent + ', ' + $json.listing_brokerage }}"),
]), (-660, -120))

# No photo anywhere in here. The template renders on our own artwork instead.
n_note = add("Build the Market Note", "n8n-nodes-base.set", 3.4, sets([
    ("post_kind", "string", "Market note"),
    ("image_source", "string", ""),
    ("badge", "string",
     "={{ $json.status === 'Sold' ? 'RECENTLY SOLD' : 'NEW TO MARKET' }}"),
    ("headline", "string", "={{ $json.neighbourhood }}"),
    ("credit_line", "string",
     "={{ $json.we_repped_the_buyer ? ('Buyer represented by ' + $json.buyer_agent"
     " + ', ' + $json.buyer_brokerage) : ('Listed by ' + $json.listing_brokerage) }}"),
]), (-660, 120))

n_skip = add("Log the Skip", "n8n-nodes-base.supabase", 1, supabase("skipped_properties", [
    ("mls_number", "={{ $json.mls_number }}"),
    ("property_key", "={{ $json.property_key }}"),
    ("address", "={{ $json.address }}"),
    ("neighbourhood", "={{ $json.neighbourhood }}"),
    ("price", "={{ $json.price }}"),
    ("reason", "={{ $json.skip_reason }}"),
    ("seen_at", "={{ $now.toISO() }}"),
]), (-660, 400), disabled=True)

# Both lanes converge. Everything after the caption writer refers back to this
# node, because an LLM node hands on its answer and nothing else.
n_asm = add("Assemble the Post", "n8n-nodes-base.set", 3.4, sets([
    ("line_1", "string", "={{ $json.badge }}"),
    ("line_2", "string", "={{ $json.headline }}"),
    ("line_3", "string",
     "={{ $json.neighbourhood + '  |  ' + $json.price_display }}"),
    ("line_4", "string",
     "={{ $json.bedrooms + ' bed  |  ' + $json.bathrooms + ' bath  |  '"
     " + $json.sqft.toLocaleString() + ' sq ft' }}"),
    ("disclosure", "string", "={{ $json.credit_line }}"),
]), (-420, 0))

# ------------------------------------------------------------------ 5. the caption
n_model = add("OpenAI Chat Model", "@n8n/n8n-nodes-langchain.lmChatOpenAi", 1.2, {
    "model": {"__rl": True, "value": "gpt-4.1-mini", "mode": "list",
              "cachedResultName": "gpt-4.1-mini"},
    "options": {"temperature": 0.4, "maxTokens": 400},
}, (-180, 240))

CAPTION = """=You write Instagram captions for a Toronto real estate brokerage. The account is a
feed, not a series of one-off posts, so every caption comes out the same shape.

WHAT HAPPENED: {{ $json.line_1 }}
WHERE: {{ $json.neighbourhood }}, Toronto
ADDRESS: {{ $json.post_kind === 'Full post' ? $json.line_2 : 'DO NOT NAME THE STREET ADDRESS - neighbourhood only' }}
PRICE, TO BE USED EXACTLY AS WRITTEN: {{ $json.price_display }}
PROPERTY: {{ $json.line_4 }} {{ $json.property_type }}
ATTRIBUTION: {{ $json.disclosure }}

Rules:
- Use the price string above word for word. **If it is a range, it is a range because we
  are not permitted to publish the exact figure.** Never narrow it, average it, round it,
  or imply a precise number in words.
- State nothing that is not listed above. No "steps from the ravine", no "rare offering",
  no year built, no lot size, no schools. You do not know any of it, and a caption that
  invents a detail about a real address is the one that gets screenshotted.
- If the address line tells you not to name it, name the neighbourhood only. Do not hint
  at the street, the block, or a landmark.
- Reproduce the attribution line exactly as given, as the last line before the hashtags.
- Three short lines, then the attribution, then 5 to 8 hashtags.
- Under 70 words before the hashtags. At most one emoji. No exclamation marks.
- Never write "we are thrilled", "we are proud", or "dream home".

Return the caption only."""

n_cap = add("Write the Caption", "@n8n/n8n-nodes-langchain.chainLlm", 1.4, {
    "promptType": "define", "text": CAPTION, "messages": {"messageValues": []},
}, (-180, 0))

# ------------------------------------------------------------------ 6. the graphic
A = "Assemble the Post"


def a(field):
    return "$('" + A + "').item.json." + field


GRAPHIC_BODY = """={
  "template": "%s",
  "wait_for": true,
  "modifications": [
    { "name": "badge", "text": "{{ %s }}" },
    { "name": "headline", "text": "{{ %s }}" },
    { "name": "detail", "text": "{{ %s }}" },
    { "name": "specs", "text": "{{ %s }}" },
    { "name": "credit", "text": "{{ %s }}" },
    { "name": "photo", "image_url": "{{ %s }}", "hide": {{ %s }} }
  ]
}""" % (ag["brand_template_id"], a("line_1"), a("line_2"), a("line_3"),
        a("line_4"), a("disclosure"), a("image_source"), "!" + a("image_source"))

n_gfx = add("Render the Branded Graphic", "n8n-nodes-base.httpRequest", 4.2, {
    "method": "POST",
    "url": "https://api.bannerbear.com/v2/images",
    "authentication": "genericCredentialType",
    "genericAuthType": "httpHeaderAuth",
    "sendBody": True,
    "specifyBody": "json",
    "jsonBody": GRAPHIC_BODY,
    "options": {},
}, (60, 0))

# ------------------------------------------------------------------ 7. approval
# On for the first fortnight, then switched off. The client asked for fully
# automatic and will get it - just not on day one, on a public account.
n_ok = add("Hold for Approval", "n8n-nodes-base.slack", 2.3, {
    "select": "channel",
    "channelId": {"__rl": True, "value": ag["review_channel"], "mode": "name"},
    "text": ("=*Ready to post* - {{ " + a("post_kind") + " }} for "
             "{{ " + a("line_2") + " }}\n"
             "{{ " + a("line_1") + " }} - {{ " + a("line_3") + " }} "
             "({{ " + a("our_role") + " }})\n"
             "{{ " + a("image_source") + " ? 'Our own listing photo.' : "
             "'_No listing photo - not our transaction, so the template runs on "
             "our own artwork._' }}\n"
             "> {{ $('Write the Caption').item.json.text }}\n"
             "{{ $json.image_url }}"),
    "otherOptions": {},
}, (300, 0), disabled=True)

# ------------------------------------------------------------------ 8. publishing
# Instagram is two calls, always: build a container, then publish it. Meta will
# not take an upload - the image has to already live at a public URL, which is
# why the renderer runs first.
IG = "https://graph.facebook.com/v21.0/YOUR_IG_USER_ID"

n_ig1 = add("Create the Instagram Post", "n8n-nodes-base.httpRequest", 4.2, {
    "method": "POST",
    "url": IG + "/media",
    "authentication": "predefinedCredentialType",
    "nodeCredentialType": "facebookGraphApi",
    "sendQuery": True,
    "queryParameters": {"parameters": [
        {"name": "image_url",
         "value": "={{ $('Render the Branded Graphic').item.json.image_url }}"},
        {"name": "caption", "value": "={{ $('Write the Caption').item.json.text }}"},
    ]},
    "options": {},
}, (540, 0), disabled=True)

n_ig2 = add("Publish It", "n8n-nodes-base.httpRequest", 4.2, {
    "method": "POST",
    "url": IG + "/media_publish",
    "authentication": "predefinedCredentialType",
    "nodeCredentialType": "facebookGraphApi",
    "sendQuery": True,
    "queryParameters": {"parameters": [
        {"name": "creation_id", "value": "={{ $json.id }}"},
    ]},
    "options": {},
}, (780, 0), disabled=True)

# Written last, and only once Instagram has confirmed. Write it before the
# publish call and one failed post makes that property invisible forever.
n_save = add("Save to the Database", "n8n-nodes-base.supabase", 1,
             supabase("published_posts", [
                 ("property_key", "={{ " + a("property_key") + " }}"),
                 ("mls_number", "={{ " + a("mls_number") + " }}"),
                 ("address", "={{ " + a("address") + " }}"),
                 ("neighbourhood", "={{ " + a("neighbourhood") + " }}"),
                 ("status", "={{ " + a("status") + " }}"),
                 ("price", "={{ " + a("price") + " }}"),
                 ("price_display", "={{ " + a("price_display") + " }}"),
                 ("listing_agent", "={{ " + a("listing_agent") + " }}"),
                 ("listing_brokerage", "={{ " + a("listing_brokerage") + " }}"),
                 ("buyer_agent", "={{ " + a("buyer_agent") + " }}"),
                 ("buyer_brokerage", "={{ " + a("buyer_brokerage") + " }}"),
                 ("our_role", "={{ " + a("our_role") + " }}"),
                 ("posted_as", "={{ " + a("post_kind") + " }}"),
                 ("caption", "={{ $('Write the Caption').item.json.text }}"),
                 ("image_url",
                  "={{ $('Render the Branded Graphic').item.json.image_url }}"),
                 ("post_id", "={{ $json.id }}"),
                 ("posted_at", "={{ $now.toISO() }}"),
             ]), (1020, 0), disabled=True)

# ------------------------------------------------------------------ connections
connections = {}


def wire(src, dst, si=0, di=0, kind="main"):
    c = connections.setdefault(src, {}).setdefault(kind, [])
    while len(c) <= si:
        c.append([])
    c[si].append({"node": dst, "type": kind, "index": di})


wire(t, n_feed)
wire(t, n_reg)
wire(n_feed, n_read)
wire(n_read, n_check, 0, 0)
wire(n_reg, n_check, 0, 1)
wire(n_check, n_allow)
wire(n_allow, n_switch)
wire(n_switch, n_full, 0)
wire(n_switch, n_note, 1)
wire(n_switch, n_skip, 2)
wire(n_full, n_asm)                 # both lanes, one shape
wire(n_note, n_asm)
wire(n_asm, n_cap)
wire(n_model, n_cap, 0, 0, "ai_languageModel")
wire(n_cap, n_gfx)
wire(n_gfx, n_ok)
wire(n_ok, n_ig1)
wire(n_ig1, n_ig2)
wire(n_ig2, n_save)

# ------------------------------------------------------------------ pinned data
pin_data = {
    n_feed: [{"json": p} for p in d["properties"]],
    n_reg: [{"json": r} for r in d["register"]],
}

wf = {"name": "Real Estate to Instagram", "nodes": nodes, "connections": connections,
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

# Every node name referenced inside an expression must be a real node.
# Deliberately naive: it takes whatever sits between $(' and the next quote. An
# apostrophe in a node name breaks that, which is the point - a name needing an
# escape is a name waiting to break something, so it should fail here.
for n in nodes:
    for ref in re.findall(r"\$\('(.*?)'\)", json.dumps(n["parameters"])):
        if ref not in names:
            errors.append("%s refers to a node that does not exist: %r "
                          "(check for an apostrophe in the node name)"
                          % (n["name"], ref))

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
reachable.add(n_model)          # sub-nodes hang off their parent, not the trigger
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

# A market note must never carry a borrowed photo. It is the one rule this whole
# demo exists to demonstrate, so it gets checked rather than trusted.
note_params = json.dumps([n["parameters"] for n in nodes if n["name"] == n_note])
if "photo_url" in note_params:
    errors.append("the market note lane references photo_url - that is the "
                  "borrowed-asset failure this demo is about")

# ---- the same arithmetic, run here in Python against the same pinned data.
# If the canvas tells a different story from the README, this is where it shows.
posted = {r["property_key"]: r for r in d["register"]}


def key_of(p):
    raw = (p["address"] + " " + (p["unit"] or "")).upper()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", "", raw)).strip()


def shown(price, ours):
    if ours:
        return "$" + ("%.2f" % (price / 1e6)).rstrip("0").rstrip(".") + "M"
    low = (price // 500000) * 500000
    return "$%.1fM-$%.1fM" % (low / 1e6, (low + 500000) / 1e6)


actual, reasons, prices = {}, {}, {}
for p in d["properties"]:
    price = p["sold_price"] if p["status"] == "Sold" else p["list_price"]
    listed = p["listing_brokerage"] == BROK
    bought = p["buyer_brokerage"] == BROK
    qualifies = p["city"] == ag["city"] and (
        (p["status"] == "Sold" and price >= SOLD_MIN) or
        (p["status"] == "New Listing" and price >= LIST_MIN))
    seen = posted.get(key_of(p))
    if seen:
        actual[p["mls_number"]] = "skip"
        reasons[p["mls_number"]] = "Already published on " + seen["posted_at"]
    elif not qualifies:
        actual[p["mls_number"]] = "skip"
        reasons[p["mls_number"]] = ("Outside Toronto" if p["city"] != ag["city"]
                                    else "Under the threshold")
    elif listed:
        actual[p["mls_number"]] = "full_post"
    else:
        actual[p["mls_number"]] = "market_note"
    if actual[p["mls_number"]] != "skip":
        prices[p["mls_number"]] = shown(price, listed or bought)

for mls, want in d["expected"].items():
    if actual.get(mls) != want:
        errors.append("%s should be %r but the rules put it in %r"
                      % (mls, want, actual.get(mls)))
if set(actual) != set(d["expected"]):
    errors.append("expected block does not cover every property")
for mls, want in d["expected_skip_reasons"].items():
    if reasons.get(mls) != want:
        errors.append("%s skip reason is %r, expected %r"
                      % (mls, reasons.get(mls), want))
for mls, want in d["expected_price_display"].items():
    if prices.get(mls) != want:
        errors.append("%s price shows as %r, expected %r"
                      % (mls, prices.get(mls), want))

# The rule that matters: nobody else's sale ever gets an exact figure.
for p in d["properties"]:
    m = p["mls_number"]
    if m in prices and p["listing_brokerage"] != BROK and p["buyer_brokerage"] != BROK:
        if "-" not in prices[m]:
            errors.append("%s is not our transaction but shows an exact price" % m)

functional = [n for n in nodes if n["type"] != "n8n-nodes-base.stickyNote"]
tally = {}
for v in actual.values():
    tally[v] = tally.get(v, 0) + 1

print("nodes: %d functional (+%d notes) | Code nodes: %d | pinned: %d | disabled: %d"
      % (len(functional), len(nodes) - len(functional), len(code_nodes), len(pin_data),
         len([n for n in nodes if n.get("disabled")])))
print("properties: %d  %s" % (len(d["properties"]), tally))
print("prices shown:", prices)
print("VALIDATION:", "PASS" if not errors else "FAIL")
for e in errors:
    print("  -", e)
import sys
sys.path.insert(0, os.path.dirname(ROOT))
from node_versions import unverified
for line in unverified(OUT):
    print("  unverified:", line)
print("wrote", OUT)
