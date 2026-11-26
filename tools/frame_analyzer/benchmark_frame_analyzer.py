#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Reproducible synthetic Frame Analyzer benchmark; not a real-trace performance claim."""

import argparse
import csv
import json
import tempfile
import time
from pathlib import Path

from veyra_frame_analyzer import NATIVE_COLUMNS, analyze, read_trace


BASE = 70_000_000
TICKS_PER_FRAME = 166_667


def write_synthetic_trace(path, frame_count):
    event_count = frame_count * 3
    with path.open("w", encoding="utf-8", newline="") as output:
        output.write(
            "# schema=veyra-frame-trace/1\n"
            "# pid=4242\n"
            f"# host_ticks_per_second=10000000\n"
            f"# started_host={BASE}\n"
            f"# ended_host={BASE + frame_count * TICKS_PER_FRAME}\n"
            f"# requested_ms={max(1, round(frame_count * TICKS_PER_FRAME / 10000))}\n"
            f"# termination=duration\n"
            f"# recorded={event_count}\n"
            "# dropped=0\n"
            f"# capacity={event_count}\n"
        )
        writer = csv.DictWriter(output, fieldnames=NATIVE_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for source in range(1, frame_count + 1):
            start = BASE + source * TICKS_PER_FRAME
            arrival = start
            writer.writerow({
                "event": "Source", "host": start + 1000, "session": 1, "epoch": 1,
                "revision": 1, "source": source, "batch": source, "frameKind": "real",
                "stage": "SyntheticInput", "arrivalHost": arrival, "processHost": arrival + 1000,
            })
            writer.writerow({
                "event": "Submitted", "host": start + 30_000, "session": 1, "epoch": 1,
                "revision": 1, "source": source, "batch": source, "count": 1, "ms": 1.0,
            })
            writer.writerow({
                "event": "Present", "host": start + 50_000, "session": 1, "epoch": 1,
                "revision": 1, "source": source, "batch": source, "frameKind": "real",
                "presentBeginHost": start + 40_000, "presentEndHost": start + 50_000,
                "readyHost": start + 35_000, "arrivalHost": arrival,
                "processHost": arrival + 1000,
            })
        output.write("# complete=1\n")


def run_once(path, input_fps, output_fps, expected_frames):
    started = time.perf_counter()
    metadata, events = read_trace(path)
    parsed = time.perf_counter()
    report = analyze(metadata, events, input_fps=input_fps, output_fps=output_fps,
                     warmup_seconds=0, tail_seconds=0)
    finished = time.perf_counter()

    # Fail the smoke test if parsing/analysis silently drops synthetic records.
    source_rows = sum(row["role"] == "source" for row in report["frames"])
    output_rows = sum(row["role"] == "output" for row in report["frames"])
    expected_events = expected_frames * 3
    if len(events) != expected_events or metadata["recorded"] != expected_events:
        raise RuntimeError(f"Expected {expected_events} synthetic events, got {len(events)}")
    if source_rows != expected_frames or output_rows != expected_frames:
        raise RuntimeError(
            f"Expected {expected_frames} source and output rows, got "
            f"{source_rows} source and {output_rows} output"
        )

    return {
        "parse_seconds": round(parsed - started, 6),
        "analyze_seconds": round(finished - parsed, 6),
        "total_seconds": round(finished - started, 6),
        "events": len(events),
        "source_rows": source_rows,
        "output_rows": output_rows,
        "frame_rows": len(report["frames"]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=int, default=10000, help="synthetic source frames (default: 10000)")
    parser.add_argument("--repeat", type=int, default=3, help="measured iterations (default: 3)")
    parser.add_argument("--input-fps", type=float, default=60)
    parser.add_argument("--output-fps", type=float, default=60)
    args = parser.parse_args()
    if args.frames < 1 or args.repeat < 1 or args.input_fps <= 0 or args.output_fps <= 0:
        parser.error("frames, repeat, and FPS values must be positive")
    with tempfile.TemporaryDirectory(prefix="veyra-frame-bench-") as temporary:
        trace = Path(temporary) / "synthetic-trace.csv"
        write_synthetic_trace(trace, args.frames)
        results = [run_once(trace, args.input_fps, args.output_fps, args.frames) for _ in range(args.repeat)]
    print(json.dumps({
        "benchmark": "synthetic-frame-analyzer-v1",
        "synthetic_only": True,
        "frames_requested": args.frames,
        "repeat": args.repeat,
        "input_fps": args.input_fps,
        "output_fps": args.output_fps,
        "results": results,
    }, indent=2))


if __name__ == "__main__":
    main()
