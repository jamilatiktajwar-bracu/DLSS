# SPDX-License-Identifier: GPL-3.0-only
"""Schema and per-frame correlation fixtures. All rows are synthetic."""

import argparse
import csv
import io
import tempfile
import unittest
from pathlib import Path

from benchmark_frame_analyzer import (measure_peak_memory, positive_finite_float,
                                      run_once, write_synthetic_trace)
from veyra_frame_analyzer import (NATIVE_COLUMNS, analyze, read_legacy, read_native,
                                  normalize_event, output_records, sample_groups, validate_output_paths, write_report, annotate_gap_evidence)


BASE = 70_000_000


def example_trace(complete=True, dropped=0):
    rows = []

    def event(kind, source, offset, **fields):
        row = dict(event=kind, host=BASE + offset, session=1, epoch=9, revision=4,
                   source=source, batch=source, frameKind="real")
        row.update(fields)
        rows.append(row)

    for source in range(1, 25):
        offset = source * 100_000
        arrival = BASE + offset
        present = arrival + 45_000
        event("Source", source, offset + 1000, stage="ScreenCapture", arrivalHost=arrival,
              processHost=arrival + 1500)
        event("Submitted", source, offset + 30_000, count=1, ms=1.2)
        event("Gpu", source, offset + 40_000, stage="Nr", ms=9 if source == 20 else 1.4,
              gpuBegin=54_000, gpuEnd=63_000, gpuFrequency=1_000_000)
        event("Cpu", source, offset + 44_000, stage="SlotWait", ms=.1)
        event("Cpu", source, offset + 44_500, detail=1, frameKind="generated", stage="DeadlineWait", ms=1.0)
        event("Present", source, offset + 42_000, detail=1, frameKind="generated", pts=source * 100_000,
              presentBeginHost=present - 30_000, presentEndHost=present - 3000, arrivalHost=arrival,
              sourceA=source-1, sourceAHost=arrival-100_000)
        event("Present", source, offset + 55_000, pts=source * 100_000 + 50_000,
              presentBeginHost=present, presentCallHost=present+5000, presentEndHost=present+10_000,
              readyHost=present+1000, arrivalHost=arrival)
    event("GpuUnavailable", 20, 2_000_100, stage="FgBatch")
    event("Discarded", 21, 2_150_000, detail=2, frameKind="generated", stage="Deadline", count=4, ms=3)
    event("SourceSkipped", 42, 2_401_000, epoch=0, batch=0, stage="ContentDedup")
    event("Source", 3, 2_600_000, epoch=10, arrivalHost=BASE+2_590_000)
    event("Present", 3, 2_650_000, epoch=10, presentBeginHost=BASE+2_649_000, presentEndHost=BASE+2_650_000)
    event("ProviderOutput", 0, 2_655_000, session=0, epoch=0, revision=0, ms=1.2)
    result = io.StringIO()
    result.write(f"# schema=veyra-frame-trace/1\n# pid=42\n# host_ticks_per_second=10000000\n"
                 f"# started_host={BASE}\n# ended_host={BASE+3_000_000}\n# requested_ms=300\n"
                 f"# termination=duration\n# recorded={len(rows)}\n# dropped={dropped}\n# capacity=1000\n")
    writer = csv.DictWriter(result, NATIVE_COLUMNS + ["presentCallHost"], lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    if complete:
        result.write("# complete=1\n")
    return result.getvalue()


class CsvExportTests(unittest.TestCase):
    def test_formula_like_text_is_escaped_but_numbers_are_preserved(self):
        report = {"frames": [{
            "time_ms": -1.25,
            "role": "=HYPERLINK(\"https://example.invalid\",\"click\")",
            "source_a": " \t+SUM(1,1)",
            "issues": ["@SUM(1,1)", "-not-a-number"],
            "metrics_ms": {"negative_measurement": -2.5},
            "discard_reason": "-=1+1",
        }]}
        with tempfile.TemporaryDirectory() as temporary:
            write_report(Path(temporary), report)
            with Path(temporary, "frames.csv").open(encoding="utf-8-sig", newline="") as file:
                row = next(csv.DictReader(file))
        self.assertEqual(row["role"], "'=HYPERLINK(\"https://example.invalid\",\"click\")")
        self.assertEqual(row["source_a"], "' \t+SUM(1,1)")
        self.assertEqual(row["issues"], "[\"@SUM(1,1)\",\"-not-a-number\"]")
        self.assertEqual(row["time_ms"], "-1.25")
        self.assertEqual(row["metrics_ms"], "{\"negative_measurement\":-2.5}")
        self.assertEqual(row["discard_reason"], "'-=1+1")


    def test_report_json_cannot_close_embedded_script_element(self):
        attack = "</script><script>globalThis.pwned=1</script>&"
        with tempfile.TemporaryDirectory() as temporary:
            write_report(Path(temporary), {"source_file": attack, "frames": []})
            html = Path(temporary, "report.html").read_text(encoding="utf-8")
        self.assertNotIn(attack, html)
        self.assertIn(r"\u003c/script\u003e\u003cscript\u003eglobalThis.pwned=1"
                      r"\u003c/script\u003e\u0026", html)


    def test_existing_analysis_outputs_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            trace = root / "capture.csv"
            trace.write_text("private trace", encoding="utf-8")
            destination = root / "capture.analysis"
            destination.mkdir()
            prior = destination / "frames.csv"
            prior.write_text("keep this report", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Refusing to overwrite"):
                validate_output_paths(trace, destination)
            self.assertEqual(prior.read_text(encoding="utf-8"), "keep this report")

            clean_destination = root / "clean.analysis"
            validate_output_paths(trace, clean_destination)
            self.assertFalse(clean_destination.exists())

    def test_broken_output_symlink_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            trace = root / "capture.csv"
            trace.write_text("private trace", encoding="utf-8")
            destination = root / "capture.analysis"
            destination.mkdir()
            broken_link = destination / "report.html"
            try:
                broken_link.symlink_to(root / "missing-report.html")
            except (NotImplementedError, OSError) as error:
                self.skipTest(f"Symlinks unavailable: {error}")
            self.assertFalse(broken_link.exists())
            self.assertTrue(broken_link.is_symlink())
            with self.assertRaisesRegex(ValueError, "report.html"):
                validate_output_paths(trace, destination)
            self.assertTrue(broken_link.is_symlink())


class SyntheticBenchmarkTests(unittest.TestCase):
    def test_benchmark_fps_arguments_must_be_finite_and_positive(self):
        for value in ("nan", "inf", "-inf", "0", "-1"):
            with self.subTest(value=value):
                with self.assertRaises(argparse.ArgumentTypeError):
                    positive_finite_float(value)
        self.assertEqual(positive_finite_float("59.94"), 59.94)

    def test_benchmark_fixture_preserves_all_source_and_output_rows(self):
        with tempfile.TemporaryDirectory() as temporary:
            trace = Path(temporary) / "synthetic.csv"
            write_synthetic_trace(trace, 4)
            result = run_once(trace, 60, 60, expected_frames=4)
            trace_mode_result = run_once(trace, 60, 60)
        self.assertEqual(result["events"], 12)
        self.assertEqual(result["source_rows"], 4)
        self.assertEqual(result["output_rows"], 4)
        self.assertEqual(result["frame_rows"], 8)
        self.assertEqual(trace_mode_result["events"], 12)
        self.assertEqual(trace_mode_result["source_rows"], 4)
        self.assertEqual(trace_mode_result["output_rows"], 4)

    def test_optional_memory_profile_reports_traced_peak_and_complete_rows(self):
        with tempfile.TemporaryDirectory() as temporary:
            trace = Path(temporary) / "synthetic.csv"
            write_synthetic_trace(trace, 4)
            result = measure_peak_memory(trace, 60, 60)
        self.assertEqual(result["events"], 12)
        self.assertEqual(result["frame_rows"], 8)
        self.assertGreater(result["peak_traced_bytes"], 0)
        self.assertEqual(result["scope"], "python_tracemalloc_only")


class SampleGroupingTests(unittest.TestCase):
    def test_metrics_and_measured_stages_are_grouped_without_unmeasured_samples(self):
        source = {"phase": "steady", "session": 1, "epoch": 2, "revision": 3,
                  "role": "source", "metrics_ms": {"decode": 1.5},
                  "stages": [{"domain": "gpu", "stage": "NR", "ms": 2.5},
                             {"domain": "cpu", "stage": "wait", "ms": None}]}
        output = {"phase": "steady", "session": 1, "epoch": 2, "revision": 3,
                  "role": "output", "metrics_ms": {"present_api": 3.0},
                  "stages": [{"domain": "cpu", "stage": "prepare", "ms": 0.5}]}
        startup = {"phase": "startup", "session": 1, "epoch": 2, "revision": 3,
                   "role": "source", "metrics_ms": {"decode": 99},
                   "stages": [{"domain": "gpu", "stage": "NR", "ms": 99}]}
        all_groups, scoped = sample_groups([source, output, startup])
        self.assertEqual(dict(all_groups), {
            "source/decode": [1.5], "source/gpu/NR": [2.5],
            "output/present_api": [3.0], "output/cpu/prepare": [0.5]})
        self.assertEqual(scoped[(1, 2, 3, "source"), "decode"], [(source, 1.5)])
        self.assertEqual(scoped[(1, 2, 3, "source"), "gpu/NR"], [(source, 2.5)])
        self.assertNotIn(((1, 2, 3, "source"), "cpu/wait"), scoped)
class GapEvidenceTests(unittest.TestCase):
    def test_anomaly_context_survives_missing_source_row(self):
        row = {
            "source_key": "1/2/3/4", "role": "output", "anomalies": [{"metric": "present_entry_interval"}],
            "metrics_ms": {"present_entry_interval": 5.0}, "present_begin_host": 150,
            "present_end_host": 155, "process_host": 120,
        }
        annotate_gap_evidence([row], {}, 1.0)
        self.assertEqual(row["anomaly_context"]["source_measurements_ms"], {})
        self.assertIsNone(row["anomaly_context"]["nearby_present_wall_ms"])
        self.assertIsNone(row["anomaly_context"]["intersection_with_source_graph_wall_ms"])


class OutputGroupingTests(unittest.TestCase):
    def test_output_rows_reuse_nonterminal_event_numbers_and_cpu_samples(self):
        key = (1, 2, 3, 4, 5, 6)
        events = [
            {"event": "FrameReady", "host": 100, "event_number": 1, "stage": "ready"},
            {"event": "Cpu", "host": 110, "event_number": 2, "stage": "Prepare", "ms": 1.0},
            {"event": "Present", "host": 120, "event_number": 3, "presentBeginHost": 115, "presentEndHost": 120},
            {"event": "Discarded", "host": 130, "event_number": 4, "stage": "Deadline", "ms": 2.0},
        ]
        rows = list(output_records({key: events}, 100, .1, legacy=False))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["events"], [3, 1, 2])
        self.assertEqual(rows[1]["events"], [4, 1, 2])
        self.assertEqual(rows[0]["stages"], rows[1]["stages"])
        self.assertIsNot(rows[0]["stages"], rows[1]["stages"])
        rows[0]["stages"][0]["stage"] = "Mutated"
        self.assertEqual(rows[0]["stages"][0]["stage"], "Mutated")
        self.assertEqual(rows[1]["stages"][0]["stage"], "Prepare")
        self.assertEqual(rows[0]["issues"], ["repeated_output_identity"])
        self.assertEqual(rows[1]["issues"], ["repeated_output_identity"])


class TraceTests(unittest.TestCase):
    def test_event_normalization_reuses_the_reader_record(self):
        raw = {"event": "Source", "host": "70001000", "session": "", "source": "4"}
        normalized = normalize_event(raw, 1)
        self.assertIs(normalized, raw)
        self.assertEqual(normalized, {"event": "Source", "host": 70001000,
                                      "source": 4, "event_number": 1})

    def test_event_numeric_fields_reject_nonfinite_and_malformed_values(self):
        for value in ("nan", "inf", "-inf", "not-a-number"):
            with self.subTest(value=value):
                raw = {"event": "Cpu", "host": "70001000", "ms": value}
                with self.assertRaisesRegex(ValueError, "Invalid ms"):
                    normalize_event(raw, 1)
        with self.assertRaisesRegex(ValueError, "Invalid host"):
            normalize_event({"event": "Source", "host": "bad"}, 1)

    def test_native_duplicate_metadata_rejected(self):
        trace = example_trace()
        lines = trace.splitlines(keepends=True)
        lines.insert(1, "# pid=99\\n")
        with self.assertRaisesRegex(ValueError, "Invalid trace metadata"):
            read_native(io.StringIO("".join(lines)))

    def test_native_host_capture_window_boundaries_are_inclusive(self):
        trace = example_trace()
        lines = trace.splitlines(keepends=True)
        header_index = next(i for i, line in enumerate(lines) if line.startswith("event,"))
        event_rows = list(csv.DictReader(lines[header_index:-1]))
        event_rows[0]["host"] = str(BASE)
        event_rows[-1]["host"] = str(BASE + 3_000_000)
        output = io.StringIO()
        output.write("".join(lines[:header_index]))
        writer = csv.DictWriter(output, NATIVE_COLUMNS + ["presentCallHost"], lineterminator="\\n")
        writer.writeheader()
        writer.writerows(event_rows)
        output.write("# complete=1\\n")
        meta, events = read_native(io.StringIO(output.getvalue()))
        self.assertEqual(events[0]["host"], meta["started_host"])
        self.assertEqual(events[-1]["host"], meta["ended_host"])

    def test_native_duplicate_and_empty_column_names_rejected(self):
        trace = example_trace()
        lines = trace.splitlines(keepends=True)
        header_index = next(i for i, line in enumerate(lines) if line.startswith("event,"))
        columns = lines[header_index].rstrip("\n").split(",")
        columns[1] = columns[0]
        lines[header_index] = ",".join(columns) + "\n"
        with self.assertRaisesRegex(ValueError, "column header is invalid"):
            read_native(io.StringIO("".join(lines)))
        lines = trace.splitlines(keepends=True)
        header_index = next(i for i, line in enumerate(lines) if line.startswith("event,"))
        columns = lines[header_index].rstrip("\n").split(",")
        columns[-1] = ""
        lines[header_index] = ",".join(columns) + "\n"
        with self.assertRaisesRegex(ValueError, "column header is invalid"):
            read_native(io.StringIO("".join(lines)))

    def test_native_malformed_csv_quotes_rejected(self):
        lines = example_trace().splitlines(keepends=True)
        header_index = next(i for i, line in enumerate(lines) if line.startswith("event,"))
        lines[header_index + 1] = '"unterminated,broken\n'
        with self.assertRaises(csv.Error):
            read_native(io.StringIO("".join(lines)))

    def test_native_completion_marker_must_be_terminal(self):
        lines = example_trace().splitlines(keepends=True)
        lines.append("unexpected,extra,row\n")
        with self.assertRaisesRegex(ValueError, "after the trace completion"):
            read_native(io.StringIO("".join(lines)))

    def test_native_event_host_must_fall_inside_capture_window(self):
        trace = example_trace()
        lines = trace.splitlines(keepends=True)
        header_index = next(i for i, line in enumerate(lines) if line.startswith("event,"))
        event_rows = list(csv.DictReader(lines[header_index:-1]))
        event_rows[0]["host"] = str(BASE - 1)
        output = io.StringIO()
        output.write("".join(lines[:header_index]))
        writer = csv.DictWriter(output, NATIVE_COLUMNS + ["presentCallHost"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(event_rows)
        output.write("# complete=1\n")
        with self.assertRaisesRegex(ValueError, "outside the trace capture window"):
            read_native(io.StringIO(output.getvalue()))

    def test_incomplete_matching_count_rejected(self):
        with self.assertRaisesRegex(ValueError, "complete=1"):
            read_native(io.StringIO(example_trace(complete=False)))
        lines = example_trace().splitlines(keepends=True)
        del lines[-2]
        with self.assertRaisesRegex(ValueError, "declared"):
            read_native(io.StringIO("".join(lines)))

    def test_warmup_loss_scope_and_single_span(self):
        meta, events = read_native(io.StringIO(example_trace(dropped=2)))
        report = analyze(meta, events, input_fps=100, output_fps=200, warmup_seconds=.03, tail_seconds=.001)
        self.assertEqual(report["coverage"]["trace_event_loss"], 2)
        self.assertGreater(report["coverage"]["row_phase_counts"]["startup"], 0)
        sources = [row for row in report["frames"] if row["role"] == "source" and row["source"] == 20]
        self.assertEqual(len(sources), 1)
        row = sources[0]
        self.assertIn("gpu/Nr", {flag["metric"] for flag in row["anomalies"]})
        self.assertTrue(any(stage["stage"] == "FgBatch" and stage["ms"] is None for stage in row["stages"]))
        self.assertNotIn("source/gpu/FgBatch", report["timing_ms"])
        later = next(row for row in report["frames"] if row["role"] == "source" and row["epoch"] == 10)
        self.assertNotIn("ingress_interval", later["metrics_ms"])
        self.assertTrue(any(row["metric"] == "ingress_interval" for row in report["phase_boundaries"]))
        self.assertEqual(report["steady_input_skips"], {"ContentDedup": 1})
        self.assertEqual(report["provider_events"][0]["source"], 0)

    def test_subframe_association_and_clock_order(self):
        meta, events = read_native(io.StringIO(example_trace()))
        report = analyze(meta, events, warmup_seconds=0)
        outputs = [row for row in report["frames"] if row["role"] == "output" and row["source"] == 20]
        generated, real = outputs
        self.assertEqual(generated["subframe"], 1)
        self.assertEqual(generated["source_a"], 19)
        self.assertEqual(generated["frame_kind"], "generated")
        self.assertEqual([stage["stage"] for stage in generated["stages"]], ["DeadlineWait"])
        self.assertEqual(real["stages"], [])
        self.assertEqual(real["metrics_ms"]["present_prepare_wall"], .5)
        self.assertEqual(real["metrics_ms"]["present_sink_wall"], .5)
        self.assertNotIn("observed_ready_to_present", real["metrics_ms"])
        self.assertIn("readiness_sampled_after_present_entry", real["issues"])
        discarded = next(row for row in report["frames"] if row.get("status") == "discarded")
        self.assertEqual(discarded["anomalies"][0]["reasons"], ["output_deadline_expired"])

    def test_legacy_header_counters_are_validated(self):
        for header in (
            "Frame trace: records=-1 capacity=10 overwritten=0",
            "Frame trace: records=1 capacity=0 overwritten=0",
            "Frame trace: records=1 capacity=10 overwritten=-1",
            "Frame trace: records=11 capacity=10 overwritten=0",
        ):
            with self.subTest(header=header):
                raw = header + "\n"
                with self.assertRaisesRegex(ValueError, "Invalid legacy trace record counters"):
                    read_legacy(io.StringIO(raw))

    def test_legacy_duplicate_fields_rejected(self):
        raw = ("Frame trace: records=1 capacity=10 overwritten=0\n"
               "event=Source host=5000000 session=1 source=2 source=3\n")
        with self.assertRaisesRegex(ValueError, "Malformed legacy event record"):
            read_legacy(io.StringIO(raw))

    def test_legacy_malformed_token_rejected(self):
        raw = ("Frame trace: records=1 capacity=10 overwritten=0\n"
               "event=Source host=5000000 session=1 malformed\n")
        with self.assertRaisesRegex(ValueError, "Malformed legacy event record"):
            read_legacy(io.StringIO(raw))

    def test_legacy_event_with_leading_whitespace_is_not_silently_dropped(self):
        raw = ("Frame trace: records=1 capacity=10 overwritten=0\n"
               "  event=Source host=5000000 session=1 source=2\n")
        meta, events = read_legacy(io.StringIO(raw))
        self.assertEqual(meta["recorded"], 1)
        self.assertEqual(events[0]["event"], "Source")
        self.assertEqual(events[0]["source"], 2)

    def test_legacy_overwrite_and_gpu_stage_map(self):
        raw = ("Veyra diagnostics\r\nFrame trace: records=2 capacity=8192 overwritten=25\r\n"
               "event=Gpu host=5000000 session=1 revision=8 epoch=2 source=42 batch=0 detail=3 ms=1.2\r\n"
               "event=Present host=5001000 session=1 revision=8 epoch=2 source=42 batch=42 detail=1 "
               "presentBeginHost=5000020 presentEndHost=5001000\r\n")
        meta, events = read_legacy(io.StringIO(raw))
        report = analyze(meta, events, warmup_seconds=0)
        self.assertEqual(report["coverage"]["trace_event_loss"], 25)
        self.assertEqual(report["timing_ms"]["source/gpu/Nr"]["samples"], 1)
        output = next(row for row in report["frames"] if row["role"] == "output")
        self.assertEqual(output["frame_kind"], "generated")
        self.assertIsNone(output["arrival_host"])
        self.assertIn("source_ingress_unobserved", output["issues"])


if __name__ == "__main__":
    unittest.main()
