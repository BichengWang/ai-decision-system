"""Build and query a deterministic face-embedding index from videos.

DeepFace and OpenCV are optional runtime dependencies and are imported lazily.
Install them before using the CLI (for example, ``pip install deepface
opencv-python``). Importing this module, loading an existing index, and testing
its distance logic do not require either package.

Face embeddings are biometric data. Store generated indexes securely and only
process media for which you have the necessary consent and authorization.
"""

from __future__ import annotations

import argparse
import itertools
import json
import logging
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol, Sequence

logger = logging.getLogger(__name__)

SAMPLE_INTERVAL = 60.0
DETECTOR_BACKEND = "retinaface"
MODEL_NAME = "ArcFace"
DISTANCE_METRIC = "cosine"
DEFAULT_MATCH_THRESHOLD = 0.4
VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"})

Embedding = tuple[float, ...]
DistanceFunction = Callable[[Sequence[float], Sequence[float]], float]


class FaceRecognitionDependencyError(RuntimeError):
    """Raised when an optional face-recognition dependency is unavailable."""


class NoFaceDetectedError(ValueError):
    """Raised when an operation requiring one face finds none."""


class FaceBackend(Protocol):
    """Minimal interface implemented by face-embedding backends."""

    def encode(self, image: Any) -> list[Embedding]:
        """Return one embedding for each face detected in *image*."""

    def distance(self, left: Sequence[float], right: Sequence[float]) -> float:
        """Return a distance where smaller values indicate a closer match."""


@dataclass(frozen=True, slots=True)
class FaceMatch:
    """Nearest-neighbor result for one face."""

    name: str | None
    distance: float | None
    matched: bool


@dataclass(frozen=True, slots=True)
class VideoFaceEncoding:
    """A face embedding and its location in a video."""

    frame_number: int
    timestamp_seconds: float
    embedding: Embedding


@dataclass(frozen=True, slots=True)
class FaceIndex:
    """Names and face embeddings with validated dimensions."""

    names: tuple[str, ...] = ()
    embeddings: tuple[Embedding, ...] = ()

    def __post_init__(self) -> None:
        raw_names = tuple(self.names)
        if any(not isinstance(name, str) for name in raw_names):
            raise ValueError("face names must be strings")
        names = tuple(name.strip() for name in raw_names)
        embeddings = tuple(_normalize_embedding(item) for item in self.embeddings)
        if len(names) != len(embeddings):
            raise ValueError("names and embeddings must have the same length")
        if any(not name for name in names):
            raise ValueError("face names must not be blank")
        dimensions = {len(item) for item in embeddings}
        if len(dimensions) > 1:
            raise ValueError("all face embeddings must have the same dimension")
        object.__setattr__(self, "names", names)
        object.__setattr__(self, "embeddings", embeddings)

    def match(
        self,
        embedding: Sequence[float],
        *,
        threshold: float = DEFAULT_MATCH_THRESHOLD,
        distance_function: DistanceFunction | None = None,
    ) -> FaceMatch:
        """Return the nearest known face if it is within *threshold*."""
        metric = distance_function or cosine_distance
        limit = _nonnegative_finite(threshold, "threshold")
        candidate = _normalize_embedding(embedding)
        if not self.embeddings:
            return FaceMatch(name=None, distance=None, matched=False)
        if len(candidate) != len(self.embeddings[0]):
            raise ValueError(
                "candidate embedding dimension does not match the face index"
            )

        distances = [metric(candidate, known) for known in self.embeddings]
        best_index = min(range(len(distances)), key=distances.__getitem__)
        best_distance = float(distances[best_index])
        if not math.isfinite(best_distance) or best_distance < 0:
            raise ValueError("distance function returned an invalid distance")
        if best_distance <= limit:
            return FaceMatch(self.names[best_index], best_distance, True)
        return FaceMatch(None, best_distance, False)

    def save(self, path: str | Path) -> None:
        """Atomically save this index as portable, non-executable JSON."""
        destination = Path(path).expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "names": list(self.names),
            "embeddings": [list(item) for item in self.embeddings],
        }
        descriptor, temporary_name = tempfile.mkstemp(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            text=True,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, separators=(",", ":"), allow_nan=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, destination)
        finally:
            Path(temporary_name).unlink(missing_ok=True)

    @classmethod
    def load(cls, path: str | Path) -> "FaceIndex":
        """Load and validate a JSON face index."""
        source = Path(path).expanduser()
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise FileNotFoundError(f"face index does not exist: {source}") from None
        except json.JSONDecodeError as exc:
            raise ValueError(f"face index is not valid JSON: {source}") from exc
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise ValueError("unsupported face-index format or version")
        names = payload.get("names")
        embeddings = payload.get("embeddings")
        if not isinstance(names, list) or not isinstance(embeddings, list):
            raise ValueError("face index must contain names and embeddings arrays")
        try:
            return cls(tuple(names), tuple(embeddings))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"face index contains invalid data: {source}") from exc


