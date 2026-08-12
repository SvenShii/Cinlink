from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from popularvideo_cli.client import RuntimeClient
from popularvideo_cli.config import Settings
from popularvideo_cli.errors import CliError


class RuntimeClientMediaUploadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.video = self.root / "source.mp4"
        self.video.write_bytes(b"video")
        self.subtitle = self.root / "translated.srt"
        self.subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
        self.reference_audio = self.root / "speaker.wav"
        self.reference_audio.write_bytes(b"audio")
        self.reference_image = self.root / "reference.png"
        self.reference_image.write_bytes(b"image")
        self.client = RuntimeClient(Settings(api_key="test-key"))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @staticmethod
    def _fake_extract(_video_path: Path, audio_path: Path) -> None:
        audio_path.write_bytes(b"extracted-audio")

    def test_translate_video_uploads_extracted_audio(self) -> None:
        uploaded: list[tuple[str, str, bool]] = []

        def fake_multipart(path: str, input_path: Path, _fields: dict) -> dict:
            uploaded.append((path, input_path.suffix, input_path.exists()))
            return {"status": "done", "outputs": {}}

        with patch("popularvideo_cli.client._extract_audio_for_upload", side_effect=self._fake_extract), patch.object(
            self.client, "_multipart", side_effect=fake_multipart
        ):
            result = self.client.translate(self.video, to_lang="en")

        self.assertEqual(uploaded, [("/v1/translate", ".m4a", True)])
        self.assertEqual(result["source_video_path"], str(self.video.resolve()))
        self.assertEqual(result["hosted_input_kind"], "audio")

    def test_summarize_and_shorten_keep_video_local(self) -> None:
        uploaded: list[tuple[str, str, bool]] = []
        requests: list[tuple[str, dict]] = []

        def fake_multipart(path: str, input_path: Path, _fields: dict) -> dict:
            uploaded.append((path, input_path.suffix, input_path.exists()))
            return {"status": "done"}

        def fake_request(_method: str, path: str, **kwargs: object) -> dict:
            requests.append((path, kwargs))
            if path == "/v1/agent/files":
                return {"cloud_file_id": "cloud-audio-1"}
            return {"status": "done"}

        with patch("popularvideo_cli.client._extract_audio_for_upload", side_effect=self._fake_extract), patch.object(
            self.client, "_multipart", side_effect=fake_multipart
        ), patch.object(
            self.client, "_request", side_effect=fake_request
        ):
            summary = self.client.summarize(self.video)
            short_plan = self.client.shorten(self.video)

        self.assertEqual(uploaded, [("/v1/summarize", ".m4a", True)])
        self.assertEqual(
            [path for path, _ in requests],
            ["/v1/agent/files", "/v1/shorten"],
        )
        self.assertEqual(
            requests[-1][1]["files"],
            {"cloud_file_id": (None, "cloud-audio-1")},
        )
        self.assertEqual(summary["source_video_path"], str(self.video.resolve()))
        self.assertEqual(short_plan["source_video_path"], str(self.video.resolve()))

    def test_shorten_falls_back_when_cloud_audio_references_are_unsupported(self) -> None:
        uploaded: list[tuple[str, str, bool]] = []

        def fake_multipart(path: str, input_path: Path, _fields: dict) -> dict:
            uploaded.append((path, input_path.suffix, input_path.exists()))
            return {"status": "done"}

        with patch(
            "popularvideo_cli.client._extract_audio_for_upload",
            side_effect=self._fake_extract,
        ), patch.object(
            self.client,
            "_upload_agent_file",
            side_effect=CliError(
                "job_not_found",
                "The requested remote resource was not found.",
                {"status_code": 404},
            ),
        ), patch.object(self.client, "_multipart", side_effect=fake_multipart):
            result = self.client.shorten(self.video)

        self.assertEqual(uploaded, [("/v1/shorten", ".m4a", True)])
        self.assertEqual(result["source_video_path"], str(self.video.resolve()))

    def test_shorten_falls_back_when_runtime_rejects_cloud_file_field(self) -> None:
        uploaded: list[tuple[str, str, bool]] = []

        def fake_request(_method: str, path: str, **_kwargs: object) -> dict:
            if path == "/v1/agent/files":
                return {"cloud_file_id": "cloud-audio-1"}
            raise CliError("invalid_input", "Missing upload file for shorten request.")

        def fake_multipart(path: str, input_path: Path, _fields: dict) -> dict:
            uploaded.append((path, input_path.suffix, input_path.exists()))
            return {"status": "done"}

        with patch(
            "popularvideo_cli.client._extract_audio_for_upload",
            side_effect=self._fake_extract,
        ), patch.object(
            self.client, "_request", side_effect=fake_request
        ), patch.object(
            self.client, "_multipart", side_effect=fake_multipart
        ):
            result = self.client.shorten(self.video)

        self.assertEqual(uploaded, [("/v1/shorten", ".m4a", True)])
        self.assertEqual(result["source_video_path"], str(self.video.resolve()))

    def test_dub_video_uploads_audio_and_speaker_references(self) -> None:
        submitted: dict = {}

        def fake_submit(audio_path: Path, subtitle_path: Path, **kwargs: object) -> dict:
            submitted.update(
                audio_suffix=audio_path.suffix,
                audio_exists=audio_path.exists(),
                subtitle_path=subtitle_path,
                reference_audio_paths=kwargs.get("reference_audio_paths"),
            )
            return {"status": "done", "dubbed_audio_path": "hosted.wav"}

        with patch("popularvideo_cli.client._extract_audio_for_upload", side_effect=self._fake_extract), patch.object(
            self.client, "_submit_dub_audio", side_effect=fake_submit
        ):
            result = self.client.dub(
                self.video,
                self.subtitle,
                reference_audio_paths={"speaker_0": self.reference_audio},
            )

        self.assertEqual(submitted["audio_suffix"], ".m4a")
        self.assertTrue(submitted["audio_exists"])
        self.assertEqual(submitted["subtitle_path"], self.subtitle.resolve())
        self.assertEqual(submitted["reference_audio_paths"], {"speaker_0": self.reference_audio.resolve()})
        self.assertEqual(result["source_video_path"], str(self.video.resolve()))
        self.assertTrue(result["requires_local_video_composition"])

    def test_dub_auto_discovers_sibling_reference_subtitle(self) -> None:
        reference = self.root / "source.reference.srt"
        reference.write_text(
            "1\n00:00:00,000 --> 00:00:01,000\n[Speaker 0] Hello\n",
            encoding="utf-8",
        )
        submitted: dict = {}

        def fake_submit(_audio_path: Path, _subtitle_path: Path, **kwargs: object) -> dict:
            submitted["reference_subtitle"] = kwargs.get("reference_subtitle")
            return {"status": "done"}

        with patch(
            "popularvideo_cli.client._extract_audio_for_upload",
            side_effect=self._fake_extract,
        ), patch.object(self.client, "_submit_dub_audio", side_effect=fake_submit):
            result = self.client.dub(self.video, self.subtitle)

        self.assertEqual(submitted["reference_subtitle"], reference.resolve())
        self.assertEqual(result["source_reference_subtitle_path"], str(reference.resolve()))
        self.assertTrue(result["reference_subtitle_auto_discovered"])

    def test_structured_agent_intent_enables_trusted_routing(self) -> None:
        with patch.object(self.client, "_request", return_value={"run_id": "run-1"}) as request:
            self.client.create_agent_run(
                "Add English subtitles",
                context_files=[self.video],
                task_intent="add_subtitles",
            )

        payload = request.call_args.kwargs["json_body"]
        self.assertTrue(payload["client_capabilities"]["trusted_fixed_workflow_routing"])

    def test_video_uploads_local_reference_images_before_generation(self) -> None:
        requests: list[tuple[str, dict]] = []
        upload_count = 0

        def fake_request(_method: str, path: str, **kwargs: object) -> dict:
            nonlocal upload_count
            requests.append((path, kwargs))
            if path == "/v1/reference-images":
                upload_count += 1
                return {
                    "reference_image_url": (
                        f"https://cdn.example/reference-{upload_count}.png"
                    )
                }
            return {"status": "done"}

        with patch.object(self.client, "_request", side_effect=fake_request):
            self.client.video(
                "replace the product",
                first_frame_image_url=str(self.reference_image),
                reference_image_urls=[str(self.reference_image)],
            )

        self.assertEqual(
            [path for path, _ in requests],
            ["/v1/reference-images", "/v1/reference-images", "/v1/video"],
        )
        body = requests[-1][1]["json_body"]
        self.assertEqual(body["generation_mode"], "reference")
        self.assertEqual(
            body["first_frame_image_url"],
            "https://cdn.example/reference-1.png",
        )
        self.assertEqual(
            body["reference_image_urls"],
            ["https://cdn.example/reference-2.png"],
        )

    def test_image_uploads_local_references_and_waits_for_job(self) -> None:
        requests: list[tuple[str, dict]] = []

        def fake_request(_method: str, path: str, **kwargs: object) -> dict:
            requests.append((path, kwargs))
            if path == "/v1/reference-images":
                return {"reference_image_url": "https://cdn.example/reference.png"}
            return {"job_id": "image-job", "status": "queued"}

        with patch.object(
            self.client, "_request", side_effect=fake_request
        ), patch.object(
            self.client,
            "wait_for_job",
            return_value={"status": "done", "outputs": {}},
        ) as wait:
            result = self.client.image(
                "restyle this product",
                reference_image_urls=[str(self.reference_image)],
                timeout=123,
            )

        self.assertEqual(
            [path for path, _ in requests],
            ["/v1/reference-images", "/v1/image"],
        )
        self.assertEqual(
            requests[-1][1]["json_body"]["reference_image_urls"],
            ["https://cdn.example/reference.png"],
        )
        wait.assert_called_once_with("image-job", 123)
        self.assertEqual(result["status"], "done")

    def test_agent_context_marks_timed_subtitle_reusable_for_video(self) -> None:
        with patch.object(
            self.client, "_request", return_value={"run_id": "run-1"}
        ) as request:
            self.client.create_agent_run(
                "Shorten this using the existing subtitles",
                context_files=[self.video, self.subtitle],
            )

        context = request.call_args.kwargs["json_body"]["context_files"]
        video = next(item for item in context if item["kind"] == "video")
        subtitle = next(item for item in context if item["kind"] == "subtitle")
        self.assertEqual(video["metadata"]["selection_scope"], "current_submission")
        self.assertEqual(video["metadata"]["input_priority"], "highest")
        self.assertEqual(subtitle["metadata"]["selection_scope"], "current_submission")
        self.assertEqual(subtitle["metadata"]["input_priority"], "highest")
        self.assertEqual(subtitle["metadata"]["subtitle_has_usable_cues"], "true")
        self.assertEqual(subtitle["metadata"]["subtitle_reuse_eligible"], "true")
        self.assertEqual(
            subtitle["metadata"]["subtitle_source_video_name"],
            self.video.name,
        )

    def test_agent_context_descriptor_is_not_implicitly_current_submission(self) -> None:
        with patch.object(
            self.client, "_request", return_value={"run_id": "run-1"}
        ) as request:
            self.client.create_agent_run(
                "Continue with the previous artifact",
                context_descriptors=[
                    {
                        "id": "historical-video",
                        "name": "historical.mp4",
                        "kind": "video",
                        "metadata": {"artifact_role": "source_video"},
                    }
                ],
            )

        descriptor = request.call_args.kwargs["json_body"]["context_files"][0]
        self.assertEqual(descriptor["metadata"]["artifact_role"], "source_video")
        self.assertNotIn("selection_scope", descriptor["metadata"])
        self.assertNotIn("input_priority", descriptor["metadata"])

    def test_agent_context_rejects_subtitle_timeline_past_video_end(self) -> None:
        self.subtitle.write_text(
            "1\n00:00:19,000 --> 00:00:20,000\nToo late\n",
            encoding="utf-8",
        )
        with patch(
            "popularvideo_cli.client._probe_media_duration", return_value=5.0
        ), patch.object(
            self.client, "_request", return_value={"run_id": "run-1"}
        ) as request:
            self.client.create_agent_run(
                "Use an existing subtitle only when it matches",
                context_files=[self.video, self.subtitle],
            )

        context = request.call_args.kwargs["json_body"]["context_files"]
        subtitle = next(item for item in context if item["kind"] == "subtitle")
        self.assertEqual(subtitle["metadata"]["subtitle_reuse_eligible"], "false")
        self.assertEqual(subtitle["metadata"]["subtitle_timeline_mismatch"], "true")
        self.assertEqual(subtitle["metadata"]["source_video_duration_sec"], "5.000")

    def test_structured_agent_clarification_preserves_task_frame_and_context(self) -> None:
        previous = {
            "run_id": "run-1",
            "conversation_id": "conversation-1",
            "status": "requires_user_input",
            "mode": "execute",
            "app_language": "zh-Hans",
            "conversation_state": {"last_translation_target_language": "zho"},
            "task_frame": {
                "workflow_decision": {
                    "decision_type": "ask_user",
                    "workflow_id": "translate_subtitle",
                    "missing_slots": ["translation_mode"],
                }
            },
            "context_files": [
                {
                    "id": "video-1",
                    "name": self.video.name,
                    "kind": "video",
                    "local_path": str(self.video),
                    "metadata": {},
                }
            ],
            "clarifications": [
                {
                    "id": "translation_mode:0",
                    "slot_key": "translation_mode",
                    "question": "字幕版还是配音版？",
                    "input_kind": "single_select",
                    "options": [
                        {"value": "subtitle", "label": "中文字幕版"},
                        {"value": "voice", "label": "中文配音版"},
                    ],
                }
            ],
        }
        with patch.object(
            self.client, "get_agent_run", return_value=previous
        ), patch.object(
            self.client,
            "create_agent_run",
            return_value={"run_id": "run-2", "status": "queued"},
        ) as create:
            result = self.client.continue_agent_clarification(
                "run-1",
                value="voice",
            )

        self.assertEqual(create.call_args.args[0], "中文配音版")
        self.assertEqual(create.call_args.kwargs["conversation_id"], "conversation-1")
        self.assertEqual(
            create.call_args.kwargs["task_parameters"],
            {
                "translation_mode": "voice",
                "__clarification_reply_language": "zh-Hans",
            },
        )
        self.assertEqual(create.call_args.kwargs["task_intent"], None)
        frame = create.call_args.kwargs["conversation_state"]["agent_task_frame_json"]
        self.assertEqual(frame.count("workflow_decision"), 1)
        self.assertEqual(create.call_args.kwargs["context_descriptors"][0]["id"], "video-1")
        self.assertEqual(result["continued_from_run_id"], "run-1")

    def test_agent_clarification_collects_all_answers_and_custom_duration(self) -> None:
        previous = {
            "run_id": "run-1",
            "conversation_id": "conversation-1",
            "status": "requires_user_input",
            "mode": "execute",
            "app_language": "zh",
            "conversation_state": {},
            "task_frame": {"workflow_decision": {"workflow_id": "shorten_video"}},
            "context_files": [],
            "clarifications": [
                {
                    "id": "target_duration_sec:0",
                    "slot_key": "target_duration_sec",
                    "workflow_id": "shorten_video",
                    "question": "目标时长？",
                    "input_kind": "single_select",
                    "options": [{"value": "60", "label": "60 秒"}],
                },
                {
                    "id": "require_audio:1",
                    "slot_key": "require_audio",
                    "workflow_id": "shorten_video",
                    "question": "保留声音？",
                    "input_kind": "single_select",
                    "options": [
                        {"value": "true", "label": "保留声音"},
                        {"value": "false", "label": "静音"},
                    ],
                },
            ],
        }
        with patch.object(
            self.client, "get_agent_run", return_value=previous
        ), patch.object(
            self.client,
            "create_agent_run",
            return_value={"run_id": "run-2", "status": "queued"},
        ) as create:
            result = self.client.continue_agent_clarification(
                "run-1",
                answers={"target_duration_sec": "1:30", "require_audio:1": "保留声音"},
            )

        self.assertEqual(create.call_args.args[0], "90；保留声音")
        self.assertEqual(create.call_args.kwargs["task_intent"], "shorten_video")
        self.assertEqual(
            create.call_args.kwargs["task_parameters"],
            {
                "target_duration_sec": "90",
                "require_audio": "true",
                "__clarification_reply_language": "zh",
            },
        )
        self.assertEqual(len(result["answered_clarifications"]), 2)
        self.assertIsNone(result["answered_clarification"])

    def test_agent_file_clarification_resolves_name_to_entity_id(self) -> None:
        previous = {
            "run_id": "run-1",
            "conversation_id": "conversation-1",
            "status": "requires_user_input",
            "mode": "execute",
            "app_language": "en",
            "conversation_state": {},
            "task_frame": {"workflow_decision": {"workflow_id": "summarize_video"}},
            "context_files": [
                {
                    "id": "context-video-1",
                    "entity_id": "entity-video-1",
                    "name": "Demo Clip.mp4",
                    "kind": "video",
                    "metadata": {},
                }
            ],
            "clarifications": [
                {
                    "id": "media_id:0",
                    "slot_key": "media_id",
                    "workflow_id": "summarize_video",
                    "question": "Which video?",
                    "input_kind": "text",
                    "options": [],
                }
            ],
        }
        with patch.object(
            self.client, "get_agent_run", return_value=previous
        ), patch.object(
            self.client,
            "create_agent_run",
            return_value={"run_id": "run-2", "status": "queued"},
        ) as create:
            self.client.continue_agent_clarification(
                "run-1",
                answer="Demo Clip.mp4",
            )

        parameters = create.call_args.kwargs["task_parameters"]
        self.assertEqual(parameters["media_id"], "entity-video-1")
        self.assertEqual(parameters["selected_entity_id"], "entity-video-1")
        self.assertEqual(parameters["video_entity_id"], "entity-video-1")
        descriptor = create.call_args.kwargs["context_descriptors"][0]
        self.assertEqual(descriptor["metadata"]["selection_scope"], "current_submission")

    def test_failed_job_preserves_safe_retry_diagnostics(self) -> None:
        with patch.object(
            self.client,
            "_request",
            return_value={
                "status": "failed",
                "error": {
                    "code": "provider_rejected",
                    "message": "The provider rejected this request.",
                    "processing_stage": "generate_video",
                    "provider": "example-provider",
                    "request_id": "provider-request-1",
                    "retryable": False,
                    "private_debug": "must not escape",
                },
            },
        ):
            with self.assertRaises(CliError) as raised:
                self.client.wait_for_job("job-1", timeout=1)

        self.assertEqual(raised.exception.details["retryable"], False)
        self.assertEqual(raised.exception.details["provider"], "example-provider")
        self.assertNotIn("private_debug", raised.exception.details)


if __name__ == "__main__":
    unittest.main()
