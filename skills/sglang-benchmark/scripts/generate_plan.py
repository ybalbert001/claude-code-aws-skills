"""Generate benchmark plan.json from spec.yaml.

Single-stage pipeline:

  1. Expand `server.search_space` per `search.tier`.
  2. If expansion > `search.max_candidates`, prune using `search.priority_axes`
     (base is always kept).
  3. Cross selected server configs with all dataset combos (per-dataset cartesian
     product) to produce experiment rows. Outer loop is dataset: finish all
     server_configs for one dataset before moving to the next.

Output is a top-level envelope:
  {
    "experiment_list": [{experiment_id, serve_cmd, bench_cmd, output_file, meta}, ...]
  }

Experiments are independent (each restarts the server), so the runner iterates
experiment_list in order.

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


def _render_flags(flags: dict[str, Any]) -> str:
    """Render a flags dict as a space-separated CLI args string (no --host/--port)."""
    args: list[str] = []
    for k, v in flags.items():
        args.extend(_flag_kv_to_args(k, v))
    return " ".join(args)


def _build_serve_cmd(
    server_host: str,
    server_port: int,
    env: dict[str, Any] | None,
    flags: dict[str, Any],
) -> str:
    """Build the full SGLang launch_server command string (python direct mode)."""
    env_prefix = ""
    if env:
        env_prefix = " ".join(f"{k}={v}" for k, v in env.items()) + " "

    body = _render_flags(flags)
    return (
        f"{env_prefix}python3 -m sglang.launch_server {body} "
        f"--host {server_host} --port {server_port}"
    )


def _render_serve_cmd_template(
    template: str,
    flags: dict[str, Any],
    host: str,
    port: int,
) -> str:
    """Substitute {flags} / {host} / {port} placeholders in a serve_cmd template.

    Supports custom launchers (docker / srun / etc.) while still sweeping
    server-side flags. {flags} is required for sweep mode; if absent the caller
    treats the string as raw (tier=1 only).
    """
    return (
        template.replace("{flags}", _render_flags(flags))
        .replace("{host}", str(host))
        .replace("{port}", str(port))
    )


# ---------- Dataset kind registry ----------

DATASET_KIND_MAP: dict[str, str] = {
    "random": "random",
    "generated_shared_prefix": "generated-shared-prefix",
}


def _expand_dataset(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand one dataset's list fields into cartesian product of concrete param dicts."""
    kind = dataset["kind"]
    if kind not in DATASET_KIND_MAP:
        raise ValueError(f"unknown dataset kind: {kind}")

    axes = {}
    for k, v in dataset.items():
        if k == "kind":
            continue
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
    dataset_name = DATASET_KIND_MAP[kind]
    args: list[str] = [
        "--backend", backend,
        "--dataset-name", dataset_name,
    ]
    if tokenizer:
        args.extend(["--tokenizer", tokenizer])
    if model:
        args.extend(["--model", model])

    for k, v in dataset_combo.items():
        if k == "kind" or v is None:
            continue
        args.extend([_key_to_flag(k), str(v)])

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

