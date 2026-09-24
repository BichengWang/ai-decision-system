from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from pathlib import Path

from src.ml.cv.text_fetcher import extract_ocr_samples, extract_text_from_video
from src.utils.disk_calc import convert_size, main as disk_main


class DiskCalcTests(unittest.TestCase):
    def test_binary_conversion_is_exact(self) -> None:
        self.assertEqual(convert_size(1_099_511_627_776), Decimal("1"))
        self.assertEqual(
            convert_size("16_000_000_000_000"),
            Decimal(16_000_000_000_000) / Decimal(1024) ** 4,
        )

    def test_decimal_and_binary_units_are_distinct(self) -> None:
        self.assertEqual(convert_size(1, "TB", "GB"), Decimal("1000"))
        self.assertEqual(convert_size(1, "TiB", "GiB"), Decimal("1024"))

    def test_invalid_sizes_and_units_are_rejected(self) -> None:
        for value in (-1, float("inf"), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                convert_size(value)
        with self.assertRaises(ValueError):
            convert_size(1, to_unit="blocks")

    def test_cli_formats_the_requested_precision(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(
                disk_main(["1024", "--to-unit", "KiB", "--precision", "2"]), 0
            )
        self.assertEqual(output.getvalue(), "1.00 KiB\n")


class FakeCapture:
    def __init__(
        self, *, fps: float = 30, frame_count: int = 901, fail_at: int | None = None
    ) -> None:
        self.fps = fps
        self.frame_count = frame_count
        self.fail_at = fail_at
        self.position = 0
        self.positions: list[int] = []
        self.released = False

    def isOpened(self) -> bool:
        return True

    def get(self, prop: int) -> float:
        return self.fps if prop == FakeCV2.CAP_PROP_FPS else float(self.frame_count)

    def set(self, prop: int, value: int) -> bool:
        self.position = int(value)
        self.positions.append(self.position)
        return True

    def read(self):
        return self.position != self.fail_at, self.position

    def release(self) -> None:
        self.released = True


class FakeCV2:
    CAP_PROP_FPS = 1
    CAP_PROP_FRAME_COUNT = 2
    CAP_PROP_POS_FRAMES = 3
    COLOR_BGR2GRAY = 4
    THRESH_BINARY = 5

    def __init__(self, capture: FakeCapture) -> None:
        self.capture = capture

    def VideoCapture(self, path: str) -> FakeCapture:
        return self.capture

    @staticmethod
    def cvtColor(frame: int, mode: int) -> int:
        return frame

    @staticmethod
    def threshold(frame: int, threshold: int, maximum: int, mode: int):
        return threshold, frame


class TextFetcherTests(unittest.TestCase):
    def setUp(self) -> None:
        handle = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        handle.close()
        self.video = Path(handle.name)

    def tearDown(self) -> None:
        self.video.unlink(missing_ok=True)

    def test_seeks_only_requested_frames_and_deduplicates_text(self) -> None:
        capture = FakeCapture()
        texts = {0: " title ", 300: "title", 600: "next"}

        samples = extract_ocr_samples(
            self.video,
            duration_limit_minutes=0.5,
            sample_interval_seconds=10,
            cv2_module=FakeCV2(capture),
            ocr_function=lambda frame, **_: texts[frame],
        )

        self.assertEqual(capture.positions, [0, 300, 600])
        self.assertEqual([sample.text for sample in samples], ["title", "next"])
        self.assertEqual(samples[-1].timestamp_seconds, 20)
        self.assertTrue(capture.released)

    def test_string_api_keeps_nonconsecutive_samples(self) -> None:
        capture = FakeCapture(frame_count=601)
        texts = {0: "same", 300: "different", 600: "same"}
        result = extract_text_from_video(
            self.video,
            duration_limit_minutes=None,
            cv2_module=FakeCV2(capture),
            ocr_function=lambda frame, **_: texts[frame],
        )
        self.assertEqual(result, "same\ndifferent\nsame")

    def test_capture_is_released_when_ocr_fails(self) -> None:
        capture = FakeCapture(frame_count=1)
        with self.assertRaisesRegex(RuntimeError, "ocr failed"):
            extract_ocr_samples(
                self.video,
                cv2_module=FakeCV2(capture),
                ocr_function=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    RuntimeError("ocr failed")
                ),
            )
        self.assertTrue(capture.released)

    def test_missing_video_and_invalid_configuration_are_rejected(self) -> None:
        with self.assertRaises(FileNotFoundError):
            extract_ocr_samples(
                self.video.with_name("missing.mp4"),
                cv2_module=FakeCV2(FakeCapture()),
                ocr_function=str,
            )
        with self.assertRaises(ValueError):
            extract_ocr_samples(
                self.video,
                sample_interval_seconds=0,
                cv2_module=FakeCV2(FakeCapture()),
                ocr_function=str,
            )
        with self.assertRaises(ValueError):
            extract_ocr_samples(
                self.video,
                threshold=256,
                cv2_module=FakeCV2(FakeCapture()),
                ocr_function=str,
            )


if __name__ == "__main__":
    unittest.main()
