# SPDX-License-Identifier: GPL-3.0-only
"""End-to-end CLI coverage for real-trace profiling mode."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from benchmark_frame_analyzer import write_synthetic_trace


class RealTraceBenchmarkCliTests(unittest.TestCase):
    def test_trace_mode_emits_profile_json_without_modifying_input(self):
        script = Path(__file__).with_name("benchmark_frame_analyzer.py")
        with tempfile.TemporaryDirectory() as temporary:
            trace = Path(temporary) / "representative.csv"
            write_synthetic_trace(trace, 5)
            original = trace.read_bytes()

            completed = subprocess.run(
                [sys.executable, "-B", str(script), "--trace", str(trace),
                 "--repeat", "2", "--measure-memory"],
                check=True, capture_output=True, text=True,
            )

            result = json.loads(completed.stdout)
            self.assertEqual(result["input_mode"], "real_trace")
            self.assertFalse(result["synthetic_only"])
            self.assertEqual(result["trace_name"], trace.name)
            self.assertEqual(result["trace_bytes"], len(original))
            self.assertEqual(result["metadata"]["recorded"], 15)
            self.assertEqual(result["event_counts"], {
                "Present": 5, "Source": 5, "Submitted": 5,
            })
            self.assertEqual(len(result["results"]), 2)
            self.assertTrue(all(row["source_rows"] == 5 and row["output_rows"] == 5
                                for row in result["results"]))
            self.assertEqual(result["memory"]["scope"], "python_tracemalloc_only")
            self.assertEqual(trace.read_bytes(), original)
            self.assertEqual(sorted(path.name for path in Path(temporary).iterdir()),
                             ["representative.csv"])


if __name__ == "__main__":
    unittest.main()
