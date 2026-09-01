from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from popularvideo_cli.client import (
    RuntimeClient,
    _iter_sse_events,
    _with_agent_delivery,
    artifact_ref_from_path,
    infer_artifact_kind,
)
from popularvideo_cli.cli import build_parser, run_agent_command
from popularvideo_cli.config import Settings, load_settings, render_options, update_brand_kit
from popularvideo_cli.dependencies import default_client_capabilities_from_dependencies
from popularvideo_cli.local_tools import _clean_cut_removals, _inverse_ranges, clean_cut
from popularvideo_cli.local_setup import setup_local_dependencies
from popularvideo_cli.enhancement import enhance_image
from popularvideo_cli.mcp import call_tool
from popularvideo_cli.schemas import TOOL_SCHEMAS
from popularvideo_cli.workflows import _first_subtitle_artifact


class RecordingClient(RuntimeClient):
    def __init__(self) -> None:
        super().__init__(Settings(api_key="ck_test"))
        self.requests: list[dict] = []

    def _request(self, method: str, path: str, **kwargs):
        self.requests.append({"method": method, "path": path, **kwargs})
        return {"status": "queued", "run_id": "run-1"}


class AgentContractTests(unittest.TestCase):
    def test_default_capabilities_advertise_image_staging_and_selection(self) -> None:
        report = {
            "ffmpeg": {"available": True, "subtitle_burn_available": True},
            "ffprobe": {"available": True},
            "local_voice_separation": {"available": False},
            "local_media_enhancement": {"available": True},
            "waifu2x": {"available": True},
        }
        with mock.patch(
            "popularvideo_cli.dependencies.local_dependency_report",
            return_value=report,
        ):
            capabilities = default_client_capabilities_from_dependencies()

        self.assertTrue(capabilities["can_stage_image_locally"])
        self.assertTrue(capabilities["supports_image_select_clarification"])
        self.assertTrue(capabilities["shell_ffmpeg_available"])
        self.assertTrue(capabilities["shell_ffprobe_available"])
        self.assertTrue(capabilities["shell_ffmpeg_subtitles_available"])
        self.assertTrue(capabilities["shell_video_encoder_available"])
        self.assertTrue(capabilities["shell_waifu2x_available"])

    def test_agent_run_sends_language_and_rich_context(self) -> None:
        client = RecordingClient()
        with tempfile.TemporaryDirectory() as temp_dir:
            video = Path(temp_dir) / "source.mp4"
            video.write_bytes(b"video")
            client.create_agent_run(
                "继续处理",
                context_files=[video],
                context_descriptors=[
                    {
                        "name": "generated.png",
                        "kind": "image",
                        "public_url": "https://cdn.example/generated.png",
                        "cloud_file_id": "cloud-1",
                        "metadata": {
                            "artifact_role": "generated_image",
                            "producer_step": "generate_image",
                        },
                    }
                ],
                app_language="zh",
            )

        body = client.requests[-1]["json_body"]
        self.assertEqual(body["app_language"], "zh")
        self.assertEqual(body["context_files"][0]["kind"], "video")
        self.assertEqual(body["context_files"][1]["cloud_file_id"], "cloud-1")
        self.assertEqual(body["context_files"][1]["metadata"]["producer_step"], "generate_image")

    def test_video_references_select_reference_generation_mode(self) -> None:
        client = RecordingClient()
        client.video("animate it", reference_image_urls=["https://cdn.example/ref.png"])
        body = client.requests[-1]["json_body"]
        self.assertEqual(body["generation_mode"], "reference")

    def test_agent_clarification_resolution_uses_in_place_runtime_route(self) -> None:
        client = RecordingClient()
        client.resolve_agent_clarification(
            "run-1",
            clarification_id="dub_reference_quality:synthesize",
            option_value="merge_primary",
        )

        request = client.requests[-1]
        self.assertEqual(request["method"], "POST")
        self.assertEqual(
            request["path"],
            "/v1/agent/runs/run-1/clarification-results",
        )
        self.assertEqual(
            request["json_body"],
            {
                "clarification_id": "dub_reference_quality:synthesize",
                "option_value": "merge_primary",
            },
        )

    def test_mcp_agent_cancel_dispatches_to_runtime(self) -> None:
        runtime = mock.Mock()
        runtime.cancel_agent_run.return_value = {
            "run_id": "run-1",
            "status": "failed",
            "error": {"code": "cancelled", "message": "Task stopped."},
        }
        with mock.patch(
            "popularvideo_cli.mcp.load_settings",
            return_value=Settings(api_key="ck_test"),
        ), mock.patch("popularvideo_cli.mcp.RuntimeClient", return_value=runtime):
            result = call_tool("agent_cancel", {"run_id": "run-1"})

        runtime.cancel_agent_run.assert_called_once_with("run-1")
        self.assertEqual(result["error"]["code"], "cancelled")

    def test_artifact_kind_is_inferred_from_extension(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            subtitle = Path(temp_dir) / "translated.srt"
            subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
            artifact = artifact_ref_from_path(
                subtitle,
                metadata={"artifact_role": "translated_subtitle"},
            )
        self.assertEqual(artifact["kind"], "subtitle")
        self.assertEqual(artifact["metadata"]["artifact_role"], "translated_subtitle")

    def test_translated_subtitle_artifact_is_preferred(self) -> None:
        selected = _first_subtitle_artifact(
            [
                {
                    "name": "source.srt",
                    "kind": "subtitle",
                    "path": "/tmp/source.srt",
                    "metadata": {"artifact_role": "source_subtitle"},
                },
                {
                    "name": "translated.srt",
                    "kind": "subtitle",
                    "path": "/tmp/translated.srt",
                    "metadata": {"artifact_role": "translated_subtitle"},
                },
            ]
        )
        self.assertEqual(selected, "/tmp/translated.srt")

    def test_local_tool_report_infers_kind_and_preserves_lineage(self) -> None:
        class ReportClient:
            result = None

            def report_local_tool_result(self, run_id, result):
                self.result = result
                return result

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "translated.srt"
            output.write_text("subtitle", encoding="utf-8")
            args = build_parser().parse_args(
                [
                    "agent",
                    "report-tool-result",
                    "run-1",
                    "--tool-call-id",
                    "call-1",
                    "--status",
                    "done",
                    "--artifact-path",
                    str(output),
                    "--artifact-metadata-json",
                    '{"artifact_role":"translated_subtitle","producer_step":"translate_subtitle"}',
                ]
            )
            client = ReportClient()
            result = run_agent_command(args, client)

        self.assertEqual(result["artifacts"][0]["kind"], "subtitle")
        self.assertEqual(result["artifacts"][0]["metadata"]["artifact_role"], "translated_subtitle")

    def test_agent_completion_classifies_delivery_artifacts(self) -> None:
        payload = _with_agent_delivery(
            {
                "completion": {
                    "message": "English dubbed version is ready.",
                    "primary_artifact_ids": ["video-1"],
                    "supporting_artifact_ids": ["subtitle-1"],
                },
                "artifacts": [
                    {
                        "id": "audio-1",
                        "name": "dubbed.wav",
                        "kind": "audio",
                        "metadata": {"artifact_role": "dubbed_audio"},
                    },
                    {
                        "id": "subtitle-1",
                        "name": "translated.srt",
                        "kind": "subtitle",
                        "metadata": {"artifact_role": "translated_subtitle"},
                    },
                    {
                        "id": "video-1",
                        "name": "dubbed.mp4",
                        "kind": "video",
                        "metadata": {"artifact_role": "dubbed_video"},
                    },
                ],
            }
        )
        self.assertEqual(payload["completion_message"], "English dubbed version is ready.")
        self.assertIsNone(payload["completion_title"])
        self.assertEqual([item["id"] for item in payload["primary_artifacts"]], ["video-1"])
        self.assertEqual([item["id"] for item in payload["supporting_artifacts"]], ["subtitle-1"])
        self.assertEqual([item["id"] for item in payload["intermediate_artifacts"]], ["audio-1"])

    def test_agent_delivery_excludes_source_reference_subtitle_from_primary(self) -> None:
        payload = _with_agent_delivery(
            {
                "completion": {"primary_artifact_ids": ["reference-1"]},
                "artifacts": [
                    {
                        "id": "subtitle-1",
                        "name": "captions.srt",
                        "kind": "subtitle",
                        "metadata": {"artifact_role": "source_subtitle"},
                    },
                    {
                        "id": "reference-1",
                        "name": "source.reference.srt",
                        "kind": "subtitle",
                        "metadata": {
                            "artifact_role": "source_reference_subtitle",
                            "plan_output_excluded": "true",
                        },
                    },
                ]
            }
        )

        self.assertEqual(payload["primary_artifacts"], [])
        self.assertEqual(
            [item["id"] for item in payload["intermediate_artifacts"]],
            ["subtitle-1", "reference-1"],
        )

    def test_agent_delivery_keeps_raw_web_query_supporting_only(self) -> None:
        payload = _with_agent_delivery(
            {
                "completion": {
                    "message": "Cited answer.",
                    "primary_artifact_ids": ["web-raw-1"],
                },
                "artifacts": [
                    {
                        "id": "web-raw-1",
                        "name": "web-query.json",
                        "kind": "document",
                        "metadata": {"artifact_role": "web_query_raw"},
                    }
                ],
            }
        )

        self.assertEqual(payload["completion_message"], "Cited answer.")
        self.assertEqual(payload["primary_artifacts"], [])
        self.assertEqual(
            [item["id"] for item in payload["supporting_artifacts"]],
            ["web-raw-1"],
        )

    def test_image_kind_supports_agent_image_select_formats(self) -> None:
        for extension in (".png", ".heic", ".tiff", ".bmp"):
            with self.subTest(extension=extension):
                self.assertEqual(infer_artifact_kind(Path(f"logo{extension}")), "image")

    def test_local_tool_report_can_stage_non_video_for_cloud_model(self) -> None:
        class ReportClient:
            def upload_agent_artifact(self, path, kind=None, metadata=None):
                return {
                    "name": path.name,
                    "kind": kind or "audio",
                    "path": str(path),
                    "url": "https://cdn.example.test/source.m4a",
                    "cloud_file_id": "cloud-audio-1",
                    "metadata": {
                        **(metadata or {}),
                        "cloud_accessible": "true",
                        "agent_server_input": "true",
                    },
                }

            def report_local_tool_result(self, run_id, result):
                return result

        with tempfile.TemporaryDirectory() as temp_dir:
            audio = Path(temp_dir) / "source.m4a"
            audio.write_bytes(b"audio")
            args = build_parser().parse_args(
                [
                    "agent",
                    "report-tool-result",
                    "run-1",
                    "--tool-call-id",
                    "stage-audio-1",
                    "--status",
                    "done",
                    "--artifact-path",
                    str(audio),
                    "--upload-for-cloud-model-input",
                ]
            )
            result = run_agent_command(args, ReportClient())

        self.assertEqual(result["artifacts"][0]["cloud_file_id"], "cloud-audio-1")
        self.assertEqual(result["output_metadata"]["agent_server_input"], "true")

    def test_agent_sse_parser_preserves_cursor_and_public_event_type(self) -> None:
        events = list(
            _iter_sse_events(
                [
                    "id: 1700000000000-1",
                    "event: reasoning_delta",
                    'data: {"run_id":"run-1","event_id":"1700000000000-1","type":"reasoning_delta","text":"Checking inputs."}',
                    "",
                    "event: done",
                    "data: {}",
                    "",
                ]
            )
        )
        self.assertEqual(events[0]["type"], "reasoning_delta")
        self.assertEqual(events[0]["event_id"], "1700000000000-1")
        self.assertEqual(events[0]["text"], "Checking inputs.")
        self.assertEqual(events[1]["type"], "done")

    def test_new_cli_surfaces_parse_deconstruction_exports_and_events(self) -> None:
        parser = build_parser()
        deconstruct = parser.parse_args(
            [
                "deconstruct-video",
                "/tmp/source.mp4",
                "--replacement-reference",
                "product=/tmp/product.png",
                "--language",
                "en",
                "--analysis-scope",
                "camera movement",
            ]
        )
        image = parser.parse_args(
            [
                "image",
                "restyle it",
                "--reference-image-url",
                "/tmp/product.png",
                "--timeout",
                "300",
            ]
        )
        project = parser.parse_args(
            [
                "export-editor-project",
                "/tmp/source.mp4",
                "--target",
                "premiere",
            ]
        )
        events = parser.parse_args(
            ["agent", "events", "run-1", "--last-event-id", "1-0"]
        )
        clarify = parser.parse_args(
            [
                "agent",
                "clarify",
                "run-1",
                "--clarification-id",
                "translation_mode:0",
                "--value",
                "voice",
                "--wait",
            ]
        )
        clean = parser.parse_args(
            [
                "clean-cut",
                "/tmp/source.mp4",
                "--plan-only",
                "--minimum-silence",
                "0.6",
            ]
        )
        shorten = parser.parse_args(
            [
                "shorten",
                "/tmp/source.mp4",
                "--selection-instruction",
                "Prefer demos",
                "--output-language",
                "ja",
            ]
        )
        cancel = parser.parse_args(["agent", "cancel", "run-1"])

        self.assertEqual(deconstruct.command, "deconstruct-video")
        self.assertEqual(
            deconstruct.replacement_reference,
            ["product=/tmp/product.png"],
        )
        self.assertEqual(deconstruct.language, "en")
        self.assertEqual(deconstruct.analysis_scope, "camera movement")
        self.assertEqual(image.reference_image_urls, ["/tmp/product.png"])
        self.assertEqual(image.timeout, 300)
        self.assertEqual(project.target, "premiere")
        self.assertEqual(events.agent_command, "events")
        self.assertEqual(events.last_event_id, "1-0")
        self.assertEqual(clarify.agent_command, "clarify")
        self.assertEqual(clarify.value, "voice")
        self.assertTrue(clarify.wait)
        self.assertTrue(clean.plan_only)
        self.assertEqual(clean.minimum_silence_sec, 0.6)
        self.assertEqual(shorten.output_language, "ja")
        self.assertEqual(shorten.selection_instruction, "Prefer demos")
        self.assertEqual(cancel.agent_command, "cancel")
        self.assertEqual(
            TOOL_SCHEMAS["clean_cut"]["input_schema"]["properties"]["minimum_silence_sec"]["default"],
            0.85,
        )
        self.assertIn("agent_cancel", TOOL_SCHEMAS)
        context_kinds = TOOL_SCHEMAS["agent_run"]["input_schema"]["properties"][
            "context_descriptors"
        ]["items"]["properties"]["kind"]["enum"]
        self.assertIn("video_analysis", context_kinds)


class BrandKitAndEditingTests(unittest.TestCase):
    def test_dependency_setup_surfaces_enhancement_configuration(self) -> None:
        report = {
            "ffmpeg": {"subtitle_burn_available": True, "path": "/ffmpeg"},
            "ffprobe": {"available": True},
            "local_voice_separation": {"available": True},
            "local_media_enhancement": {"available": False},
            "waifu2x": {"path": None},
        }
        with mock.patch(
            "popularvideo_cli.local_setup.local_dependency_report",
            return_value=report,
        ):
            result = setup_local_dependencies(
                dry_run=True,
                with_enhancement=True,
                interactive=False,
            )

        enhancement = next(
            item for item in result["actions"] if item["component"] == "media_enhancement"
        )
        self.assertEqual(enhancement["status"], "would_configure")
        self.assertIn("CINLINK_WAIFU2X_DIR", enhancement["message"])

    def test_image_enhancement_returns_typed_local_artifact(self) -> None:
        png_header = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (64).to_bytes(4, "big") + (48).to_bytes(4, "big")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            binary_root = root / "waifu2x"
            binary_root.mkdir()
            binary = binary_root / "waifu2x-ncnn-vulkan"
            binary.write_text("binary", encoding="utf-8")
            binary.chmod(0o755)
            (binary_root / "models-upconv_7_photo").mkdir()
            source = root / "source.png"
            source.write_bytes(png_header)

            def fake_run(command, message):
                output = Path(command[command.index("-o") + 1])
                output.write_bytes(png_header)
                return mock.Mock(stdout="", stderr="", returncode=0)

            with mock.patch(
                "popularvideo_cli.enhancement.resolve_waifu2x",
                return_value=binary,
            ), mock.patch("popularvideo_cli.enhancement._run", side_effect=fake_run):
                result = enhance_image(source, out=root / "out")

        self.assertEqual(result["width"], 64)
        self.assertEqual(result["height"], 48)
        self.assertEqual(result["artifacts"][0]["metadata"]["artifact_role"], "enhanced_image")
        self.assertIn("enhance_image", TOOL_SCHEMAS)
        self.assertIn("enhance_video", TOOL_SCHEMAS)

    def test_brand_kit_persists_and_applies_with_explicit_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            with mock.patch.dict(os.environ, {"CINLINK_CLI_CONFIG": str(config_path)}, clear=False):
                settings = Settings(api_key="ck_test")
                update_brand_kit(
                    settings,
                    {
                        "enabled": True,
                        "font_name": "Inter",
                        "font_color": "#22AAEE",
                        "watermark_text": "CinLink",
                    },
                )
                loaded = load_settings()
                effective = render_options(loaded, {"font_color": "#FFFFFF"})

        self.assertEqual(effective["font_name"], "Inter")
        self.assertEqual(effective["font_color"], "#FFFFFF")
        self.assertEqual(effective["watermark_text"], "CinLink")

    def test_clean_cut_keeps_natural_pause_edges(self) -> None:
        removals = _clean_cut_removals(
            [(1.0, 3.0), (5.0, 5.3)],
            source_duration_sec=8.0,
            retained_pause_sec=0.24,
            minimum_removal_sec=0.18,
        )
        keep = _inverse_ranges(removals, 8.0)
        self.assertEqual(removals, [(1.12, 2.88)])
        self.assertEqual(keep, [(0.0, 1.12), (2.88, 8.0)])

    def test_clean_cut_plan_returns_indexed_candidates_without_rendering(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            video = Path(temp_dir) / "source.mp4"
            video.write_bytes(b"video")
            with mock.patch(
                "popularvideo_cli.local_tools.probe_video_duration",
                return_value=10.0,
            ), mock.patch(
                "popularvideo_cli.local_tools.detect_silence",
                return_value=[(1.0, 3.0), (5.0, 7.0)],
            ), mock.patch("popularvideo_cli.local_tools._render_segment") as render:
                result = clean_cut(video, plan_only=True)

        self.assertEqual(result["status"], "planned")
        self.assertFalse(result["changed"])
        self.assertTrue(result["has_candidates"])
        self.assertIsNone(result["video_output_path"])
        self.assertEqual(
            [item["index"] for item in result["candidate_removed_ranges"]],
            [0, 1],
        )
        self.assertEqual(result["artifacts"], [])
        render.assert_not_called()

    def test_clean_cut_exports_only_selected_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video = root / "source.mp4"
            video.write_bytes(b"video")

            def fake_render(_source, _start, _end, output_path):
                output_path.write_bytes(b"segment")

            def fake_concat(_segments, output_path):
                output_path.write_bytes(b"output")

            with mock.patch(
                "popularvideo_cli.local_tools.probe_video_duration",
                return_value=10.0,
            ), mock.patch(
                "popularvideo_cli.local_tools.detect_silence",
                return_value=[(1.0, 3.0), (5.0, 7.0)],
            ), mock.patch(
                "popularvideo_cli.local_tools._render_segment",
                side_effect=fake_render,
            ), mock.patch(
                "popularvideo_cli.local_tools._concat_segments",
                side_effect=fake_concat,
            ):
                result = clean_cut(
                    video,
                    out=root / "out",
                    selected_removal_indexes=[1],
                )

        self.assertTrue(result["changed"])
        self.assertEqual(result["selected_removal_indexes"], [1])
        self.assertEqual(len(result["candidate_removed_ranges"]), 2)
        self.assertAlmostEqual(result["removed_ranges"][0]["start_sec"], 5.12)
        self.assertAlmostEqual(result["removed_ranges"][0]["end_sec"], 6.88)
        self.assertEqual(len(result["artifacts"]), 1)


if __name__ == "__main__":
    unittest.main()