class DeepFaceBackend:
    """Lazy adapter around DeepFace's embedding API."""

    def __init__(
        self,
        *,
        model_name: str = MODEL_NAME,
        detector_backend: str = DETECTOR_BACKEND,
        distance_metric: str = DISTANCE_METRIC,
    ) -> None:
        if distance_metric not in {"cosine", "euclidean", "euclidean_l2"}:
            raise ValueError(
                "distance_metric must be cosine, euclidean, or euclidean_l2"
            )
        try:
            from deepface import DeepFace
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise FaceRecognitionDependencyError(
                "DeepFace is required for face encoding; install it with "
                "`pip install deepface`."
            ) from exc
        self._deepface = DeepFace
        self.model_name = model_name
        self.detector_backend = detector_backend
        self.distance_metric = distance_metric

    def encode(self, image: Any) -> list[Embedding]:
        source = str(image) if isinstance(image, Path) else image
        try:
            representations = self._deepface.represent(
                img_path=source,
                model_name=self.model_name,
                detector_backend=self.detector_backend,
                enforce_detection=True,
                align=True,
            )
        except ValueError as exc:
            message = str(exc).casefold()
            if "face" in message and ("detect" in message or "could not" in message):
                return []
            raise
        if isinstance(representations, dict):
            representations = [representations]
        if not isinstance(representations, (list, tuple)):
            raise RuntimeError("DeepFace returned an unexpected representation format")
        return [
            _normalize_embedding(item["embedding"])
            for item in representations
            if isinstance(item, dict) and "embedding" in item
        ]

    def distance(self, left: Sequence[float], right: Sequence[float]) -> float:
        if self.distance_metric == "cosine":
            return cosine_distance(left, right)
        if self.distance_metric == "euclidean_l2":
            return euclidean_distance(_l2_normalize(left), _l2_normalize(right))
        return euclidean_distance(left, right)


def _normalize_embedding(values: Sequence[float]) -> Embedding:
    if isinstance(values, (str, bytes)):
        raise ValueError("embedding must be a numeric sequence")
    try:
        result = tuple(float(value) for value in values)
    except (TypeError, ValueError) as exc:
        raise ValueError("embedding must be a numeric sequence") from exc
    if not result:
        raise ValueError("embedding must not be empty")
    if not all(math.isfinite(value) for value in result):
        raise ValueError("embedding values must be finite")
    return result


def _nonnegative_finite(value: float, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number, not a boolean")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name} must be a non-negative finite number")
    return result


def _positive_finite(value: float, name: str) -> float:
    result = _nonnegative_finite(value, name)
    if result == 0:
        raise ValueError(f"{name} must be greater than zero")
    return result


def _l2_normalize(values: Sequence[float]) -> Embedding:
    embedding = _normalize_embedding(values)
    norm = math.sqrt(sum(value * value for value in embedding))
    if norm == 0:
        raise ValueError("cannot normalize a zero-length embedding vector")
    return tuple(value / norm for value in embedding)


