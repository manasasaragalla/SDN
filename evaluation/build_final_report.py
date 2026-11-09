"""Builds the final Phase 14 research-results package from the
evaluation output files already on disk under evaluation/results/ --
this script does NO new Mininet/Ryu/root work and takes no new
measurements; it only reads, separates, tabulates, and plots data that
was already collected in prior sessions.

Reads two distinct kinds of existing output:

  1. evaluation_runs_*.json (excluding *_combined_*.json, which is a
     derived file from a previous evaluation/summarize.py run and would
     double-count rows if included) -- the Phase 13 systematic,
     repeated ONE_SHOT vs CLOSED_LOOP sweep. Each row is one
     EvaluationRun record (backend/models/evaluation.py); a row with
     pipeline=None is an infrastructure-error run (never a measured
     result) and is kept separate from every statistic.

  2. run_*.json -- individual backend/cli.py demo invocations
     (ExperimentLog records, backend/models/experiment_log.py). These
     are the Phase 11/12 manual capability demonstrations (the
     hand-picked runs documented in docs/experiments.md's Phase 12
     section, including the run that first surfaced the decision-policy
     bug) plus incidental regression-check runs made while building
     Phase 13. Kept entirely separate from the systematic sweep -- these
     were not repeated for statistical confidence, they were chosen by
     hand to demonstrate specific real behaviors.

Writes everything under evaluation/results/final/:
  - systematic_runs.csv / .json      (valid, non-infra-error sweep rows)
  - infra_error_runs.csv / .json     (excluded sweep rows, kept for the record)
  - manual_demo_runs.csv / .json     (Phase 11/12 CLI demo runs)
  - comparison_tables.json           (per-scenario ONE_SHOT vs CLOSED_LOOP, from
                                       backend/evaluation/aggregate.aggregate_runs)
  - satisfaction_rate_by_scenario_mode.png
  - throughput_vs_target.png
  - correction_iterations.png

Usage:
    PYTHONPATH=. python3 evaluation/build_final_report.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

RESULTS_DIR = PROJECT_ROOT / "evaluation" / "results"
OUT_DIR = RESULTS_DIR / "final"


def load_systematic_runs() -> tuple[list[dict], list[dict]]:
    """Returns (valid_runs, infra_error_runs) from every
    evaluation_runs_*.json file, excluding any *_combined_*.json
    (a derived file, would double-count)."""
    valid: list[dict] = []
    errors: list[dict] = []
    seen_source_files = []
    for path in sorted(RESULTS_DIR.glob("evaluation_runs_*.json")):
        if "combined" in path.name:
            continue
        seen_source_files.append(path.name)
        rows = json.loads(path.read_text())
        for row in rows:
            row = dict(row)
            row["_source_file"] = path.name
            if row.get("pipeline") is None:
                errors.append(row)
            else:
                valid.append(row)
    print(f"Loaded {len(seen_source_files)} systematic-sweep source file(s): {seen_source_files}")
    return valid, errors


def load_manual_demo_runs() -> list[dict]:
    """Returns every run_*.json (backend/cli.py ExperimentLog demo
    invocation), sorted by timestamp."""
    runs = []
    for path in sorted(RESULTS_DIR.glob("run_*.json")):
        row = json.loads(path.read_text())
        row["_source_file"] = path.name
        runs.append(row)
    runs.sort(key=lambda r: r.get("timestamp", ""))
    return runs


def _flatten_systematic_row(row: dict) -> dict:
    p = row["pipeline"]
    return {
        "source_file": row["_source_file"],
        "scenario": row["scenario"],
        "mode": p["mode"],
        "repetition": row["repetition"],
        "timestamp": row["timestamp"],
        "target_mbps": p["target_mbps"],
        "selected_path": " -> ".join(p["selected_path"]),
        "initial_throughput_mbps": p["initial_throughput_mbps"],
        "initial_satisfied": p["initial_satisfied"],
        "correction_iterations": p["correction_iterations"],
        "final_throughput_mbps": p["final_throughput_mbps"],
        "final_satisfied": p["final_satisfied"],
        "final_validation_valid": p["final_validation_valid"],
        "final_deployment_success": p["final_deployment_success"],
        "execution_time_s": p["execution_time_s"],
        "failure_reason": p["failure_reason"],
        "background_rate_changes_mbps": ";".join(f"{r:.3f}" for r in p["background_rate_changes_mbps"]),
    }


def _flatten_infra_error_row(row: dict) -> dict:
    return {
        "source_file": row["_source_file"],
        "scenario": row["scenario"],
        "repetition": row["repetition"],
        "timestamp": row["timestamp"],
        "error": row["error"],
    }


def _flatten_manual_row(row: dict) -> dict:
    intent = row["structured_intent"]
    return {
        "source_file": row["_source_file"],
        "timestamp": row["timestamp"],
        "objective": intent["objective"],
        "raw_intent": row["raw_intent"],
        "target_mbps": row.get("target_mbps"),
        "selected_path": " -> ".join(row["selected_path"]),
        "correction_iterations": row.get("correction_iterations", 0),
        "measured_mbps": row.get("measured_mbps"),
        "intent_satisfied": row["intent_satisfied"],
        "satisfaction_reason": row["satisfaction_reason"],
    }


def _write_csv_and_json(rows: list[dict], out_stem: Path) -> None:
    out_stem.parent.mkdir(parents=True, exist_ok=True)
    out_stem.with_suffix(".json").write_text(json.dumps(rows, indent=2))
    if rows:
        with out_stem.with_suffix(".csv").open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    else:
        out_stem.with_suffix(".csv").write_text("")


def build_plots(valid_runs: list[dict], summary: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    scenarios = sorted({r["scenario"] for r in valid_runs})
    modes = ["ONE_SHOT", "CLOSED_LOOP"]

    # --- Plot 1: satisfaction rate by scenario and mode ---
    fig, ax = plt.subplots(figsize=(8, 5))
    x = range(len(scenarios))
    width = 0.35
    for i, mode in enumerate(modes):
        rates = []
        for scenario in scenarios:
            key = f"{scenario}|{mode}"
            group = summary["groups"].get(key)
            rates.append(group["final_satisfaction_rate"] * 100 if group else 0)
        offset = (i - 0.5) * width
        bars = ax.bar([xi + offset for xi in x], rates, width, label=mode)
        for bar, scenario in zip(bars, scenarios):
            key = f"{scenario}|{mode}"
            group = summary["groups"].get(key)
            n = group["n_runs"] if group else 0
            ax.annotate(f"n={n}", (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                        ha="center", va="bottom", fontsize=8)
    ax.set_xticks(list(x))
    ax.set_xticklabels(scenarios)
    ax.set_ylabel("Final satisfaction rate (%)")
    ax.set_ylim(0, 110)
    ax.set_title("MIN_BANDWIDTH final satisfaction rate by scenario and mode\n(real measured runs only; infra errors excluded)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT_DIR / "satisfaction_rate_by_scenario_mode.png", dpi=150)
    plt.close(fig)

    # --- Plot 2: throughput vs target ---
    fig, ax = plt.subplots(figsize=(8, 5))
    colors = {"ONE_SHOT": "#4C72B0", "CLOSED_LOOP": "#DD8452"}
    for mode in modes:
        xs = [r["pipeline"]["target_mbps"] for r in valid_runs if r["pipeline"]["mode"] == mode]
        ys = [r["pipeline"]["final_throughput_mbps"] for r in valid_runs if r["pipeline"]["mode"] == mode]
        ax.scatter(xs, ys, label=mode, color=colors[mode], alpha=0.7)
    lims = [0, max(max(r["pipeline"]["target_mbps"] for r in valid_runs),
                   max(r["pipeline"]["final_throughput_mbps"] or 0 for r in valid_runs)) * 1.05]
    ax.plot(lims, lims, linestyle="--", color="gray", linewidth=1, label="target = achieved")
    ax.set_xlabel("Target bandwidth (Mbps)")
    ax.set_ylabel("Final measured throughput (Mbps, real iperf3)")
    ax.set_title("Final measured throughput vs requested target\n(points above the dashed line meet the target)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT_DIR / "throughput_vs_target.png", dpi=150)
    plt.close(fig)

    # --- Plot 3: correction iterations distribution (CLOSED_LOOP only) ---
    fig, ax = plt.subplots(figsize=(8, 5))
    closed_loop_runs = [r for r in valid_runs if r["pipeline"]["mode"] == "CLOSED_LOOP"]
    by_scenario: dict[str, list[int]] = {s: [] for s in scenarios}
    for r in closed_loop_runs:
        by_scenario[r["scenario"]].append(r["pipeline"]["correction_iterations"])
    scenario_labels = [s for s in scenarios if by_scenario[s]]
    means = [sum(by_scenario[s]) / len(by_scenario[s]) for s in scenario_labels]
    bars = ax.bar(scenario_labels, means, color="#55A868")
    for bar, s in zip(bars, scenario_labels):
        ax.annotate(f"n={len(by_scenario[s])}", (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                    ha="center", va="bottom", fontsize=8)
    ax.set_ylabel("Mean correction iterations (CLOSED_LOOP runs)")
    ax.set_title("Mean real correction iterations by scenario\n(0 = first measurement already satisfied target)")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "correction_iterations.png", dpi=150)
    plt.close(fig)

    print(f"Wrote 3 plots to {OUT_DIR.relative_to(PROJECT_ROOT)}/")


def main() -> int:
    from backend.evaluation.aggregate import aggregate_runs

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    valid_runs, infra_error_runs = load_systematic_runs()
    manual_runs = load_manual_demo_runs()

    print(f"Systematic sweep: {len(valid_runs)} valid run(s), {len(infra_error_runs)} infra-error run(s)")
    print(f"Manual CLI demo runs: {len(manual_runs)}")

    all_systematic = valid_runs + infra_error_runs
    summary = aggregate_runs(all_systematic)

    _write_csv_and_json([_flatten_systematic_row(r) for r in valid_runs], OUT_DIR / "systematic_runs")
    _write_csv_and_json([_flatten_infra_error_row(r) for r in infra_error_runs], OUT_DIR / "infra_error_runs")
    _write_csv_and_json([_flatten_manual_row(r) for r in manual_runs], OUT_DIR / "manual_demo_runs")
    (OUT_DIR / "comparison_tables.json").write_text(json.dumps(summary, indent=2))
    print(f"Wrote systematic_runs.{{csv,json}}, infra_error_runs.{{csv,json}}, "
          f"manual_demo_runs.{{csv,json}}, comparison_tables.json to {OUT_DIR.relative_to(PROJECT_ROOT)}/")

    build_plots(valid_runs, summary)

    return 0


if __name__ == "__main__":
    sys.exit(main())
