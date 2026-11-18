"""latency + cost from what the agent logged. only real turn_metrics rows, no made up numbers
usage: python latency_report.py [runs/run123.jsonl ...]   (no args = every call in the db)"""
import sys
import json
from pathlib import Path

import numpy as np
from sqlalchemy import select

from backend.db import SessionLocal
from backend.models import Call, TurnMetric

ROOT = Path(__file__).resolve().parent
PRICES = json.load(open(ROOT / "prices.json"))
TARGET_MS = 800


def pct(a, p):
    return float(np.percentile(a, p)) if len(a) else float("nan")


def call_cost(call: Call):
    """dollars for one call using prices.json and the usage the agent saved"""
    if not call.usage or not call.ended_at:
        return None
    minutes = (call.ended_at - call.started_at).total_seconds() / 60
    p = PRICES
    llm = tts = stt = 0.0
    for u in call.usage.get("models", []):
        if u.get("type") == "llm_usage":
            h = p["anthropic_haiku_4_5"]
            fresh = u.get("input_tokens", 0) - u.get("input_cached_tokens", 0) - u.get("input_cache_creation_tokens", 0)
            llm += (fresh * h["input_per_mtok"] + u.get("input_cached_tokens", 0) * h["cache_read_per_mtok"]
                    + u.get("input_cache_creation_tokens", 0) * h["cache_write_per_mtok"]
                    + u.get("output_tokens", 0) * h["output_per_mtok"]) / 1e6
        elif u.get("type") == "tts_usage":
            tts += u.get("characters_count", 0) / 1000 * p["elevenlabs_flash_per_1k_chars"]
        elif u.get("type") == "stt_usage":
            stt += u.get("audio_duration", 0) / 60 * p["deepgram_nova3_stream_per_min"]
    phone = minutes * (p["twilio_sip_origination_ca_local_per_min"] if call.sip_identity else 0)
    lk = minutes * p["livekit_per_min"]
    return {"llm": llm, "tts": tts, "stt": stt, "phone": phone, "livekit": lk, "total": llm + tts + stt + phone + lk,
            "minutes": minutes}


def main(paths):
    with SessionLocal() as db:
        q = select(Call)
        if paths:
            rooms = [json.loads(l)["room"] for p in paths for l in open(p)]
            q = q.where(Call.room.in_(rooms))
        calls = db.scalars(q).all()
        ids = [c.id for c in calls]
        turns = db.scalars(select(TurnMetric).where(TurnMetric.call_id.in_(ids))).all() if ids else []

    v2v = np.array([t.v2v_ms for t in turns if t.v2v_ms is not None])
    if not len(v2v):
        sys.exit("no turn metrics logged yet, run some calls first")

    print(f"calls: {len(calls)}   agent turns with latency: {len(v2v)}")
    print(f"voice-to-voice  median {pct(v2v, 50):.0f} ms   p95 {pct(v2v, 95):.0f} ms   max {v2v.max():.0f} ms")
    if pct(v2v, 50) > TARGET_MS:
        print(f"  median is ABOVE the {TARGET_MS} ms target")

    stages = {"end of utterance": [t.eou_delay_ms for t in turns],
              "LLM first token": [t.llm_ttft_ms for t in turns],
              "TTS first byte": [t.tts_ttfb_ms for t in turns]}
    med = {k: float(np.median([x for x in v if x is not None])) if any(x is not None for x in v) else 0.0
           for k, v in stages.items()}
    for k, v in med.items():
        print(f"  median {k}: {v:.0f} ms")
    no_tool = [t.v2v_ms for t in turns if t.v2v_ms is not None and not t.had_tool_call]
    tool = [t.v2v_ms for t in turns if t.v2v_ms is not None and t.had_tool_call]
    if tool:
        print(f"  median without tool call {np.median(no_tool):.0f} ms, with tool call {np.median(tool):.0f} ms")

    costs = [c for c in (call_cost(x) for x in calls) if c]
    if costs:
        avg = {k: np.mean([c[k] for c in costs]) for k in costs[0]}
        print(f"cost per call (avg of {len(costs)}, {avg['minutes']:.1f} min): ${avg['total']:.4f}  "
              f"(llm {avg['llm']:.4f}, stt {avg['stt']:.4f}, tts {avg['tts']:.4f}, phone {avg['phone']:.4f})")

    chart(med, pct(v2v, 50), pct(v2v, 95))


def chart(med, p50, p95, out=ROOT / "docs" / "images" / "latency_breakdown.png"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    other = max(p50 - sum(med.values()), 0)  # network, audio buffering, playout
    parts = list(med.items()) + [("other / network", other)]
    colors = ["#4C78A8", "#F58518", "#54A24B", "#BAB0AC"]
    fig, ax = plt.subplots(figsize=(8, 2.6), dpi=150)
    left = 0
    for (name, val), c in zip(parts, colors):
        ax.barh(0, val, left=left, color=c, label=f"{name} ({val:.0f} ms)")
        left += val
    ax.axvline(TARGET_MS, color="#B22222", ls="--", lw=1)
    ax.text(TARGET_MS, 0.45, " 800 ms target", color="#B22222", fontsize=8, va="bottom")
    ax.set_yticks([])
    ax.set_xlabel("milliseconds (median turn)")
    ax.set_title(f"Voice-to-voice latency: median {p50:.0f} ms, p95 {p95:.0f} ms", fontsize=10)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.38), ncol=2, fontsize=8, frameon=False)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight")
    print("chart saved to", out)


if __name__ == "__main__":
    main(sys.argv[1:])
