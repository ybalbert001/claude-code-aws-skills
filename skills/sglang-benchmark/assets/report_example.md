# SGLang Benchmark Report

## server_config list

| server_config_id | {search_space_dim_1} | {search_space_dim_2} | {reqsearch_space_dim_3} | ... |
|---|---|---|---|---|
| Base             | flashinfer           | 128                  | 0.9                     |      |
| 1                | flashinfer           | 128                  | 0.85                    | ...  |
| 2 | Fa3 | 128 | 0.9 | ... |

## dataset = `random/random-input=1024/random-output=128`

| exp | server_config_id | conc | status | req/s | out_tok/s | TTFT p50 (ms) | TTFT p99 (ms) | ITL p50 (ms) | ITL p99 (ms) |
|---|---|---|---|---|---|---|---|---|---|
| 0 | base | 16 | OK | 17.64 | 1110.80 | 39.2 | 332.0 | 10.3 | 40.5 |
| 1 | 1 | 16 | OK | 17.63 | 1110.39 | 37.3 | 351.4 | 10.4 | 41.7 |
| 2 | 2 | 16 | MISSING | - | - | - | - | - | - |
| 3    | Base             | 64   | OK      | 22.42 | 1412.23   | 72.9          | 1138.1        | 23.7         | 144.8        |
| 4    | 1                | 64   | OK      | 24.24 | 1526.85   | 69.3          | 1046.8        | 23.8         | 109.3        |
| 5    | 2                | 64   | OK      | 24.33 | 1532.51   | 67.6          | 1020.0        | 23.9         | 108.5        |
| 6    | ..               | ..   | ..      | ..    | ..        | ..            | ..            | ..           | ..           |

## dataset = `generated_shared_prefix/gsp-num-groups=100/gsp-prompts-per-group=2/gsp-num-turns=10/gsp-system-prompt-len=1024/gsp-question-len=256/gsp-output-len=128`

| exp | server_config | conc | status | req/s | out_tok/s | TTFT p50 (ms) | TTFT p99 (ms) | ITL p50 (ms) | ITL p99 (ms) |
|---|---|---|---|---|---|---|---|---|---|
| 7    | base          | 16   | OK      | 17.64 | 1110.80   | 39.2          | 332.0         | 10.3         | 40.5         |
| 8    | 1             | 16   | OK      | 17.63 | 1110.39   | 37.3          | 351.4         | 10.4         | 41.7         |
| 9    | 2             | 16   | MISSING | -     | -         | -             | -             | -            | -            |
| 10   | Base          | 64   | OK      | 22.42 | 1412.23   | 72.9          | 1138.1        | 23.7         | 144.8        |
| 11   | 1             | 64   | OK      | 24.24 | 1526.85   | 69.3          | 1046.8        | 23.8         | 109.3        |
| 12   | 2             | 64   | OK      | 24.33 | 1532.51   | 67.6          | 1020.0        | 23.9         | 108.5        |
| 13   | ..            | ..   | ..      | ..    | ..        | ..            | ..            | ..           | ..           |
