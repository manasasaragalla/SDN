"""Combines one or more `evaluation_runs_*.json` files written by
evaluation/run_evaluation.py (a long sweep is often split across several
invocations -- see that script's docstring) into a single merged dataset,
runs the pure aggregation (backend/evaluation/aggregate.py), and writes
both a machine-readable combined summary and a short human-readable
report -- item 8/9 of the Phase 13 evaluation brief.

Usage:
    PYTHONPATH=. python3 evaluation/summarize.py
        # combines every evaluation_runs_*.json under evaluation/results/

    PYTHONPATH=. python3 evaluation/summarize.py evaluation/results/evaluation_runs_123.json evaluation/results/evaluation_runs_456.json
        # combines only the named files

This script does no Mininet/Ryu work and needs no root privileges --
it only reads and aggregates already-collected real run records.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _load_runs(paths: list[Path]) -> list[dict]:
    all_runs: list[dict] = []
    for path in paths:
        all_runs.extend(json.loads(path.read_text()))
    return all_runs


def _format_pct(x) -> str:
    return "n/a" if x is None else f"{x * 100:.0f}%"


def _render_report(all_runs: list[dict], summary: dict) -> str:
    lines = ["# Phase 13 evaluation report", "",
              f"Total runs: {len(all_runs)} "
              f"({len(all_runs) - summary['n_infra_errors_total']} real measured, "
              f"{summary['n_infra_errors_total']} infrastructure error(s), excluded from all "
              f"statistics below).", ""]

    lines.append("## Per (scenario, mode) statistics")
    lines.append("")
    lines.append("| scenario | mode | n | initial satisfied | final satisfied | mean corrections | mean time (s) |")
    lines.append("|---|---|---|---|---|---|---|")
    for key in sorted(summary["groups"]):
        g = summary["groups"][key]
        lines.append(
            f"| {g['scenario']} | {g['mode']} | {g['n_runs']} | "
            f"{_format_pct(g['initial_satisfaction_rate'])} | {_format_pct(g['final_satisfaction_rate'])} | "
            f"{g['mean_correction_iterations']:.2f} | {g['mean_execution_time_s']:.1f} |"
        )
    lines.append("")

    lines.append("## Does closed-loop correction improve intent satisfaction? (per scenario)")
    lines.append("")
    lines.append("| scenario | one-shot satisfied | closed-loop satisfied | improvement | "
                  "correction helped | correction ran, did not help |")
    lines.append("|---|---|---|---|---|---|")
    for scenario, c in summary["scenario_comparison"].items():
        improvement = "n/a" if c["improvement"] is None else f"{c['improvement'] * 100:+.0f}pp"
        lines.append(
            f"| {scenario} | {_format_pct(c['one_shot_satisfaction_rate'])} | "
            f"{_format_pct(c['closed_loop_satisfaction_rate'])} | {improvement} | "
            f"{c['runs_where_correction_helped']} | {c['runs_where_correction_ran_but_did_not_help']} |"
        )
    lines.append("")

    overall = summary["overall"]
    lines.append("## Overall")
    lines.append("")
    lines.append(f"- ONE_SHOT satisfaction rate (all scenarios): {_format_pct(overall['one_shot_satisfaction_rate'])}")
    lines.append(f"- CLOSED_LOOP satisfaction rate (all scenarios): "
                  f"{_format_pct(overall['closed_loop_satisfaction_rate'])}")
    improvement = ("n/a" if overall["overall_improvement"] is None
                   else f"{overall['overall_improvement'] * 100:+.0f} percentage points")
    lines.append(f"- Overall improvement from closed-loop correction: {improvement}")
    if summary["infra_errors"]:
        lines.append(f"- Infrastructure errors by scenario (excluded above): {summary['infra_errors']}")
    return "\n".join(lines)


def main() -> int:
    from backend.evaluation.aggregate import aggregate_runs

    if len(sys.argv) > 1:
        paths = [Path(p) for p in sys.argv[1:]]
    else:
        paths = sorted((PROJECT_ROOT / "evaluation" / "results").glob("evaluation_runs_*.json"))

    if not paths:
        print("No evaluation_runs_*.json files found under evaluation/results/. "
              "Run evaluation/run_evaluation.py first.")
        return 1

    print(f"Combining {len(paths)} file(s): {[p.name for p in paths]}")
    all_runs = _load_runs(paths)
    summary = aggregate_runs(all_runs)

    results_dir = PROJECT_ROOT / "evaluation" / "results"
    stamp = int(time.time())
    combined_runs_path = results_dir / f"evaluation_runs_combined_{stamp}.json"
    combined_summary_path = results_dir / f"evaluation_summary_combined_{stamp}.json"
    report_path = results_dir / f"evaluation_report_{stamp}.md"

    combined_runs_path.write_text(json.dumps(all_runs, indent=2))
    combined_summary_path.write_text(json.dumps(summary, indent=2))
    report = _render_report(all_runs, summary)
    report_path.write_text(report + "\n")

    print(f"\nWrote combined runs to {combined_runs_path.relative_to(PROJECT_ROOT)}")
    print(f"Wrote combined summary to {combined_summary_path.relative_to(PROJECT_ROOT)}")
    print(f"Wrote human-readable report to {report_path.relative_to(PROJECT_ROOT)}")
    print()
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
