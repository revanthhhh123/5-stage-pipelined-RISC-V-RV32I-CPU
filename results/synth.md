# Synthesis summary (Yosys, generic gates, no technology library)

| Configuration | Total cells | Flip-flops | Comb. gates | ~Gate equivalents | Logic depth (gate levels) |
|---|---:|---:|---:|---:|---:|
| Core + BTB/BHT predictor (default) | 13565 | 3654 | 9911 | 44438 | 89 |
| Core, static not-taken (no predictor) | 7123 | 1731 | 5392 | 23030 | 78 |

Predictor cost: **+1923 flip-flops, +21408 GE (93%)**.

Cell-type breakdown (default configuration):

| Cell | Count |
|---|---:|
| `$_MUX_` | 4495 |
| `$_DFFE_PP_` | 2848 |
| `$_NAND_` | 2332 |
| `$_AND_` | 1904 |
| `$_SDFF_PP0_` | 378 |
| `$_XOR_` | 362 |
| `$_OR_` | 355 |
| `$_SDFFE_PP0P_` | 259 |
| `$_NOT_` | 173 |
| `$_XNOR_` | 156 |
| `$_SDFFE_PP0N_` | 155 |
| `$_NOR_` | 134 |
| `$_DFF_P_` | 11 |
| `$_SDFFE_PP1N_` | 3 |