def cosine_distance(left: Sequence[float], right: Sequence[float]) -> float:
    """Calculate cosine distance between equal-length embeddings."""
    left_vector = _normalize_embedding(left)
    right_vector = _normalize_embedding(right)
    if len(left_vector) != len(right_vector):
        raise ValueError("embedding dimensions do not match")
    left_norm = math.sqrt(sum(value * value for value in left_vector))
    right_norm = math.sqrt(sum(value * value for value in right_vector))
    if left_norm == 0 or right_norm == 0:
        raise ValueError("cosine distance is undefined for a zero vector")
    similarity = sum(a * b for a, b in zip(left_vector, right_vector)) / (
        left_norm * right_norm
    )
    # Clamp tiny floating-point excursions beyond the mathematical range.
    return 1 - min(1.0, max(-1.0, similarity))


def euclidean_distance(left: Sequence[float], right: Sequence[float]) -> float:
    """Calculate Euclidean distance between equal-length embeddings."""
    left_vector = _normalize_embedding(left)
    right_vector = _normalize_embedding(right)
    if len(left_vector) != len(right_vector):
        raise ValueError("embedding dimensions do not match")
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left_vector, right_vector)))


def _load_cv2() -> Any:
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise FaceRecognitionDependencyError(
            "OpenCV is required for video processing; install it with "
            "`pip install opencv-python`."
        ) from exc
    return cv2


