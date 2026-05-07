"""Generate benchmark plan from spec.yaml.

Two stages:

  --stage expand   : expand server.search_space per search.tier, write expanded.json
  --stage finalize : cross selected server configs × datasets (per-dataset cartesian
                     product) → plan.jsonl

expanded.json schema:
  [
    {"server_config_id": "base",    "flags": {...}},
    {"server_config_id": "cfg_001", "flags": {...}},
    ...
  ]

selected.json is a subset of expanded.json (same list-of-objects format).
When the expansion size is within max_candidates, selected.json == expanded.json.

Usage:
  python3 generate_plan.py --spec spec.yaml --stage expand --out expanded.json
  python3 generate_plan.py --spec spec.yaml --stage finalize \
      --selected selected.json --out plan.jsonl
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path
from typing import Any

import yaml


# ---------- Flag formatting ----------

def _key_to_flag(key: str) -> str:
    """foo_bar_baz -> --foo-bar-baz"""
    return "--" + key.replace("_", "-")


def _flag_kv_to_args(key: str, value: Any) -> list[str]:
    """Render a single (key, value) pair to CLI arg tokens.

    - bool True  -> ['--flag']
    - bool False -> []  (omitted)
    - scalar     -> ['--flag', str(value)]
    """
    flag = _key_to_flag(key)
    if isinstance(value, bool):
        return [flag] if value else []
    return [flag, str(value)]


def _build_serve_cmd(
    server_host: str,
    server_port: int,
    env: dict[str, Any] | None,
    flags: dict[str, Any],
) -> str:
    """Build the full SGLang launch_server command string."""
    env_prefix = ""
    if env:
        env_prefix = " ".join(f"{k}={v}" for k, v in env.items()) + " "

    args: list[str] = []
    for k, v in flags.items():
        args.extend(_flag_kv_to_args(k, v))
    args.extend(["--host", str(server_host), "--port", str(server_port)])

    return f"{env_prefix}python3 -m sglang.launch_server " + " ".join(args)


# ---------- Dataset kind registry ----------

DATASET_KIND_MAP: dict[str, dict[str, Any]] = {
    "random": {
        "dataset_name": "random",
        "fields": {
            "num_prompts": "--num-prompts",
            "input_len": "--random-input",
            "output_len": "--random-output",
            "request_rate": "--request-rate",
            "max_concurrency": "--max-concurrency",
        },
    },
    "generated_shared_prefix": {
        "dataset_name": "generated-shared-prefix",
        "fields": {
            "num_groups": "--gsp-num-groups",
            "prompts_per_group": "--gsp-prompts-per-group",
            "num_turns": "--gsp-num-turns",
            "system_prompt_len": "--gsp-system-prompt-len",
            "question_len": "--gsp-question-len",
            "output_len": "--gsp-output-len",
            "max_concurrency": "--max-concurrency",
        },
    },
}


def _expand_dataset(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand one dataset's list fields into cartesian product of concrete param dicts."""
    kind = dataset["kind"]
    if kind not in DATASET_KIND_MAP:
        raise ValueError(f"unknown dataset kind: {kind}")

    known_fields = set(DATASET_KIND_MAP[kind]["fields"].keys())
    # Only fields that appear in the spec and are known; user can omit fields to use
    # SGLang defaults.
    spec_fields = {k: v for k, v in dataset.items() if k != "kind" and k in known_fields}
    unknown = set(dataset.keys()) - {"kind"} - known_fields
    if unknown:
        raise ValueError(f"unknown fields for dataset kind={kind}: {unknown}")

    # Each field must be a list; scalar→single-element list for convenience.
    axes = {}
    for k, v in spec_fields.items():
        axes[k] = v if isinstance(v, list) else [v]

    keys = list(axes.keys())
    combos = []
    for values in itertools.product(*[axes[k] for k in keys]):
        combo = dict(zip(keys, values))
        combo["kind"] = kind
        combos.append(combo)
    return combos


def _build_bench_cmd(
    backend: str,
    tokenizer: str | None,
    model: str | None,
    dataset_combo: dict[str, Any],
    output_file_remote: str,
    extra_bench_flags: dict[str, Any] | None = None,
) -> str:
    """Build one bench_serving command string from a resolved dataset combo."""
    kind = dataset_combo["kind"]
    entry = DATASET_KIND_MAP[kind]
    args: list[str] = [
        "--backend", backend,
        "--dataset-name", entry["dataset_name"],
    ]
    if tokenizer:
        args.extend(["--tokenizer", tokenizer])
    if model:
        args.extend(["--model", model])

    for field_key, cli_flag in entry["fields"].items():
        if field_key not in dataset_combo:
            continue
        value = dataset_combo[field_key]
        if value is None:
            continue
        args.extend([cli_flag, str(value)])

    if extra_bench_flags:
        for k, v in extra_bench_flags.items():
            args.extend(_flag_kv_to_args(k, v))

    args.extend(["--output-file", output_file_remote])
    return "python3 -m sglang.bench_serving " + " ".join(args)


# ---------- Search space expansion ----------

def _validate_base_covers_search_space(
    base: dict[str, Any], search_space: dict[str, list[Any]]
) -> None:
    missing = set(search_space.keys()) - set(base.keys())
    if missing:
        raise ValueError(
            "server.base_flags must cover all server.search_space keys. "
            f"Missing: {sorted(missing)}"
        )


