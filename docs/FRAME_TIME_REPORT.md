# Frame-time report tool

This is an offline CSV analyzer for frame pacing experiments. It does **not** run a GPU test, benchmark the application, or change source CSV files.

## Usage

Python 3.10+ (standard library only):

```sh
python scripts/dlss-frame-time-report.py capture.csv --target-fps 60
```

CSV format A (preferred):

```csv
frame_time_ms
16.67
16.69
22.1
```

CSV format B (timestamps, in milliseconds):

```csv
timestamp_ms
0
16.67
33.34
51.0
```

For timestamp CSVs, intervals are derived from adjacent timestamps and the first timestamp does not count as a sample.

The report shows interval-derived average FPS, mean/median/P95/P99/max frame time, and intervals above a threshold. With `--target-fps`, the threshold is 1.5 times the target frame interval; otherwise it is 1.5 times the measured mean. This threshold is a heuristic, not a universal definition of stutter.

## Interpreting comparisons

Compare captures with the same source, resolution, refresh rate, capture method, and workload. Keep original CSVs and record the settings/hardware separately. A single report cannot prove an optimization is faster; repeat runs and compare distributions.