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
)
from popularvideo_cli.cli import build_parser, run_agent_command
from popularvideo_cli.config import Settings, load_settings, render_options, update_brand_kit
from popularvideo_cli.local_tools import _clean_cut_removals, _inverse_ranges
from popularvideo_cli.workflows import _first_subtitle_artifact


class RecordingClient(RuntimeClient):
    def __init__(self) -> None:
        super().__init__(Settings(api_key="ck_test"))
        self.requests: list[dict] = []

    def _request(self, method: str, path: str, **kwargs):
        self.requests.append({"method": method, "path": path, **kwargs})
        return {"status": "queued", "run_id": "run-1"}


class AgentContractTests(unittest.TestCase):
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


class BrandKitAndEditingTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
