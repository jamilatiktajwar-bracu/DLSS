#!/usr/bin/env python3
"""Analyze frame-time CSVs for DLSS/Veyra experiments without modifying source data.

Accepted CSV columns: frame_time_ms (preferred), or timestamp_ms (consecutive
presentation timestamps; the first row is omitted). Outputs a compact report.
"""
from __future__ import annotations
import argparse
import csv
import math
import statistics
import sys
from pathlib import Path


def percentile(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    rank = (len(ordered) - 1) * p
    lo, hi = math.floor(rank), math.ceil(rank)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (rank - lo)


def read_frame_times(path: Path) -> list[float]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV has no header row")
        names = {name.strip().lower(): name for name in reader.fieldnames if name}
        if "frame_time_ms" in names:
            column = names["frame_time_ms"]
            times = []
            for line, row in enumerate(reader, 2):
                raw = (row.get(column) or "").strip()
                if not raw:
                    continue
                value = float(raw)
                if not math.isfinite(value) or value <= 0:
                    raise ValueError(f"line {line}: frame_time_ms must be finite and > 0")
                times.append(value)
            return times
        if "timestamp_ms" in names:
            column = names["timestamp_ms"]
            stamps = []
            for line, row in enumerate(reader, 2):
                raw = (row.get(column) or "").strip()
                if not raw:
                    continue
                value = float(raw)
                if not math.isfinite(value):
                    raise ValueError(f"line {line}: timestamp_ms must be finite")
                if stamps and value <= stamps[-1]:
                    raise ValueError(f"line {line}: timestamps must be strictly increasing")
                stamps.append(value)
            return [b - a for a, b in zip(stamps, stamps[1:])]
        raise ValueError("CSV needs a frame_time_ms or timestamp_ms column")


def report(times: list[float], target_fps: float | None) -> str:
    if not times:
        raise ValueError("No frame intervals found")
    mean = statistics.fmean(times)
    threshold = (1000.0 / target_fps * 1.5) if target_fps else 1.5 * mean
    missed = sum(t > threshold for t in times)
    return "\n".join([
        "DLSS Frame-Time Analysis (offline; not a GPU benchmark)",
        f"Samples: {len(times)}",
        f"Average FPS (interval-derived): {1000.0 / mean:.2f}",
        f"Mean frame time: {mean:.3f} ms",
        f"Median: {statistics.median(times):.3f} ms",
        f"P95: {percentile(times, 0.95):.3f} ms",
        f"P99: {percentile(times, 0.99):.3f} ms",
        f"Maximum: {max(times):.3f} ms",
        f"Stutter threshold: {threshold:.3f} ms",
        f"Intervals above threshold: {missed} ({100.0 * missed / len(times):.2f}%)",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path, help="CSV containing frame_time_ms or timestamp_ms")
    parser.add_argument("--target-fps", type=float, help="Target refresh rate for 1.5x stutter threshold")
    args = parser.parse_args()
    if args.target_fps is not None and (not math.isfinite(args.target_fps) or args.target_fps <= 0):
        parser.error("--target-fps must be finite and positive")
    try:
        print(report(read_frame_times(args.csv_file), args.target_fps))
    except (OSError, csv.Error, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
