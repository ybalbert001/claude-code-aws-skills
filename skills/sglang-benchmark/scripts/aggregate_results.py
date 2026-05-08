"""Aggregate experiment results into a markdown report.

Flow:
  1. Read plan.json (JSON array) for experiment metadata (server_config_id, dataset, concurrency)
  2. For each experiment, load its output_file bundle (produced by run_experiment.sh)
  3. Merge into results/all.jsonl (flat rows: meta + extracted metrics)
  4. Group by dataset (workload) → per-workload table (server_config × concurrency)
  5. Cross-workload summary table at top (best server_config per workload)

Usage:
  python3 aggregate_results.py --plan plan.json --results-dir results/ --out report.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


# Fields we try to pull from bench_serving's output summary.
# bench_serving writes a single JSON object (one line in jsonl mode) with these keys.
METRIC_FIELDS = [
    "completed",
    "total_input_tokens",
    "total_output_tokens",
    "request_throughput",
    "input_throughput",
    "output_throughput",
    "mean_ttft_ms",
    "median_ttft_ms",
    "p99_ttft_ms",
    "mean_tpot_ms",
    "median_tpot_ms",
    "p99_tpot_ms",
    "mean_itl_ms",
    "median_itl_ms",
    "p99_itl_ms",
]


def _extract_metrics(raw: Any) -> dict[str, Any]:
    """From the bundle's 'raw' field (list of jsonl objects), pull the summary.

    bench_serving appends a summary line per run; if the remote output file was
    not cleared between runs, multiple lines accumulate. Take the LAST object
    with throughput fields (freshest run wins). Fallback: single-dict raw.
    """
    if not isinstance(raw, list):
        return {k: None for k in METRIC_FIELDS}
    for obj in reversed(raw):
        if isinstance(obj, dict) and any(k in obj for k in ("request_throughput", "output_throughput")):
            return {k: obj.get(k) for k in METRIC_FIELDS}
    if len(raw) == 1 and isinstance(raw[0], dict):
        return {k: raw[0].get(k) for k in METRIC_FIELDS}
    return {k: None for k in METRIC_FIELDS}


def _load_plan(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or "experiment_list" not in data:
        raise ValueError(
            "plan file must be an object with 'experiment_list' (see assets/plan_schema.json)"
        )
    return data["experiment_list"]


_BENCH_FLAG_LABELS = {
    "random": ["--random-input", "--random-output", "--request-rate"],
    "generated-shared-prefix": [
        "--gsp-num-groups", "--gsp-prompts-per-group", "--gsp-num-turns",
        "--gsp-system-prompt-len", "--gsp-question-len", "--gsp-output-len",
    ],
}


def _parse_bench_flags(cmd: str, flags: list[str]) -> dict[str, str]:
    """Extract --flag VALUE pairs from bench_cmd for dataset labeling."""
    tokens = cmd.split()
    out = {}
    for i, tok in enumerate(tokens):
        if tok in flags and i + 1 < len(tokens):
            out[tok.lstrip("-")] = tokens[i + 1]
    return out


def _dataset_label(bench_cmd: str, kind: str) -> str:
    dataset_name = "generated-shared-prefix" if kind == "generated_shared_prefix" else kind
    flags = _BENCH_FLAG_LABELS.get(dataset_name, [])
    kv = _parse_bench_flags(bench_cmd, flags)
    if not kv:
        return kind
    body = "/".join(f"{k}={v}" for k, v in kv.items())
    return f"{kind}/{body}"


def _fmt(v: Any, digits: int = 2) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def _build_flat_rows(
    plan: list[dict[str, Any]], results_dir: Path
) -> list[dict[str, Any]]:
    out = []
    for p in plan:
        eid = p["experiment_id"]
        bundle_path = results_dir / Path(p["output_file"]).name
        meta = p.get("meta", {})
        dataset = _dataset_label(p.get("bench_cmd", ""), meta.get("dataset_kind", "?"))

        base_row = {
            "experiment_id": eid,
            "server_config_id": meta.get("server_config_id", "?"),
            "concurrency": meta.get("concurrency"),
            "dataset": dataset,
        }

        if not bundle_path.exists():
            row = {**base_row, "status": "MISSING"}
            row.update({k: None for k in METRIC_FIELDS})
        else:
            bundle = json.loads(bundle_path.read_text())
            metrics = _extract_metrics(bundle.get("raw"))
            row = {**base_row, "status": "OK"}
            row.update(metrics)
        out.append(row)
    return out


def _group_by(rows: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        buckets.setdefault(r[key], []).append(r)
    return buckets


def _render_md_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(["---"] * len(headers)) + "|",
    ]
    for r in rows:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def _render_group_section(dataset: str, group_rows: list[dict[str, Any]]) -> str:
    headers = [
        "exp",
        "server_config",
        "conc",
        "status",
        "req/s",
        "out_tok/s",
        "TTFT p50 (ms)",
        "TTFT p99 (ms)",
        "ITL p50 (ms)",
        "ITL p99 (ms)",
    ]
    table_rows = []
    for r in sorted(group_rows, key=lambda x: (x.get("concurrency") or 0, x.get("server_config_id") or "", x["experiment_id"])):
        table_rows.append([
            str(r["experiment_id"]),
            str(r.get("server_config_id", "?")),
            _fmt(r["concurrency"], 0),
            r["status"],
            _fmt(r.get("request_throughput"), 2),
            _fmt(r.get("output_throughput"), 2),
            _fmt(r.get("median_ttft_ms"), 1),
            _fmt(r.get("p99_ttft_ms"), 1),
            _fmt(r.get("median_itl_ms"), 1),
            _fmt(r.get("p99_itl_ms"), 1),
        ])
    table = _render_md_table(headers, table_rows)
    return "\n".join([f"## dataset = `{dataset}`", "", table, ""])


def _render_cross_summary(rows: list[dict[str, Any]]) -> str:
    """Best server_config per dataset (workload) at top."""
    buckets = _group_by([r for r in rows if r["status"] == "OK"], "dataset")
    summary_rows = []
    for dataset, group in buckets.items():
        best = max(
            (r for r in group if r.get("output_throughput") is not None),
            key=lambda r: r["output_throughput"],
            default=None,
        )
        if best is None:
            continue
        summary_rows.append([
            dataset,
            str(best.get("server_config_id", "?")),
            _fmt(best["concurrency"], 0),
            _fmt(best.get("request_throughput"), 2),
            _fmt(best.get("output_throughput"), 2),
            _fmt(best.get("median_ttft_ms"), 1),
            _fmt(best.get("p99_ttft_ms"), 1),
        ])
    summary_rows.sort(key=lambda r: float(r[4]) if r[4] != "-" else 0, reverse=True)
    headers = ["dataset", "best_server_config", "conc", "req/s", "out_tok/s", "TTFT p50", "TTFT p99"]
    return _render_md_table(headers, summary_rows)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--plan", required=True)
    p.add_argument("--results-dir", default="results")
    p.add_argument("--out", default="report.md")
    args = p.parse_args()

    plan = _load_plan(Path(args.plan))
    results_dir = Path(args.results_dir)
    rows = _build_flat_rows(plan, results_dir)

    # Write flat all.jsonl.
    all_jsonl = results_dir / "all.jsonl"
    all_jsonl.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")

    # Build report.md.
    sections = ["# SGLang Benchmark Report", ""]
    sections.append("## Cross-workload summary (best server_config per dataset)")
    sections.append("")
    sections.append(_render_cross_summary(rows))
    sections.append("")

    for dataset, group in _group_by(rows, "dataset").items():
        sections.append(_render_group_section(dataset, group))

    Path(args.out).write_text("\n".join(sections))
    print(f"wrote {args.out} and {all_jsonl} ({len(rows)} experiments)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
