"""Validate a call's analysis.json (written by the analyst) and print it as a chat-ready scorecard.

    python tools/analysis.py check <call_id>     # validate, exit non-zero with every problem
    python tools/analysis.py card  <call_id>     # validate, then print the scorecard text
    python tools/analysis.py template            # print an empty analysis.json to fill in

The fixed schema is what lets tools/dashboard.py compare calls across the whole team.
"""

from __future__ import annotations

import argparse
import json
import sys

from common import call_dir, fmt_ts, read_json, utf8_stdout

OBJECTION_CATEGORIES = ["price", "timing", "competitor", "authority", "need", "trust", "integration", "other"]
STAGES = ["lead", "discovery", "demo", "proposal", "negotiation", "closed-won", "closed-lost"]
BANT_STATUS = ["confirmed", "partial", "unknown"]
SENTIMENTS = ["positive", "neutral", "negative", "mixed"]

TEMPLATE = {
    "call_id": "<call_id>",
    "account": "BrightMart",
    "contact": "Priya Shah, Head of Ops",
    "rep": "Arjun Mehta",
    "meeting_type": "in-person demo",
    "summary": "Two or three sentences a manager can read in ten seconds.",
    "sentiment": "positive",
    "deal_score": 72,
    "deal_score_reason": "Clear pain and budget; decision maker not yet met.",
    "stage_suggested": "proposal",
    "bant": {
        "budget": {"status": "partial", "evidence": "quote or paraphrase"},
        "authority": {"status": "unknown", "evidence": ""},
        "need": {"status": "confirmed", "evidence": ""},
        "timeline": {"status": "partial", "evidence": ""},
    },
    "objections": [{"category": "price", "quote": "exact words", "handled": True, "how": "what the rep said"}],
    "buying_signals": ["asked about onboarding time"],
    "risks": ["CFO not involved yet"],
    "competitors": ["Zoho"],
    "products_discussed": ["Inventory module"],
    "next_steps": [{"owner": "rep", "action": "send pricing for 40 stores", "due": "2026-11-10"}],
    "coaching": [{"tip": "Ask about the approval process earlier", "evidence": "segment 41"}],
}


def validate(a: dict) -> list[str]:
    errs: list[str] = []

    def need(key: str, kind: type | tuple) -> None:
        if key not in a:
            errs.append(f"missing '{key}'")
        elif not isinstance(a[key], kind):
            errs.append(f"'{key}' should be {kind}")

    for key in ("call_id", "account", "contact", "rep", "summary", "sentiment", "deal_score_reason", "stage_suggested"):
        need(key, str)
    need("deal_score", int)
    need("bant", dict)
    for key in ("objections", "buying_signals", "risks", "competitors", "next_steps", "coaching"):
        need(key, list)
    if errs:
        return errs

    if a["sentiment"] not in SENTIMENTS:
        errs.append(f"sentiment '{a['sentiment']}' not in {SENTIMENTS}")
    if not 0 <= a["deal_score"] <= 100:
        errs.append("deal_score must be 0-100")
    if a["stage_suggested"] not in STAGES:
        errs.append(f"stage_suggested '{a['stage_suggested']}' not in {STAGES}")
    for k in ("budget", "authority", "need", "timeline"):
        item = a["bant"].get(k)
        if not isinstance(item, dict) or item.get("status") not in BANT_STATUS:
            errs.append(f"bant.{k}.status must be one of {BANT_STATUS}")
    for i, o in enumerate(a["objections"]):
        if not isinstance(o, dict) or o.get("category") not in OBJECTION_CATEGORIES:
            errs.append(f"objections[{i}].category must be one of {OBJECTION_CATEGORIES}")
        elif not isinstance(o.get("handled"), bool):
            errs.append(f"objections[{i}].handled must be true/false")
    for i, s in enumerate(a["next_steps"]):
        if not isinstance(s, dict) or not s.get("action"):
            errs.append(f"next_steps[{i}] needs an 'action'")
    return errs


def card(a: dict, metrics: dict | None) -> str:
    icon = {"positive": "🟢", "neutral": "⚪", "negative": "🔴", "mixed": "🟡"}[a["sentiment"]]
    bant_icon = {"confirmed": "✅", "partial": "🟡", "unknown": "❓"}
    out = [
        f"📊 Call scorecard: {a['account']} ({a['contact']})",
        f"Deal score {a['deal_score']}/100 {icon} {a['sentiment']} · suggested stage: {a['stage_suggested']}",
        f"Why: {a['deal_score_reason']}",
        "",
        a["summary"],
        "",
        "BANT: " + " · ".join(f"{k.title()} {bant_icon[a['bant'][k]['status']]}" for k in ("budget", "authority", "need", "timeline")),
    ]
    if metrics:
        r = metrics["speakers"][metrics["rep"]]
        out.append(f"Rep talk ratio {r['talk_ratio']:.0%} · {r['questions']} questions · longest monologue {fmt_ts(r['longest_monologue_sec'])}")
    if a["objections"]:
        out += ["", "Objections:"]
        out += [f"• [{o['category']}] \"{o.get('quote', '')}\" {'✅ handled' if o['handled'] else '⚠️ not handled'}" for o in a["objections"]]
    if a["buying_signals"]:
        out += ["", "Buying signals: " + "; ".join(a["buying_signals"])]
    if a["risks"]:
        out += ["Risks: " + "; ".join(a["risks"])]
    if a["competitors"]:
        out += ["Competitors mentioned: " + ", ".join(a["competitors"])]
    if a["next_steps"]:
        out += ["", "Next steps:"]
        out += [f"• {s.get('owner', '?')}: {s['action']}" + (f" (by {s['due']})" if s.get("due") else "") for s in a["next_steps"]]
    if a["coaching"]:
        out += ["", "Coaching:"]
        out += [f"• {c['tip']}" for c in a["coaching"]]
    if metrics and metrics.get("flags"):
        out += [f"• {f}" for f in metrics["flags"]]
    return "\n".join(out)


def main() -> None:
    utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["check", "card", "template"])
    parser.add_argument("call_id", nargs="?")
    args = parser.parse_args()

    if args.command == "template":
        print(json.dumps(TEMPLATE, indent=2, ensure_ascii=False))
        return
    if not args.call_id:
        sys.exit("error: call_id required")

    folder = call_dir(args.call_id)
    path = folder / "analysis.json"
    if not path.exists():
        sys.exit(f"error: {path} does not exist yet. `python tools/analysis.py template` shows the shape.")
    try:
        a = read_json(path)
    except json.JSONDecodeError as exc:
        sys.exit(f"error: analysis.json is not valid JSON: {exc}")
    errs = validate(a)
    if errs:
        print("analysis.json has problems:")
        for e in errs:
            print(f"  - {e}")
        sys.exit(1)
    if args.command == "check":
        print("analysis.json OK")
        return
    metrics = read_json(folder / "metrics.json") if (folder / "metrics.json").exists() else None
    print(card(a, metrics))


if __name__ == "__main__":
    main()
