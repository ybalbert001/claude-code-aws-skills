"""Generate benchmark plan.json from spec.yaml.

Single-stage pipeline:

  1. Expand `server.search_space` per `search.tier`.
  2. If expansion > `search.max_candidates`, prune using `search.priority_axes`
     (base is always kept).
  3. Cross selected server configs with all dataset combos (per-dataset cartesian
     product) to produce experiment rows.
  4. Chain `dependencies` so experiments sharing a `server_config_id` form a chain
     (exp_i depends on the previous exp with the same server_config_id). This
     expresses intent for future "same-server reuse" scheduling; the default runner
     still restarts per experiment.

Output is a top-level envelope:
  {
    "dependencies": [[], [0], ...],   # dependencies[i] = prereqs of experiment_list[i]
    "experiment_list": [{experiment_id, serve_cmd, bench_cmd, output_file, meta}, ...]
  }

Usage:
  python3 generate_plan.py --spec spec.yaml --out plan.json
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
    spec_fields = {k: v for k, v in dataset.items() if k != "kind" and k in known_fields}
    unknown = set(dataset.keys()) - {"kind"} - known_fields
    if unknown:
        raise ValueError(f"unknown fields for dataset kind={kind}: {unknown}")

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


# ---------- Server config expansion + selection ----------

DEFAULT_PRIORITY_AXES = [
    "prefill_attention_backend",
    "decode_attention_backend",
    "attention_backend",
    "chunked_prefill_size",
    "max_running_requests",
    "mem_fraction_static",
    "tp_size",
]


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
            is_base = all(flags[k] == base[k] for k in keys)
            sid = "base" if is_base else f"cfg_{idx:03d}"
            configs.append({"server_config_id": sid, "flags": flags})
            idx += 1
        return configs

    raise ValueError(f"search.tier must be 1, 2 or 3; got {tier}")


def _diff_axes(cfg: dict[str, Any], base: dict[str, Any]) -> list[str]:
    """Return axes where cfg differs from base."""
    return [k for k in cfg if k in base and cfg[k] != base[k]]


def _select_configs(
    configs: list[dict[str, Any]],
    base: dict[str, Any],
    max_candidates: int | None,
    priority_axes: list[str],
) -> list[dict[str, Any]]:
    """Prune configs to at most max_candidates while keeping base and prioritizing
    variants that exercise `priority_axes`.

    Strategy:
      1. Base is always kept.
      2. Score each non-base config by (−priority hits, #total axes touched,
         priority index of first touched axis). Lower = higher priority.
      3. Sort by score; take the top (max_candidates − 1).
    """
    if max_candidates is None or len(configs) <= max_candidates:
        return configs

    base_cfg = next((c for c in configs if c["server_config_id"] == "base"), None)
    non_base = [c for c in configs if c["server_config_id"] != "base"]

    priority_rank = {axis: i for i, axis in enumerate(priority_axes)}

    def score(c: dict[str, Any]) -> tuple[int, int, int]:
        touched = _diff_axes(c["flags"], base)
        priority_hits = sum(1 for a in touched if a in priority_rank)
        first_priority_idx = min(
            (priority_rank[a] for a in touched if a in priority_rank),
            default=len(priority_axes),
        )
        return (-priority_hits, len(touched), first_priority_idx)

    non_base.sort(key=score)
    keep_n = max_candidates - (1 if base_cfg else 0)
    return ([base_cfg] if base_cfg else []) + non_base[:keep_n]


# ---------- Plan assembly ----------

def _build_dependency_chain(rows: list[dict[str, Any]]) -> list[list[int]]:
    """Return a positional dependencies list: deps[i] = prereqs for rows[i],
    chaining experiments that share a server_config_id."""
    last_by_cfg: dict[str, int] = {}
    deps: list[list[int]] = []
    for row in rows:
        cfg_id = row["meta"]["server_config_id"]
        prev = last_by_cfg.get(cfg_id)
        deps.append([prev] if prev is not None else [])
        last_by_cfg[cfg_id] = row["experiment_id"]
    return deps


def build_plan(spec: dict[str, Any]) -> dict[str, Any]:
    server = spec["server"]
    base = server["base_flags"]
    search_space = server.get("search_space", {})
    search = spec.get("search", {})
    tier = int(search.get("tier", 1))
    max_candidates = search.get("max_candidates")
    priority_axes = search.get("priority_axes") or DEFAULT_PRIORITY_AXES

    bench = spec.get("benchmark", {})
    datasets_spec = spec.get("datasets", [])

    backend = bench.get("backend", "sglang")
    tokenizer = bench.get("tokenizer")
    model = bench.get("model")

    expanded = _expand_server_configs(base, search_space, tier)
    selected = _select_configs(expanded, base, max_candidates, priority_axes)

    print(
        f"[plan] tier={tier} expanded={len(expanded)} "
        f"selected={len(selected)} max_candidates={max_candidates}",
        file=sys.stderr,
    )

    dataset_combos: list[dict[str, Any]] = []
    for d in datasets_spec:
        dataset_combos.extend(_expand_dataset(d))

    rows: list[dict[str, Any]] = []
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
            rows.append({
                "experiment_id": exp_id,
                "serve_cmd": serve_cmd,
                "bench_cmd": bench_cmd,
                "output_file": local_out,
                "meta": {
                    "server_config_id": cfg["server_config_id"],
                    "concurrency": dcombo.get("max_concurrency"),
                    "dataset_kind": dcombo.get("kind"),
                },
            })
            exp_id += 1

    deps = _build_dependency_chain(rows)
    return {
        "dependencies": deps,
        "experiment_list": rows,
    }


# ---------- CLI ----------

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--spec", required=True, help="spec.yaml path")
    p.add_argument("--out", required=True, help="output plan.json path")
    args = p.parse_args()

    spec = yaml.safe_load(Path(args.spec).read_text())
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = build_plan(spec)
    out_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} experiments -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