def _expand_server_configs(
    base: dict[str, Any],
    search_space: dict[str, list[Any]],
    tier: int,
) -> list[dict[str, Any]]:
    """Return list of {server_config_id, flags}.

    tier 1: [base]
    tier 2: base + per-axis variants (each axis swaps one value != base[axis])
    tier 3: full cartesian product over search_space; non-search keys inherit from base
    """
    if tier == 1:
        return [{"server_config_id": "base", "flags": dict(base)}]

    if tier == 2:
        _validate_base_covers_search_space(base, search_space)
        configs: list[dict[str, Any]] = [
            {"server_config_id": "base", "flags": dict(base)}
        ]
        idx = 1
        for axis, values in search_space.items():
            for v in values:
                if v == base[axis]:
                    continue
                flags = dict(base)
                flags[axis] = v
                configs.append(
                    {"server_config_id": f"cfg_{idx:03d}", "flags": flags}
                )
                idx += 1
        return configs

    if tier == 3:
        _validate_base_covers_search_space(base, search_space)
        keys = list(search_space.keys())
        configs = []
        idx = 0
        for values in itertools.product(*[search_space[k] for k in keys]):
            flags = dict(base)
            for k, v in zip(keys, values):
                flags[k] = v
            # Tag base combination explicitly.
            is_base = all(flags[k] == base[k] for k in keys)
            sid = "base" if is_base else f"cfg_{idx:03d}"
            configs.append({"server_config_id": sid, "flags": flags})
            idx += 1
        return configs

    raise ValueError(f"search.tier must be 1, 2 or 3; got {tier}")


# ---------- Stages ----------

def stage_expand(spec: dict[str, Any], out_path: Path) -> None:
    server = spec["server"]
    base = server["base_flags"]
    search_space = server.get("search_space", {})
    tier = int(spec.get("search", {}).get("tier", 1))

    configs = _expand_server_configs(base, search_space, tier)
    out_path.write_text(json.dumps(configs, indent=2, ensure_ascii=False))

    print(f"expanded {len(configs)} server configs (tier={tier}) -> {out_path}")
    max_cand = spec.get("search", {}).get("max_candidates")
    if max_cand is not None and len(configs) > max_cand:
        print(
            f"WARNING: {len(configs)} > max_candidates={max_cand}. "
            "Claude should select a subset before --stage finalize.",
            file=sys.stderr,
        )


def stage_finalize(spec: dict[str, Any], selected_path: Path, out_path: Path) -> None:
    selected = json.loads(selected_path.read_text())
    if not isinstance(selected, list) or not all(
        isinstance(s, dict) and "server_config_id" in s and "flags" in s
        for s in selected
    ):
        raise ValueError(
            "selected.json must be a list of {server_config_id, flags} objects "
            "(subset of expanded.json)."
        )

    server = spec["server"]
    bench = spec.get("benchmark", {})
    datasets_spec = spec.get("datasets", [])
    deploy_target = spec.get("deploy_target", "ec2")

    backend = bench.get("backend", "sglang")
    tokenizer = bench.get("tokenizer")
    model = bench.get("model")

    # Per-dataset combos.
    dataset_combos: list[dict[str, Any]] = []
    for d in datasets_spec:
        dataset_combos.extend(_expand_dataset(d))

    plan_lines: list[str] = []
    exp_id = 0
    for cfg in selected:
        serve_cmd = _build_serve_cmd(
            server_host=server.get("host", "127.0.0.1"),
            server_port=int(server.get("port", 30000)),
            env=server.get("env"),
            flags=cfg["flags"],
        )
        for dcombo in dataset_combos:
            remote_out = f"/tmp/sglang-bench-exp-{exp_id:04d}.jsonl"
            local_out = f"results/exp_{exp_id:04d}.json"
            bench_cmd = _build_bench_cmd(
                backend=backend,
                tokenizer=tokenizer,
                model=model,
                dataset_combo=dcombo,
                output_file_remote=remote_out,
            )
            row = {
                "experiment_id": exp_id,
                "serve_cmd": serve_cmd,
                "bench_cmd": bench_cmd,
                "dependencies": [],
                "deploy_target": deploy_target,
                "output_file": local_out,
                "meta": {
                    "server_config_id": cfg["server_config_id"],
                    "dataset": dcombo,
                    "concurrency": dcombo.get("max_concurrency"),
                },
            }
            plan_lines.append(json.dumps(row, ensure_ascii=False))
            exp_id += 1

    out_path.write_text("\n".join(plan_lines) + ("\n" if plan_lines else ""))
    print(
        f"finalized plan: {len(selected)} server configs × "
        f"{len(dataset_combos)} dataset combos = {exp_id} experiments -> {out_path}"
    )


# ---------- CLI ----------

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--spec", required=True, help="spec.yaml path")
    p.add_argument("--stage", required=True, choices=["expand", "finalize"])
    p.add_argument("--selected", help="selected.json (required for --stage finalize)")
    p.add_argument("--out", required=True, help="output path (expanded.json or plan.jsonl)")
    args = p.parse_args()

    spec = yaml.safe_load(Path(args.spec).read_text())
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if args.stage == "expand":
        stage_expand(spec, out_path)
    else:
        if not args.selected:
            p.error("--selected is required for --stage finalize")
        stage_finalize(spec, Path(args.selected), out_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