def build_plan(spec: dict[str, Any]) -> dict[str, Any]:
    server = spec["server"]
    raw_serve_cmd = server.get("serve_cmd")
    base = server.get("base_flags", {})
    search_space = server.get("search_space", {})
    search = spec.get("search", {})
    tier = int(search.get("tier", 1))
    max_candidates = search.get("max_candidates")
    priority_axes = search.get("priority_axes") or DEFAULT_PRIORITY_AXES

    bench = spec.get("benchmark", {})
    datasets_spec = spec.get("datasets", [])
    cleanup_cmd = server.get("cleanup_cmd")

    # serve_cmd modes:
    #   - Absent: build from base_flags + search_space (python direct launch).
    #   - Template (contains "{flags}"): custom launcher with sweep support.
    #     base_flags/search_space/tier still apply; flags get substituted in.
    #   - Raw (no "{flags}"): fixed server config, tier forced to 1.
    template_mode = bool(raw_serve_cmd) and "{flags}" in raw_serve_cmd
    raw_mode = bool(raw_serve_cmd) and not template_mode

    if raw_mode:
        if tier != 1:
            raise ValueError(
                "server.serve_cmd is raw (no {flags} placeholder); server-side search "
                "is unsupported. Set search.tier=1, or add {flags} to serve_cmd to enable sweeps."
            )
        if search_space:
            print(
                "[plan] warning: server.search_space ignored (raw serve_cmd without {flags})",
                file=sys.stderr,
            )

    backend = bench.get("backend", "sglang")
    tokenizer = bench.get("tokenizer")
    model = bench.get("model")

    if raw_mode:
        selected = [{"server_config_id": "base", "flags": {}}]
        print(f"[plan] raw serve_cmd mode (tier=1, 1 config)", file=sys.stderr)
    else:
        if not base:
            raise ValueError(
                "server.base_flags is required unless server.serve_cmd is raw (no {flags})"
            )
        expanded = _expand_server_configs(base, search_space, tier)
        selected = _select_configs(expanded, base, max_candidates, priority_axes)
        mode_label = "template serve_cmd" if template_mode else "native"
        print(
            f"[plan] {mode_label} tier={tier} expanded={len(expanded)} "
            f"selected={len(selected)} max_candidates={max_candidates}",
            file=sys.stderr,
        )

    dataset_combos: list[dict[str, Any]] = []
    for d in datasets_spec:
        dataset_combos.extend(_expand_dataset(d))

    # Outer loop = dataset (per SKILL.md: finish all server_configs for one
    # dataset before moving to the next). Inner loop = server_config.
    rows: list[dict[str, Any]] = []
    exp_id = 0
    host = server.get("host", "127.0.0.1")
    port = int(server.get("port", 30000))
    if raw_mode:
        serve_cmd_cache: dict[str, str] = {"base": raw_serve_cmd}
    elif template_mode:
        serve_cmd_cache = {
            cfg["server_config_id"]: _render_serve_cmd_template(
                raw_serve_cmd, cfg["flags"], host, port
            )
            for cfg in selected
        }
    else:
        serve_cmd_cache = {
            cfg["server_config_id"]: _build_serve_cmd(
                server_host=host,
                server_port=port,
                env=server.get("env"),
                flags=cfg["flags"],
            )
            for cfg in selected
        }
    for dcombo in dataset_combos:
        for cfg in selected:
            serve_cmd = serve_cmd_cache[cfg["server_config_id"]]
            remote_out = f"/tmp/sglang-bench-exp-{exp_id:04d}.jsonl"
            local_out = f"results/exp_{exp_id:04d}.json"
            bench_cmd = _build_bench_cmd(
                backend=backend,
                tokenizer=tokenizer,
                model=model,
                dataset_combo=dcombo,
                output_file_remote=remote_out,
            )
            row: dict[str, Any] = {
                "experiment_id": exp_id,
                "serve_cmd": serve_cmd,
                "bench_cmd": bench_cmd,
                "output_file": local_out,
                "meta": {
                    "server_config_id": cfg["server_config_id"],
                    "concurrency": dcombo.get("max_concurrency"),
                    "dataset_kind": dcombo.get("kind"),
                },
            }
            if cleanup_cmd:
                row["cleanup_cmd"] = cleanup_cmd
            rows.append(row)
            exp_id += 1

    # Top-level metadata for report rendering:
    #   - search_space_axes: ordered list of axes varied across configs
    #   - server_configs: each config's (id, flags) so the report can show a
    #     server_config table keyed by search_space axes.
    search_space_axes = list(search_space.keys()) if not raw_mode else []
    server_configs_meta = [
        {"server_config_id": cfg["server_config_id"], "flags": dict(cfg["flags"])}
        for cfg in selected
    ]

    return {
        "search_space_axes": search_space_axes,
        "server_configs": server_configs_meta,
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

    plan = build_plan(spec)
    out_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {len(plan['experiment_list'])} experiments -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
