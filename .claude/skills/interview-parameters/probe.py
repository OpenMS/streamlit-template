"""Measure what each parameter of a python tool actually does.

Runs the tool repeatedly on a downsampled input, sweeping one parameter at a
time, and reports the measured effect on its declared OUTPUTS.

A parameter that shows no effect in isolation is re-probed with every other
numeric parameter driven to its neutral value. If an effect appears, the
parameter is MASKED, not inert -- reporting those as inert is how a probe ends
up recommending that the most important parameter in a notebook be hardcoded.

Usage:
  python probe.py --script identify.py --inputs a.fasta b.mzML \
      --budget-key max-spectra --budget 40
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd

# A metric must move by more than this fraction to count as any effect at all.
EFFECT_THRESHOLD = 0.02

# Below this, a parameter is not yet worth surfacing on its own evidence, so it
# is a candidate for masking. Masking is a COMPARISON between the masked and
# unmasked effect, never an absolute test for zero: Task 2's precursor tolerance
# measures 4.2% as shipped -- past a zero test, but still inert across its whole
# usable range, because another parameter opens a window 1700x wider.
MATERIAL_THRESHOLD = 0.25

# Unmasking must reveal an effect at least this many times larger to be reported
# as masking rather than noise.
MASKING_RATIO = 3.0
# Refuse to start a masking pass predicted to run longer than this without
# --allow-long. O(n^2) is fine at 11 parameters and an overnight job at 43.
LONG_PROBE_HOURS = 1.0


def load_tool(script: Path):
    spec = importlib.util.spec_from_file_location("tool_under_probe", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sweep_values(param):
    """Three probe points for a parameter, or None if it is not probeable."""
    value = param.get("value")
    if isinstance(value, bool):
        return [False, True]
    if isinstance(value, (int, float)):
        lo = param.get("min", 0 if value >= 0 else value * 2)
        hi = param.get("max", value * 4 if value else 1)
        pts = sorted({lo, value, hi})
        if isinstance(value, int) and not isinstance(value, bool):
            pts = sorted({int(round(x)) for x in pts})
        return pts if len(pts) > 1 else None
    if param.get("options"):
        return list(param["options"])
    return None


def neutral_value(param):
    """The value at which a parameter stops contributing."""
    value = param.get("value")
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return param.get("min", 0)
    return value


def run_once(script: Path, base: dict, overrides: dict, outputs) -> dict | None:
    """Run the tool once and reduce its outputs to a metric dict."""
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "out"
        out_dir.mkdir()
        params = dict(base)
        params.update(overrides)
        params["out"] = [str(out_dir)]

        pfile = Path(tmp) / "params.json"
        pfile.write_text(json.dumps(params), encoding="utf-8")

        proc = subprocess.run(
            [sys.executable, str(script), str(pfile)],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            return None

        metrics = {}
        for spec in outputs:
            path = out_dir / spec["file"]
            if not path.exists() or path.suffix != ".parquet":
                continue
            df = pd.read_parquet(path)
            metrics[f"{spec['key']}.rows"] = float(len(df))
            for col in df.select_dtypes("number").columns:
                if len(df):
                    metrics[f"{spec['key']}.{col}.mean"] = float(df[col].mean())
        return metrics


def effect_size(runs: list[dict | None]) -> float:
    """Largest relative spread of any metric across a sweep."""
    good = [r for r in runs if r]
    if len(good) < 2:
        return 0.0
    worst = 0.0
    for key in good[0]:
        vals = [r.get(key) for r in good if r.get(key) is not None]
        if len(vals) < 2:
            continue
        lo, hi = min(vals), max(vals)
        if hi == lo:
            continue
        denom = max(abs(lo), abs(hi)) or 1.0
        worst = max(worst, (hi - lo) / denom)
    return worst


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True, type=Path)
    ap.add_argument("--inputs", nargs="+", required=True)
    ap.add_argument("--budget-key", default=None,
                    help="Parameter that limits work, set to --budget while probing.")
    ap.add_argument("--budget", type=int, default=40)
    ap.add_argument("--allow-long", action="store_true",
                    help="Run a masking pass predicted to exceed "
                         "LONG_PROBE_HOURS.")
    ap.add_argument("--no-masking", action="store_true",
                    help="Sweep only. CANNOT distinguish inert from "
                         "masked -- the error this tool exists to catch.")
    ap.add_argument("--params", default=None, help="Comma-separated subset.")
    args = ap.parse_args()

    tool = load_tool(args.script)
    defaults = {d["key"]: d for d in tool.DEFAULTS}
    outputs = tool.OUTPUTS

    base = {"in": [str(Path(x).resolve()) for x in args.inputs]}
    if args.budget_key:
        base[args.budget_key] = args.budget

    skip = {"in", "out", args.budget_key}
    wanted = set(args.params.split(",")) if args.params else None
    targets = [
        d for k, d in defaults.items()
        if k not in skip and not d.get("hide")
        and (wanted is None or k in wanted) and sweep_values(d)
    ]

    print(f"probing {len(targets)} parameters, budget {args.budget_key}={args.budget}\n")

    # Time the baseline so the cost can be stated before the wait, not after it.
    # A multi-minute silence reads as a hang, and the masking re-probe below is
    # nested -- it can be much longer than the sweeps that precede it.
    t0 = time.time()
    baseline = run_once(args.script, base, {}, outputs)
    per_run = max(time.time() - t0, 0.01)
    if baseline is None:
        print("ERROR: tool failed at default parameters", file=sys.stderr)
        return 1

    # A budget key that does not actually limit work is worse than none: it caps
    # every metric effect_size reads while looking like a speed-up. The classic
    # case is a truncation that sits AFTER the expensive step -- max-features on a
    # tool whose cost is feature detection buys nothing and pins features.rows.
    # Trusting the caller to pick correctly is how a whole probe gets invalidated,
    # so measure it: a real budget key makes a quarter-budget run meaningfully
    # faster.
    if args.budget_key:
        small = max(1, args.budget // 4)
        t1 = time.time()
        probe_small = run_once(args.script, {**base, args.budget_key: small}, {}, outputs)
        small_run = max(time.time() - t1, 0.01)
        speedup = per_run / small_run
        if probe_small is None:
            print(f"  WARNING: the tool failed at {args.budget_key}={small}; "
                  f"cannot verify the budget key limits work", flush=True)
        elif speedup < 1.25:
            print(f"\n  WARNING: {args.budget_key} does not appear to limit work.")
            print(f"    {args.budget_key}={args.budget} took {per_run:.1f}s, "
                  f"={small} took {small_run:.1f}s ({speedup:.2f}x).")
            print( "    A budget key applied AFTER the expensive step buys no time")
            print( "    and caps every metric this probe reads -- every effect size")
            print( "    below would measure the cap, not the parameter.")
            print( "    Budget by shrinking the INPUT instead (crop the mzML).\n",
                  flush=True)
        else:
            print(f"  {args.budget_key} verified: {speedup:.1f}x faster at "
                  f"{small} than at {args.budget}", flush=True)

    planned = sum(len(sweep_values(p)) for p in targets)
    # The masking pass is O(n^2): every low-effect parameter is re-swept against
    # every other one. At 11 parameters that is minutes; at 43 it is an overnight
    # job, and nothing used to say so until you were already inside it.
    worst_masking = sum(
        len(sweep_values(p)) * max(len(targets) - 1, 0) for p in targets
    )
    worst_hours = per_run * worst_masking / 3600
    print(f"  one run takes {per_run:.1f}s")
    print(f"  {planned} sweep runs planned  ->  about "
          f"{per_run * planned / 60:.1f} min")
    print(f"  masking re-probe is O(n^2): worst case {worst_masking} more runs "
          f"-> up to {worst_hours:.1f} hours")
    print(f"  raise --budget to trade accuracy for time\n", flush=True)

    if worst_hours > LONG_PROBE_HOURS and not args.allow_long:
        print(f"REFUSING to start: the masking pass could run {worst_hours:.1f} "
              f"hours (limit {LONG_PROBE_HOURS}).", file=sys.stderr)
        print("Choose one:", file=sys.stderr)
        print("  --params a,b,c     probe a shortlist", file=sys.stderr)
        print(f"  --budget <smaller> shrink each run "
              f"(currently {args.budget_key}={args.budget})", file=sys.stderr)
        print("  --no-masking       sweep only -- NOTE this cannot tell inert "
              "from masked, which is the error this tool exists to catch",
              file=sys.stderr)
        print("  --allow-long       run it anyway", file=sys.stderr)
        return 2

    results = []
    started = time.time()
    for i, param in enumerate(targets, 1):
        key = param["key"]
        values = sweep_values(param)
        print(f"  [{i}/{len(targets)}] {key:30s} sweeping {len(values)} values "
              f"({per_run * len(values):.0f}s)", flush=True)
        runs = [run_once(args.script, base, {key: v}, outputs) for v in values]
        eff = effect_size(runs)
        failures = sum(1 for r in runs if r is None)

        record = {
            "key": key, "values": values, "effect": eff,
            "failures": failures, "masked_by": None,
        }

        if eff < MATERIAL_THRESHOLD and not args.no_masking:
            # Not convincing on its own evidence. Before recommending against it,
            # check whether another parameter is swamping it. Keep the strongest
            # unmasking found, not merely the first.
            candidates = [
                o for o in targets
                if o["key"] != key and neutral_value(o) != o.get("value")
            ]
            print(f"        effect {eff:.1%} is under {MATERIAL_THRESHOLD:.0%} -- "
                  f"re-probing against {len(candidates)} other parameter(s) "
                  f"({per_run * len(candidates) * len(values):.0f}s) before "
                  f"concluding anything", flush=True)
            best_unmask = None
            for other in targets:
                if other["key"] == key:
                    continue
                neutral = neutral_value(other)
                if neutral == other.get("value"):
                    continue
                print(f"        ... with {other['key']} neutralised", flush=True)
                re_runs = [
                    run_once(args.script, base, {key: v, other["key"]: neutral}, outputs)
                    for v in values
                ]
                re_eff = effect_size(re_runs)
                if (
                    re_eff > MATERIAL_THRESHOLD
                    and re_eff >= MASKING_RATIO * max(eff, EFFECT_THRESHOLD)
                    and (best_unmask is None or re_eff > best_unmask[1])
                ):
                    best_unmask = (other["key"], re_eff)
            if best_unmask:
                record["masked_by"], record["effect_unmasked"] = best_unmask

        results.append(record)
        tag = (
            f"MASKED by {record['masked_by']} "
            f"(effect {record.get('effect_unmasked', 0):.1%} once unmasked)"
            if record["masked_by"]
            else ("inert" if eff <= EFFECT_THRESHOLD else f"effect {eff:.1%}")
        )
        if failures:
            tag += (f"   [{failures}/{len(values)} sweep points FAILED - "
                    f"effect measured over {len(values) - failures}]")
        print(f"        -> {tag}", flush=True)

    print(f"\n  probed in {time.time() - started:.0f}s")
    print("\n" + "=" * 74)
    print(f"{'parameter':32s} {'effect':>9s}  recommendation")
    print("=" * 74)
    for r in sorted(results, key=lambda x: -x["effect"]):
        if r["masked_by"]:
            rec = f"KEEP - masked by {r['masked_by']}, not inert"
            eff = f"{r['effect_unmasked']:.1%}*"
        elif r["effect"] > 0.25:
            rec = "KEEP - large effect"
            eff = f"{r['effect']:.1%}"
        elif r["effect"] > EFFECT_THRESHOLD:
            rec = "ADVANCED - small but real effect"
            eff = f"{r['effect']:.1%}"
        elif r["failures"]:
            # A sweep that lost points did not measure inertness, it measured
            # less. Recommending HARDCODE here is the exact error this whole
            # skill exists to prevent, arrived at by arithmetic rather than by
            # masking.
            rec = (f"INCOMPLETE - {r['failures']} of {len(r['values'])} runs "
                   f"failed, no verdict")
            eff = f"{r['effect']:.1%}?"
        else:
            rec = "HARDCODE - no measurable effect"
            eff = f"{r['effect']:.1%}"
        print(f"{r['key']:32s} {eff:>9s}  {rec}")
    print("\n* effect measured with the masking parameter neutralised")

    incomplete = [r for r in results if r["failures"]]
    if incomplete:
        print(f"\nWARNING: {len(incomplete)} parameter(s) had sweep points fail. "
              "A failed point is")
        print("         dropped silently by the effect calculation, so the effect "
              "is measured")
        print("         over fewer values and reads LOWER than the truth - the "
              "direction that")
        print("         produces HARDCODE. Common cause: an int/float parameter "
              "with no declared")
        print("         min/max, so the sweep invents bounds and probes an "
              "invalid value.")
        for r in incomplete:
            print(f"           {r['key']:30s} tried {r['values']}")

    # The scope travels with the numbers, or the numbers get reused outside it.
    # These effect sizes were measured with every parameter NOT in this set
    # pinned at whatever the tool defaults to; widen the set and they stop being
    # evidence.
    print(f"\nSCOPE: measured over these {len(targets)} parameter(s) only, with "
          f"all others held at their defaults.")
    print("       Exposing further parameters invalidates these figures - "
          "re-probe rather than carrying them forward.")
    if args.no_masking:
        print("\nWARNING: --no-masking was used. An 'inert' reading here may be a "
              "masked parameter;")
        print("         this run cannot tell the difference.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
