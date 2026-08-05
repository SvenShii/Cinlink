from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from popularvideo_cli.deconstruction import (
    _deconstruct_request,
    combined_generation_prompt,
    generation_segments,
)
from popularvideo_cli.dependencies import resolve_ffmpeg_with_encoder
from popularvideo_cli.editor_exports import export_editor_project


class VideoDeconstructionTests(unittest.TestCase):
    def test_generation_segments_split_long_shot_and_merge_short_tail(self) -> None:
        segments = generation_segments(20.0, [])
        self.assertEqual(len(segments), 2)
        self.assertAlmostEqual(segments[0]["duration_sec"], 10.0)
        self.assertTrue(segments[1]["continues_previous"])

        merged = generation_segments(8.0, [6.0])
        self.assertEqual(len(merged), 1)
        self.assertAlmostEqual(merged[0]["duration_sec"], 8.0)

    def test_deconstruct_request_keeps_video_local_and_encodes_frames(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video = root / "source.mp4"
            video.write_bytes(b"local-video")
            frames = []
            for role in ("first", "middle", "last"):
                path = root / f"{role}.jpg"
                path.write_bytes(role.encode())
                frames.append(str(path))
            request = _deconstruct_request(
                video,
                5.0,
                "16:9",
                [
                    {
                        "index": 1,
                        "start_sec": 0.0,
                        "end_sec": 5.0,
                        "continues_previous": False,
                        "reference_frame_paths": frames,
                    }
                ],
                batch_index=1,
                batch_count=1,
                language="en",
                analysis_scope="camera motion and product presentation",
            )

        self.assertNotIn("video_path", request)
        self.assertEqual(len(request["frames"]), 3)
        self.assertEqual(request["frames"][0]["role"], "first")
        self.assertEqual(request["shots"][0]["frame_indexes"], [1, 2, 3])
        self.assertEqual(request["language"], "en")
        self.assertEqual(
            request["analysis_scope"],
            "camera motion and product presentation",
        )

    def test_replacement_prompt_names_roles_and_continuity(self) -> None:
        prompt = combined_generation_prompt(
            "Match the source pacing.",
            {
                "index": 2,
                "generation_duration_sec": 5,
                "generation_prompt": "A close-up product reveal.",
                "negative_prompt": "flicker",
            },
            continuing=True,
            has_timeline_reference=True,
            replacements=[
                {"path": "/tmp/person.png", "role": "person"},
                {"path": "/tmp/product.png", "role": "product"},
            ],
        )
        self.assertIn("previous clip's final frame", prompt)
        self.assertIn("Reference image 2", prompt)
        self.assertIn("Reference image 3", prompt)
        self.assertIn("main person's identity", prompt)
        self.assertIn("featured product's shape", prompt)


class FfmpegCapabilityTests(unittest.TestCase):
    def test_encoder_resolver_skips_incompatible_ffmpeg(self) -> None:
        bundled = Path("/tmp/cinlink-bundled-ffmpeg")
        system = Path("/tmp/system-ffmpeg")
        with patch(
            "popularvideo_cli.dependencies.ffmpeg_candidates",
            return_value=[bundled, system],
        ), patch(
            "popularvideo_cli.dependencies._is_executable",
            return_value=True,
        ), patch(
            "popularvideo_cli.dependencies._binary_works",
            return_value=True,
        ), patch(
            "popularvideo_cli.dependencies.ffmpeg_supports_encoder",
            side_effect=[False, True],
        ):
            resolved = resolve_ffmpeg_with_encoder("libmp3lame")

        self.assertEqual(resolved, system)


class EditorProjectExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.video = self.root / "source.mp4"
        self.video.write_bytes(b"video")
        self.subtitle = self.root / "source.srt"
        self.subtitle.write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nHello\n",
            encoding="utf-8",
        )
        self.audio = self.root / "translated.wav"
        self.audio.write_bytes(b"audio")
        self.metadata = {
            "duration_sec": 5.0,
            "width": 1280,
            "height": 720,
            "fps": 30.0,
            "timebase": 30,
        }

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_final_cut_export_writes_fcpxml_and_srt(self) -> None:
        with patch("popularvideo_cli.editor_exports._probe_media", return_value=self.metadata):
            result = export_editor_project(
                self.video,
                target="final-cut",
                subtitle_path=self.subtitle,
                out=self.root / "final-cut",
            )
        project = Path(result["project_output_path"])
        self.assertTrue(project.is_file())
        self.assertIn("<fcpxml", project.read_text(encoding="utf-8"))
        self.assertEqual(len(result["supporting_artifacts"]), 1)

    def test_capcut_export_writes_portable_package(self) -> None:
        with patch("popularvideo_cli.editor_exports._probe_media", return_value=self.metadata):
            result = export_editor_project(
                self.video,
                target="capcut",
                subtitle_path=self.subtitle,
                out=self.root / "capcut",
            )
        package = Path(result["package_path"])
        self.assertTrue((package / "cinlink-timeline.json").is_file())
        self.assertTrue((package / "media" / "source.mp4").is_file())
        self.assertTrue((package / "subtitles.srt").is_file())
        self.assertTrue((package / "README.txt").is_file())

    def test_final_cut_project_references_separate_audio(self) -> None:
        with patch(
            "popularvideo_cli.editor_exports._probe_media",
            return_value=self.metadata,
        ), patch(
            "popularvideo_cli.editor_exports._probe_duration",
            return_value=4.5,
        ):
            result = export_editor_project(
                self.video,
                target="final-cut",
                audio_path=self.audio,
                out=self.root / "final-cut-audio",
            )
        project_text = Path(result["project_output_path"]).read_text(
            encoding="utf-8"
        )
        self.assertIn(self.audio.resolve().as_uri(), project_text)
        self.assertIn('audioRole="dialogue"', project_text)


if __name__ == "__main__":
    unittest.main()