def _sampled_frames(
    video_path: str | Path,
    *,
    interval_seconds: float,
    max_samples: int | None,
    cv2_module: Any | None,
) -> Iterable[tuple[int, float, Any]]:
    path = Path(video_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"video file does not exist: {path}")
    interval = _positive_finite(interval_seconds, "interval_seconds")
    if max_samples is not None and (
        isinstance(max_samples, bool)
        or not isinstance(max_samples, int)
        or max_samples <= 0
    ):
        raise ValueError("max_samples must be a positive integer or None")

    cv2 = cv2_module or _load_cv2()
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        capture.release()
        raise ValueError(f"OpenCV could not open video file: {path}")

    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError(f"video reports an invalid frame rate: {fps!r}")
        raw_count = float(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_count = (
            int(raw_count) if math.isfinite(raw_count) and raw_count > 0 else 0
        )
        step = max(1, round(fps * interval))
        targets: Iterable[int]
        if frame_count:
            targets = range(0, frame_count, step)
        else:
            targets = itertools.count(0, step)
        if max_samples is not None:
            targets = itertools.islice(targets, max_samples)

        for frame_number in targets:
            if not capture.set(cv2.CAP_PROP_POS_FRAMES, frame_number):
                raise RuntimeError(
                    f"video backend could not seek to frame {frame_number} in {path}"
                )
            success, frame = capture.read()
            if not success:
                if frame_count:
                    raise RuntimeError(
                        f"could not decode frame {frame_number} from {path}"
                    )
                break
            yield frame_number, frame_number / fps, frame
    finally:
        capture.release()


def extract_frames(
    video_path: str | Path,
    interval_sec: float = SAMPLE_INTERVAL,
    *,
    max_samples: int | None = None,
    cv2_module: Any | None = None,
) -> list[Any]:
    """Return directly sought video frames at a wall-clock interval."""
    return [
        frame
        for _, _, frame in _sampled_frames(
            video_path,
            interval_seconds=interval_sec,
            max_samples=max_samples,
            cv2_module=cv2_module,
        )
    ]


def scan_video_faces(
    video_path: str | Path,
    frame_interval: float = SAMPLE_INTERVAL,
    *,
    backend: FaceBackend | None = None,
    max_samples: int | None = None,
    skip_errors: bool = False,
    cv2_module: Any | None = None,
) -> list[VideoFaceEncoding]:
    """Extract every detected face from regularly sampled video frames."""
    encoder = backend or DeepFaceBackend()
    results: list[VideoFaceEncoding] = []
    for frame_number, timestamp, frame in _sampled_frames(
        video_path,
        interval_seconds=frame_interval,
        max_samples=max_samples,
        cv2_module=cv2_module,
    ):
        try:
            embeddings = encoder.encode(frame)
        except Exception:
            if not skip_errors:
                raise
            logger.exception(
                "face encoding failed at frame %d in %s", frame_number, video_path
            )
            continue
        results.extend(
            VideoFaceEncoding(frame_number, timestamp, _normalize_embedding(embedding))
            for embedding in embeddings
        )
    return results


def extract_encodings_from_video(
    video_path: str | Path,
    frame_interval: float = SAMPLE_INTERVAL,
    **kwargs: Any,
) -> list[Embedding]:
    """Compatibility wrapper returning embeddings without frame metadata."""
    return [
        item.embedding
        for item in scan_video_faces(video_path, frame_interval, **kwargs)
    ]


def create_face_encoding(
    image_path: str | Path,
    *,
    backend: FaceBackend | None = None,
) -> Embedding:
    """Create one face encoding, rejecting images with zero or many faces."""
    path = Path(image_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"image file does not exist: {path}")
    embeddings = (backend or DeepFaceBackend()).encode(path)
    if not embeddings:
        raise NoFaceDetectedError(f"no face detected in image: {path}")
    if len(embeddings) > 1:
        raise ValueError(
            f"expected one face but found {len(embeddings)} in image: {path}"
        )
    return _normalize_embedding(embeddings[0])


def recognize_faces(
    image: Any,
    known_encodings: Sequence[Sequence[float]],
    known_names: Sequence[str],
    *,
    threshold: float = DEFAULT_MATCH_THRESHOLD,
    backend: FaceBackend | None = None,
) -> list[str]:
    """Recognize all faces in an image against known embeddings."""
    encoder = backend or DeepFaceBackend()
    index = FaceIndex(
        tuple(known_names), tuple(tuple(item) for item in known_encodings)
    )
    names: list[str] = []
    for embedding in encoder.encode(image):
        match = index.match(
            embedding,
            threshold=threshold,
            distance_function=encoder.distance,
        )
        names.append(match.name if match.matched and match.name else "Unknown")
    return names


def build_face_index(
    root_dir: str | Path,
    *,
    max_folders: int | None = None,
    max_videos_per_folder: int = 5,
    frame_interval: float = SAMPLE_INTERVAL,
    extensions: Iterable[str] = VIDEO_EXTENSIONS,
    backend: FaceBackend | None = None,
    skip_errors: bool = False,
    cv2_module: Any | None = None,
) -> FaceIndex:
    """Build an index from ``root/person/**/*.video`` in stable path order."""
    root = Path(root_dir).expanduser()
    if not root.is_dir():
        raise NotADirectoryError(f"face library root is not a directory: {root}")
    if max_folders is not None and (
        isinstance(max_folders, bool)
        or not isinstance(max_folders, int)
        or max_folders < 0
    ):
        raise ValueError("max_folders must be a non-negative integer or None")
    if (
        isinstance(max_videos_per_folder, bool)
        or not isinstance(max_videos_per_folder, int)
        or max_videos_per_folder <= 0
    ):
        raise ValueError("max_videos_per_folder must be a positive integer")
    suffixes = {
        extension.casefold()
        if str(extension).startswith(".")
        else f".{str(extension).casefold()}"
        for extension in extensions
    }
    if not suffixes:
        raise ValueError("extensions must contain at least one file extension")

    encoder = backend or DeepFaceBackend()
    people = sorted(
        (path for path in root.iterdir() if path.is_dir()), key=lambda p: p.name
    )
    if max_folders:
        people = people[:max_folders]

    names: list[str] = []
    embeddings: list[Embedding] = []
    for person_dir in people:
        videos = sorted(
            (
                path
                for path in person_dir.rglob("*")
                if path.is_file() and path.suffix.casefold() in suffixes
            ),
            key=lambda path: str(path.relative_to(person_dir)),
        )[:max_videos_per_folder]
        for video in videos:
            logger.info("Processing %s for %s", video, person_dir.name)
            try:
                faces = scan_video_faces(
                    video,
                    frame_interval,
                    backend=encoder,
                    skip_errors=skip_errors,
                    cv2_module=cv2_module,
                )
            except Exception:
                if not skip_errors:
                    raise
                logger.exception("failed to process %s", video)
                continue
            embeddings.extend(item.embedding for item in faces)
            names.extend([person_dir.name] * len(faces))
    return FaceIndex(tuple(names), tuple(embeddings))


def build_known_faces_encodings(
    root_dir: str | Path,
    max_folders: int | None = None,
    max_videos_per_folder: int = 5,
    **kwargs: Any,
) -> tuple[list[Embedding], list[str]]:
    """Compatibility wrapper returning the notebook's two-list result."""
    index = build_face_index(
        root_dir,
        max_folders=max_folders,
        max_videos_per_folder=max_videos_per_folder,
        **kwargs,
    )
    return list(index.embeddings), list(index.names)


def _add_backend_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--model", default=MODEL_NAME)
    parser.add_argument("--detector", default=DETECTOR_BACKEND)
    parser.add_argument(
        "--distance-metric",
        choices=("cosine", "euclidean", "euclidean_l2"),
        default=DISTANCE_METRIC,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser("build", help="build an index from person directories")
    build.add_argument("root", type=Path)
    build.add_argument("output", type=Path)
    build.add_argument("--interval", type=float, default=SAMPLE_INTERVAL)
    build.add_argument("--max-folders", type=int)
    build.add_argument("--max-videos-per-person", type=int, default=5)
    build.add_argument("--skip-errors", action="store_true")
    _add_backend_options(build)

    recognize = commands.add_parser("recognize", help="match faces in a video")
    recognize.add_argument("index", type=Path)
    recognize.add_argument("video", type=Path)
    recognize.add_argument("--interval", type=float, default=SAMPLE_INTERVAL)
    recognize.add_argument("--max-samples", type=int)
    recognize.add_argument("--threshold", type=float, default=DEFAULT_MATCH_THRESHOLD)
    recognize.add_argument("--json", action="store_true")
    recognize.add_argument("--skip-errors", action="store_true")
    _add_backend_options(recognize)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the face-index CLI."""
    parser = _parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)
    try:
        backend = DeepFaceBackend(
            model_name=args.model,
            detector_backend=args.detector,
            distance_metric=args.distance_metric,
        )
        if args.command == "build":
            index = build_face_index(
                args.root,
                max_folders=args.max_folders,
                max_videos_per_folder=args.max_videos_per_person,
                frame_interval=args.interval,
                backend=backend,
                skip_errors=args.skip_errors,
            )
            index.save(args.output)
            print(
                f"Saved {len(index.embeddings)} embeddings for "
                f"{len(set(index.names))} people to {args.output}"
            )
            return 0

        index = FaceIndex.load(args.index)
        faces = scan_video_faces(
            args.video,
            args.interval,
            backend=backend,
            max_samples=args.max_samples,
            skip_errors=args.skip_errors,
        )
        records = []
        for face in faces:
            match = index.match(
                face.embedding,
                threshold=args.threshold,
                distance_function=backend.distance,
            )
            records.append(
                {
                    "frame_number": face.frame_number,
                    "timestamp_seconds": face.timestamp_seconds,
                    "name": match.name or "Unknown",
                    "distance": match.distance,
                    "matched": match.matched,
                }
            )
        if args.json:
            print(json.dumps(records, indent=2, allow_nan=False))
        elif not records:
            print("No faces detected.")
        else:
            for record in records:
                distance = record["distance"]
                distance_text = "n/a" if distance is None else f"{distance:.4f}"
                print(
                    f"{record['timestamp_seconds']:10.2f}s  "
                    f"{record['name']:<24} distance={distance_text}"
                )
        return 0
    except (
        FaceRecognitionDependencyError,
        FileNotFoundError,
        NotADirectoryError,
        ValueError,
    ) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
