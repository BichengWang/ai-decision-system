from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.utils.face_rec.face_rec import (
    FaceIndex,
    build_face_index,
    cosine_distance,
    create_face_encoding,
    extract_frames,
    recognize_faces,
    scan_video_faces,
)


class FakeBackend:
    def __init__(self, encodings=None) -> None:
        self.encodings = encodings or {}

    def encode(self, image):
        return self.encodings.get(image, [])

    @staticmethod
    def distance(left, right):
        return cosine_distance(left, right)


class FakeCapture:
    def __init__(self, frames, fps=10) -> None:
        self.frames = frames
        self.fps = fps
        self.position = 0
        self.positions = []
        self.released = False

    def isOpened(self):
        return True

    def get(self, prop):
        return self.fps if prop == FakeCV2.CAP_PROP_FPS else len(self.frames)

    def set(self, prop, value):
        self.position = int(value)
        self.positions.append(self.position)
        return True

    def read(self):
        if self.position >= len(self.frames):
            return False, None
        return True, self.frames[self.position]

    def release(self):
        self.released = True


class FakeCV2:
    CAP_PROP_FPS = 1
    CAP_PROP_FRAME_COUNT = 2
    CAP_PROP_POS_FRAMES = 3

    def __init__(self, capture_factory):
        self.capture_factory = capture_factory
        self.captures = []

    def VideoCapture(self, path):
        capture = self.capture_factory(path)
        self.captures.append(capture)
        return capture


class FaceIndexTests(unittest.TestCase):
    def test_nearest_neighbor_and_threshold(self) -> None:
        index = FaceIndex(("Alice", "Bob"), ((1, 0), (0, 1)))
        match = index.match((0.99, 0.01), threshold=0.1)
        self.assertTrue(match.matched)
        self.assertEqual(match.name, "Alice")

        unknown = index.match((-1, 0), threshold=0.1)
        self.assertFalse(unknown.matched)
        self.assertIsNone(unknown.name)
        self.assertAlmostEqual(unknown.distance, 1)

    def test_empty_index_returns_unknown_without_min_error(self) -> None:
        match = FaceIndex().match((1, 0))
        self.assertFalse(match.matched)
        self.assertIsNone(match.distance)

    def test_index_validation(self) -> None:
        with self.assertRaisesRegex(ValueError, "same length"):
            FaceIndex(("Alice",), ())
        with self.assertRaisesRegex(ValueError, "same dimension"):
            FaceIndex(("Alice", "Bob"), ((1, 0), (1, 0, 0)))
        with self.assertRaisesRegex(ValueError, "dimension"):
            FaceIndex(("Alice",), ((1, 0),)).match((1, 0, 0))

    def test_json_round_trip_and_schema_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "faces.json"
            original = FaceIndex(("Alice",), ((0.1, 0.2),))
            original.save(path)
            self.assertEqual(FaceIndex.load(path), original)

            path.write_text(json.dumps({"version": 2}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "version"):
                FaceIndex.load(path)

            path.write_text(
                json.dumps({"version": 1, "names": [123], "embeddings": [0]}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "invalid data"):
                FaceIndex.load(path)


class VideoTests(unittest.TestCase):
    def setUp(self) -> None:
        handle = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        handle.close()
        self.video = Path(handle.name)

    def tearDown(self) -> None:
        self.video.unlink(missing_ok=True)

    def test_frame_sampling_seeks_instead_of_decoding_every_frame(self) -> None:
        cv2 = FakeCV2(lambda _path: FakeCapture(list(range(31)), fps=10))
        frames = extract_frames(
            self.video,
            interval_sec=1,
            cv2_module=cv2,
        )
        self.assertEqual(frames, [0, 10, 20, 30])
        self.assertEqual(cv2.captures[0].positions, [0, 10, 20, 30])
        self.assertTrue(cv2.captures[0].released)

    def test_scan_preserves_frame_metadata_and_multiple_faces(self) -> None:
        cv2 = FakeCV2(lambda _path: FakeCapture(list(range(21)), fps=10))
        backend = FakeBackend({0: [(1, 0), (0, 1)], 10: [], 20: [(1, 1)]})
        faces = scan_video_faces(
            self.video,
            frame_interval=1,
            backend=backend,
            cv2_module=cv2,
        )
        self.assertEqual([face.frame_number for face in faces], [0, 0, 20])
        self.assertEqual([face.timestamp_seconds for face in faces], [0, 0, 2])

    def test_recognize_faces_handles_known_and_unknown_faces(self) -> None:
        backend = FakeBackend({"image": [(1, 0), (-1, 0)]})
        names = recognize_faces(
            "image",
            [(1, 0)],
            ["Alice"],
            threshold=0.1,
            backend=backend,
        )
        self.assertEqual(names, ["Alice", "Unknown"])

    def test_create_encoding_requires_exactly_one_face(self) -> None:
        image = self.video.with_suffix(".jpg")
        image.touch()
        self.addCleanup(image.unlink)
        with self.assertRaisesRegex(ValueError, "found 2"):
            create_face_encoding(
                image,
                backend=FakeBackend({image: [(1, 0), (0, 1)]}),
            )


class BuildIndexTests(unittest.TestCase):
    def test_build_is_sorted_and_honors_video_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for person in ("Bob", "Alice"):
                folder = root / person
                folder.mkdir()
                (folder / "b.mp4").touch()
                (folder / "a.mp4").touch()

            cv2 = FakeCV2(lambda path: FakeCapture([Path(path).parent.name], fps=1))
            backend = FakeBackend(
                {
                    "Alice": [(1, 0)],
                    "Bob": [(0, 1)],
                }
            )
            index = build_face_index(
                root,
                max_videos_per_folder=1,
                frame_interval=1,
                backend=backend,
                cv2_module=cv2,
            )

            self.assertEqual(index.names, ("Alice", "Bob"))
            self.assertEqual(index.embeddings, ((1.0, 0.0), (0.0, 1.0)))
            self.assertEqual(len(cv2.captures), 2)


if __name__ == "__main__":
    unittest.main()
