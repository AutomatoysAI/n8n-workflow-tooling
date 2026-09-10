"""Which n8n node versions has nobody else confirmed?

Every node in a workflow file carries a version number - "Google Sheets, version
4.5". Those numbers are written by hand when a build script generates the JSON,
and there is no n8n instance here to check them against. A wrong one may not
import cleanly, and the place you find out is in front of a client.

The check: two demos were often built in separate sessions without coordinating.
A version that turns up in two or more of them has been arrived at twice
independently, which is real evidence. A version that appears in exactly one
demo has been confirmed by nobody.

That is not proof. It is the difference between "something in here might be
wrong" and "open these three nodes first".

Two ways to use it:

    python node_versions.py          - the whole library, demo by demo

and from inside a build script, after the JSON is written:

    import sys, os
    sys.path.insert(0, os.path.dirname(ROOT))
    from node_versions import unverified
    for line in unverified(OUT):
        print("  unverified:", line)
"""
import json, os, glob

HERE = os.path.dirname(os.path.abspath(__file__))
SKIP = ("n8n-nodes-base.stickyNote",)


def _workflows(root=HERE):
    """Every generated workflow file in the demos folder, keyed by demo name."""
    out = {}
    for path in sorted(glob.glob(os.path.join(root, "*", "*.json"))):
        if "sample" in os.path.basename(path).lower():
            continue
        try:
            wf = json.load(open(path, encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if isinstance(wf, dict) and "nodes" in wf:
            out[os.path.basename(os.path.dirname(path))] = wf
    return out


def _versions(wf):
    return {"%s@%s" % (n["type"], n["typeVersion"])
            for n in wf["nodes"] if n["type"] not in SKIP}


def usage(root=HERE):
    """{'nodeType@version': {demo names that use it}}"""
    seen = {}
    for demo, wf in _workflows(root).items():
        for v in _versions(wf):
            seen.setdefault(v, set()).add(demo)
    return seen


def unverified(workflow_path):
    """Node versions in this workflow that no other demo uses.

    Returns a list of strings, ready to print. Empty means every version in
    this file is corroborated by at least one independently built demo.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(workflow_path)))
    me = os.path.basename(os.path.dirname(os.path.abspath(workflow_path)))
    seen = usage(root)
    try:
        mine = _versions(json.load(open(workflow_path, encoding="utf-8")))
    except (ValueError, OSError):
        return ["could not read %s" % workflow_path]
    return sorted(v for v in mine if seen.get(v, set()) <= {me})


if __name__ == "__main__":
    seen = usage()
    demos = _workflows()
    print("%d node versions across %d demos\n" % (len(seen), len(demos)))

    solo = {v: list(d)[0] for v, d in seen.items() if len(d) == 1}
    print("CONFIRMED BY TWO OR MORE DEMOS: %d" % (len(seen) - len(solo)))
    print("USED IN ONLY ONE DEMO - nobody has confirmed these: %d\n" % len(solo))

    for demo in sorted(demos):
        mine = sorted(v for v in _versions(demos[demo]) if v in solo)
        if mine:
            print("%s - open these first on import:" % demo)
            for v in mine:
                print("    %s" % v)
        else:
            print("%s - every version confirmed elsewhere" % demo)
