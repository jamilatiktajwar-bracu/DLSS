import importlib.util
import math
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "dlss-frame-time-report.py"
SPEC = importlib.util.spec_from_file_location("frame_report", SCRIPT)
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)


class FrameTimeReportTests(unittest.TestCase):
    def test_percentile_interpolates(self):
        self.assertAlmostEqual(REPORT.percentile([1, 2, 3, 4], 0.5), 2.5)

    def test_frame_time_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.csv"
            path.write_text("frame_time_ms\\n16.67\\n20\\n", encoding="utf-8")
            self.assertEqual(REPORT.read_frame_times(path), [16.67, 20.0])

    def test_timestamp_csv_derives_intervals(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "timestamps.csv"
            path.write_text("timestamp_ms\\n0\\n10\\n25\\n", encoding="utf-8")
            self.assertEqual(REPORT.read_frame_times(path), [10.0, 15.0])

    def test_non_increasing_timestamps_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.csv"
            path.write_text("timestamp_ms\\n5\\n5\\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                REPORT.read_frame_times(path)

    def test_zero_frame_interval_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.csv"
            path.write_text("frame_time_ms\\n0\\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                REPORT.read_frame_times(path)


if __name__ == "__main__":
    unittest.main()
