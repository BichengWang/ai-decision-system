"""Extract text from sampled video frames with Tesseract OCR.

The public functions are import-safe when the optional OCR runtime is absent.
OpenCV and pytesseract are loaded only when extraction starts. The Tesseract
executable must also be installed and discoverable on ``PATH``.
"""

from __future__ import annotations

import argparse
import itertools
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

logger = logging.getLogger(__name__)


class OCRDependencyError(RuntimeError):
    """Raised when the Python or system OCR dependencies are unavailable."""


@dataclass(frozen=True, slots=True)
class OCRSample:
    """Text extracted from one sampled video frame."""

    frame_number: int
    timestamp_seconds: float
    text: str


def _load_cv2() -> Any:
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise OCRDependencyError(
            "OpenCV is required; install the project dependencies or "
            "`pip install opencv-python`."
        ) from exc
    return cv2


def _load_ocr_function() -> Callable[..., str]:
    try:
        import pytesseract
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise OCRDependencyError(
            "pytesseract is required; install it with `pip install pytesseract` "
            "and install the Tesseract executable for your operating system."
        ) from exc
    return pytesseract.image_to_string


def _validate_positive(value: float, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return number


def _target_frames(
    *,
    fps: float,
    frame_count: int,
    duration_limit_minutes: float | None,
    sample_interval_seconds: float,
) -> Iterable[int]:
    step = max(1, round(fps * sample_interval_seconds))
    if duration_limit_minutes is not None:
        duration_frames = max(1, math.ceil(duration_limit_minutes * 60 * fps))
        stop = min(frame_count, duration_frames) if frame_count > 0 else duration_frames
        return range(0, stop, step)
    if frame_count > 0:
        return range(0, frame_count, step)
    return itertools.count(0, step)


def extract_ocr_samples(
    video_path: str | Path,
    duration_limit_minutes: float | None = 5,
    sample_interval_seconds: float = 10,
    *,
    threshold: int = 127,
    language: str | None = None,
    deduplicate: bool = True,
    skip_errors: bool = False,
    cv2_module: Any | None = None,
    ocr_function: Callable[..., str] | None = None,
) -> list[OCRSample]:
    """Extract OCR samples from a video at a fixed wall-clock interval.

    Frames are sought directly instead of decoding every frame, which makes
    long-video sampling substantially cheaper. Consecutive duplicate OCR text
    is omitted by default.

    Args:
        video_path: Existing video file to inspect.
        duration_limit_minutes: Maximum duration to inspect, or ``None`` for
            the complete video.
        sample_interval_seconds: Time between sampled frames.
        threshold: Grayscale binary threshold in the inclusive range 0..255.
        language: Optional Tesseract language code, such as ``"eng"``.
        deduplicate: Drop consecutive samples with identical stripped text.
        skip_errors: Log failed frames and continue instead of raising.
        cv2_module: Dependency-injection hook used by tests.
        ocr_function: Dependency-injection hook compatible with
            ``pytesseract.image_to_string``.
    """
    path = Path(video_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"video file does not exist: {path}")
    interval = _validate_positive(sample_interval_seconds, "sample_interval_seconds")
    if duration_limit_minutes is not None:
        duration_limit_minutes = _validate_positive(
            duration_limit_minutes, "duration_limit_minutes"
        )
    if (
        isinstance(threshold, bool)
        or not isinstance(threshold, int)
        or not 0 <= threshold <= 255
    ):
        raise ValueError("threshold must be an integer between 0 and 255")

    cv2 = cv2_module or _load_cv2()
    ocr = ocr_function or _load_ocr_function()
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        capture.release()
        raise ValueError(f"OpenCV could not open video file: {path}")

    samples: list[OCRSample] = []
    previous_text: str | None = None
    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError(f"video reports an invalid frame rate: {fps!r}")
        raw_count = float(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_count = (
            int(raw_count) if math.isfinite(raw_count) and raw_count > 0 else 0
        )

        for frame_number in _target_frames(
            fps=fps,
            frame_count=frame_count,
            duration_limit_minutes=duration_limit_minutes,
            sample_interval_seconds=interval,
        ):
            positioned = capture.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            if not positioned:
                message = (
                    f"video backend could not seek to frame {frame_number} in {path}"
                )
                if not skip_errors:
                    raise RuntimeError(message)
                logger.warning(message)
                if frame_count == 0:
                    break
                continue
            success, frame = capture.read()
            if not success:
                # For streams with unknown frame counts, this is the normal end.
                if frame_count == 0:
                    break
                message = f"could not decode frame {frame_number} from {path}"
                if skip_errors:
                    logger.warning(message)
                    continue
                raise RuntimeError(message)

            try:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                _, binary = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)
                kwargs = {"lang": language} if language else {}
                text = str(ocr(binary, **kwargs)).strip()
            except Exception:
                if not skip_errors:
                    raise
                logger.exception("OCR failed for frame %d in %s", frame_number, path)
                continue

            if not text or (deduplicate and text == previous_text):
                continue
            samples.append(
                OCRSample(
                    frame_number=frame_number,
                    timestamp_seconds=frame_number / fps,
                    text=text,
                )
            )
            previous_text = text
    finally:
        capture.release()

    return samples


def extract_text_from_video(
    video_path: str | Path,
    duration_limit_minutes: float | None = 5,
    sample_interval_seconds: float = 10,
    **kwargs: Any,
) -> str:
    """Return sampled OCR text joined by newlines.

    This preserves the notebook's original string-returning API while exposing
    timestamps through :func:`extract_ocr_samples` for richer callers.
    """
    samples = extract_ocr_samples(
        video_path,
        duration_limit_minutes,
        sample_interval_seconds,
        **kwargs,
    )
    return "\n".join(sample.text for sample in samples)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path, help="video file to scan")
    parser.add_argument(
        "--minutes",
        type=float,
        default=5,
        help="maximum video duration to scan (default: 5)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=10,
        help="seconds between sampled frames (default: 10)",
    )
    parser.add_argument("--threshold", type=int, default=127)
    parser.add_argument("--language", help="Tesseract language code")
    parser.add_argument("--output", type=Path, help="write text to this UTF-8 file")
    parser.add_argument("--keep-duplicates", action="store_true")
    parser.add_argument("--skip-errors", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the video OCR CLI."""
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)
    text = extract_text_from_video(
        args.video,
        duration_limit_minutes=args.minutes,
        sample_interval_seconds=args.interval,
        threshold=args.threshold,
        language=args.language,
        deduplicate=not args.keep_duplicates,
        skip_errors=args.skip_errors,
    )
    if args.output:
        args.output.expanduser().write_text(
            text + ("\n" if text else ""), encoding="utf-8"
        )
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
