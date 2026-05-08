"""Aggregate experiment results into a markdown report with mermaid charts.

Flow:
  1. Read plan.json (JSON array) for experiment metadata (server_config_id, dataset, concurrency)
  2. For each experiment, load its output_file bundle (produced by run_experiment.sh)
  3. Merge into results/all.jsonl (flat rows: meta + extracted metrics)
  4. Group by server_config_id → per-group table + mermaid charts
  5. Cross-config summary table at top

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

    bench_serving typically writes one aggregate line per run. Take the first
    object that contains throughput fields; fall back to empty.
    """
    if not isinstance(raw, list):
        return {k: None for k in METRIC_FIELDS}
    for obj in raw:
        if isinstance(obj, dict) and any(k in obj for k in ("request_throughput", "output_throughput")):
            return {k: obj.get(k) for k in METRIC_FIELDS}
    # Fallback: if there's exactly one dict, use it even without throughput keys.
    if len(raw) == 1 and isinstance(raw[0], dict):
        return {k: raw[0].get(k) for k in METRIC_FIELDS}
    return {k: None for k in METRIC_FIELDS}


def _load_plan(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or "experiment_list" not in data:
        raise ValueError(
            "plan file must be an object with 'experiment_list' (see plan_schema.json)"
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


def _mermaid_xychart(
    title: str, x_label: str, y_label: str, xs: list[Any], ys: list[float]
) -> str:
    xs_str = "[" + ", ".join(f'"{x}"' for x in xs) + "]"
    ys_str = "[" + ", ".join(f"{y:.2f}" if isinstance(y, (int, float)) else "0" for y in ys) + "]"
    return (
        "```mermaid\n"
        "xychart-beta\n"
        f'  title "{title}"\n'
        f"  x-axis {xs_str}\n"
        f'  y-axis "{y_label}"\n'
        f"  line {ys_str}\n"
        "```"
    )


def _render_group_section(sid: str, group_rows: list[dict[str, Any]]) -> str:
    headers = [
        "exp",
        "dataset",
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
    for r in sorted(group_rows, key=lambda x: x["experiment_id"]):
        table_rows.append([
            str(r["experiment_id"]),
            r["dataset"],
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

    # Mermaid: throughput vs concurrency (numeric conc only).
    conc_rows = [r for r in group_rows if isinstance(r.get("concurrency"), int) and r.get("output_throughput") is not None]
    conc_rows.sort(key=lambda x: x["concurrency"])
    charts = []
    if conc_rows:
        charts.append(
            _mermaid_xychart(
                f"output_throughput vs concurrency — {sid}",
                "concurrency",
                "output_tok/s",
                [r["concurrency"] for r in conc_rows],
                [r["output_throughput"] for r in conc_rows],
            )
        )
        charts.append(
            _mermaid_xychart(
                f"TTFT p99 vs concurrency — {sid}",
                "concurrency",
                "TTFT p99 (ms)",
                [r["concurrency"] for r in conc_rows],
                [r.get("p99_ttft_ms") or 0 for r in conc_rows],
            )
        )

    parts = [f"## server_config = `{sid}`", "", table, ""]
    if charts:
        parts.extend(charts)
        parts.append("")
    return "\n".join(parts)


def _render_cross_summary(rows: list[dict[str, Any]]) -> str:
    """Best-throughput-per-config summary at top."""
    buckets = _group_by([r for r in rows if r["status"] == "OK"], "server_config_id")
    summary_rows = []
    for sid, group in buckets.items():
        # Take the row with max output_throughput.
        best = max(
            (r for r in group if r.get("output_throughput") is not None),
            key=lambda r: r["output_throughput"],
            default=None,
        )
        if best is None:
            continue
        summary_rows.append([
            sid,
            best["dataset"],
            _fmt(best["concurrency"], 0),
            _fmt(best.get("request_throughput"), 2),
            _fmt(best.get("output_throughput"), 2),
            _fmt(best.get("median_ttft_ms"), 1),
            _fmt(best.get("p99_ttft_ms"), 1),
        ])
    summary_rows.sort(key=lambda r: float(r[4]) if r[4] != "-" else 0, reverse=True)
    headers = ["server_config", "best_dataset", "conc", "req/s", "out_tok/s", "TTFT p50", "TTFT p99"]
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
    sections.append("## Cross-config summary (best throughput per server config)")
    sections.append("")
    sections.append(_render_cross_summary(rows))
    sections.append("")

    for sid, group in _group_by(rows, "server_config_id").items():
        sections.append(_render_group_section(sid, group))

    Path(args.out).write_text("\n".join(sections))
    print(f"wrote {args.out} and {all_jsonl} ({len(rows)} experiments)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
