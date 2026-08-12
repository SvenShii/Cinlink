from __future__ import annotations

from contextlib import ExitStack
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile
import time
from typing import Any
from uuid import uuid4

from .config import Settings
from .dependencies import resolve_ffmpeg, resolve_ffprobe
from .dependencies import default_client_capabilities_from_dependencies
from .errors import CliError, normalize_remote_error


_SAFE_JOB_ERROR_DETAIL_KEYS = (
    "processing_stage",
    "error_type",
    "error_code",
    "provider",
    "http_status",
    "request_id",
    "retryable",
)
_SUBTITLE_TIMESTAMP_PATTERN = re.compile(
    r"(\d+):(\d{2}):(\d{2})(?:[,.])(\d{1,3})"
)


class RuntimeClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/v1/health", auth=False)

    def transcribe(self, input_path: Path, lang: str = "auto", out: Path | None = None, timeout: float | None = None) -> dict[str, Any]:
        checked = require_existing_file(input_path)
        payload = self._multipart_audio_or_file(
            "/v1/transcribe",
            checked,
            {"source_lang": lang},
            temp_prefix="cinlink-transcribe-audio-",
        )
        result = self.wait_for_job(payload["job_id"], timeout or self.settings.timeout_sec)
        localized = self._localize_job_outputs(
            result,
            out or checked.parent / f"{checked.stem}.cinlink",
            ("subtitle_path", "transcript_path", "source_reference_subtitle_path", "elevenlabs_payload_path"),
        )
        return _annotate_local_media_payload(localized, checked, cloud_step="transcribe_audio")

    def translate(
        self,
        input_path: Path,
        from_lang: str = "auto",
        to_lang: str = "zh",
        bilingual: bool = False,
        delivery: str = "subtitle",
        out: Path | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        checked = require_existing_file(input_path)
        payload = self._multipart_audio_or_file(
            "/v1/translate",
            checked,
            {
                "from_lang": from_lang,
                "to_lang": to_lang,
                "bilingual": "true" if bilingual else "false",
                "delivery": delivery,
                "output_dir": str(out) if out else None,
            },
            temp_prefix="cinlink-translate-audio-",
        )
        if isinstance(payload, dict) and "job_id" in payload and payload.get("status") not in {"done", "failed"}:
            payload = self.wait_for_job(payload["job_id"], timeout or self.settings.timeout_sec)
        result = self._localize_job_outputs(
            payload,
            out or checked.parent / f"{checked.stem}.cinlink",
            (
                "subtitle_path",
                "translated_subtitle_path",
                "output_subtitle_path",
                "source_subtitle_path",
                "source_reference_subtitle_path",
                "translated_text_path",
            ),
        )
        return _annotate_local_media_payload(result, checked, cloud_step="translate_subtitle")

    def dub(
        self,
        video_path: Path,
        subtitle_path: Path,
        reference_subtitle_path: Path | None = None,
        reference_audio_paths: dict[str, Path] | None = None,
        voice: str | None = None,
        language: str = "zh",
        out: Path | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        media = require_existing_file(video_path)
        media_is_video = _looks_like_video(media)
        subtitle = require_existing_file(subtitle_path)
        reference_subtitle = require_existing_file(reference_subtitle_path) if reference_subtitle_path else _discover_reference_subtitle(subtitle)
        reference_subtitle_auto_discovered = reference_subtitle is not None and reference_subtitle_path is None
        checked_reference_audio_paths = {
            str(speaker_id): require_existing_file(path)
            for speaker_id, path in (reference_audio_paths or {}).items()
        }
        data = {
            "language": language,
            "voice": voice,
            "output_dir": str(out) if out else None,
        }
        fields = {key: value for key, value in data.items() if value is not None}

        if media_is_video:
            with tempfile.TemporaryDirectory(prefix="cinlink-dub-audio-") as temp_dir:
                audio_path = Path(temp_dir) / "source.m4a"
                _extract_audio_for_upload(media, audio_path)
                payload = self._submit_dub_audio(
                    audio_path,
                    subtitle,
                    fields=fields,
                    reference_subtitle=reference_subtitle,
                    reference_audio_paths=checked_reference_audio_paths,
                )
        else:
            payload = self._submit_dub_audio(
                media,
                subtitle,
                fields=fields,
                reference_subtitle=reference_subtitle,
                reference_audio_paths=checked_reference_audio_paths,
            )
        if isinstance(payload, dict) and "job_id" in payload and payload.get("status") not in {"done", "failed"}:
            payload = self.wait_for_job(payload["job_id"], timeout or self.settings.timeout_sec)
        payload = _annotate_dub_payload(payload, media, media_is_video=media_is_video)
        if reference_subtitle is not None:
            payload.setdefault("source_reference_subtitle_path", str(reference_subtitle))
            payload.setdefault("reference_subtitle_auto_discovered", reference_subtitle_auto_discovered)
        return payload

    def _submit_dub_audio(
        self,
        audio_path: Path,
        subtitle_path: Path,
        *,
        fields: dict[str, Any],
        reference_subtitle: Path | None = None,
        reference_audio_paths: dict[str, Path] | None = None,
    ) -> dict[str, Any]:
        with ExitStack() as stack:
            audio_handle = stack.enter_context(audio_path.open("rb"))
            subtitle_handle = stack.enter_context(subtitle_path.open("rb"))
            files: dict[str, Any] = {
                "file": (audio_path.name, audio_handle),
                "subtitle": (subtitle_path.name, subtitle_handle),
            }
            if reference_subtitle:
                reference_handle = stack.enter_context(reference_subtitle.open("rb"))
                files["reference_subtitle"] = (reference_subtitle.name, reference_handle)
            for speaker_id, reference_audio_path in sorted((reference_audio_paths or {}).items()):
                reference_audio_handle = stack.enter_context(reference_audio_path.open("rb"))
                files[f"reference_audio__{speaker_id}"] = (reference_audio_path.name, reference_audio_handle)
            return self._request("POST", "/v1/dub", data=fields, files=files)

    def summarize(self, input_path: Path, out: Path | None = None, max_highlights: int = 3) -> dict[str, Any]:
        checked = require_existing_file(input_path)
        payload = self._multipart_audio_or_file(
            "/v1/summarize",
            checked,
            {"output_dir": str(out) if out else None, "max_highlights": str(max_highlights)},
            temp_prefix="cinlink-summary-audio-",
        )
        return _annotate_local_media_payload(payload, checked, cloud_step="summarize_video")

    def shorten(
        self,
        video_path: Path,
        out: Path | None = None,
        max_clips: int = 5,
        target_duration: int = 45,
        style_preset: str | None = None,
        music_mode: str = "none",
        music_prompt: str | None = None,
    ) -> dict[str, Any]:
        checked = require_existing_file(video_path)
        fields = {
            "output_dir": str(out) if out else None,
            "max_clips": str(max_clips),
            "target_duration_sec": str(target_duration),
            "style_preset": style_preset,
            "music_mode": music_mode,
            "music_prompt": music_prompt,
        }
        if _looks_like_video(checked):
            with tempfile.TemporaryDirectory(prefix="cinlink-shorten-audio-") as temp_dir:
                audio_path = Path(temp_dir) / "source.m4a"
                _extract_audio_for_upload(checked, audio_path)
                payload = self._submit_shorten_audio(audio_path, fields)
        else:
            payload = self._submit_shorten_audio(checked, fields)
        return _annotate_local_media_payload(payload, checked, cloud_step="shorten_video")

    def image(
        self,
        prompt: str,
        out: Path | None = None,
        aspect_ratio: str = "1:1",
        image_size: str = "1K",
        reference_image_urls: list[str] | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        if len(reference_image_urls or []) > 3:
            raise CliError(
                "invalid_input",
                "Image generation supports at most 3 reference images.",
            )
        uploaded_references = self._upload_reference_images_if_needed(
            reference_image_urls or []
        )
        payload = self._request(
            "POST",
            "/v1/image",
            json_body=_compact(
                {
                    "prompt": prompt,
                    "output_dir": str(out) if out else None,
                    "aspect_ratio": aspect_ratio,
                    "image_size": image_size,
                    "reference_image_urls": uploaded_references,
                    "model": model,
                }
            ),
        )
        if isinstance(payload, dict) and "job_id" in payload:
            result = self.wait_for_job(
                payload["job_id"], timeout or self.settings.timeout_sec
            )
        else:
            result = payload
        return self._localize_generated_file(
            result,
            out or Path.cwd() / "cinlink-generated-images",
            path_key="image_path",
            source_url_key="source_url",
        )

    def video(
        self,
        prompt: str,
        out: Path | None = None,
        aspect_ratio: str = "16:9",
        resolution: str = "720P",
        duration: int = 5,
        generate_audio: bool = True,
        watermark: bool = False,
        generation_mode: str | None = None,
        first_frame_image_url: str | None = None,
        reference_image_urls: list[str] | None = None,
        reference_video_urls: list[str] | None = None,
        reference_audio_urls: list[str] | None = None,
        model: str | None = None,
        model_name: str | None = None,
        model_version: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        if len(reference_image_urls or []) > 9:
            raise CliError(
                "invalid_input",
                "Video generation supports at most 9 reference images.",
            )
        uploaded_first_frame = self._upload_reference_images_if_needed(
            [first_frame_image_url] if first_frame_image_url else []
        )
        uploaded_reference_images = self._upload_reference_images_if_needed(reference_image_urls or [])
        effective_generation_mode = generation_mode or (
            "reference"
            if uploaded_reference_images or reference_video_urls or reference_audio_urls
            else "first_frame"
            if uploaded_first_frame
            else "text"
        )
        payload = self._request(
            "POST",
            "/v1/video",
            json_body=_compact(
                {
                    "prompt": prompt,
                    "output_dir": str(out) if out else None,
                    "aspect_ratio": aspect_ratio,
                    "resolution": resolution,
                    "duration_sec": duration,
                    "generate_audio": generate_audio,
                    "watermark": watermark,
                    "generation_mode": effective_generation_mode,
                    "first_frame_image_url": uploaded_first_frame[0] if uploaded_first_frame else None,
                    "reference_image_urls": uploaded_reference_images,
                    "reference_video_urls": reference_video_urls or [],
                    "reference_audio_urls": reference_audio_urls or [],
                    "model": model,
                    "model_name": model_name,
                    "model_version": model_version,
                }
            ),
        )
        if isinstance(payload, dict) and "job_id" in payload:
            result = self.wait_for_job(payload["job_id"], timeout or self.settings.timeout_sec)
        else:
            result = payload
        return self._localize_generated_file(result, out or Path.cwd() / "cinlink-generated-videos", path_key="video_path", source_url_key="source_url")

    def deconstruct_frames(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/v1/videos/deconstruct", json_body=payload)

    def nlu(
        self,
        prompt: str,
        has_video: bool = False,
        has_subtitle: bool = False,
        pending_target_language: str | None = None,
        context_files: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/nlu",
            json_body={
                "prompt": prompt,
                "has_selected_video": has_video,
                "has_subtitle": has_subtitle,
                "pending_translation_target_language": pending_target_language,
                "context_files": context_files or [],
            },
        )

    def create_agent_run(
        self,
        prompt: str,
        conversation_id: str | None = None,
        context_files: list[Path] | None = None,
        context_descriptors: list[dict[str, Any]] | None = None,
        mode: str = "execute",
        task_intent: str | None = None,
        task_parameters: dict[str, str] | None = None,
        conversation_state: dict[str, str] | None = None,
        client_request_id: str | None = None,
        app_language: str | None = None,
        hidden_context: str | None = None,
        client_capabilities: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        request_files = [
            _context_file_payload(path, current_submission=True)
            for path in (context_files or [])
        ]
        request_files.extend(
            _context_descriptor_payload(item, current_submission=False)
            for item in (context_descriptors or [])
        )
        request_files = _dedupe_context_files(request_files)
        request_files = _annotate_context_relationships(request_files)
        capabilities = dict(client_capabilities if client_capabilities is not None else default_client_capabilities())
        if task_intent and task_intent.strip():
            capabilities["trusted_fixed_workflow_routing"] = True
        return self._request(
            "POST",
            "/v1/agent/runs",
            json_body={
                "conversation_id": conversation_id or f"cli-{uuid4()}",
                "prompt": prompt,
                "client_request_id": client_request_id,
                "context_files": request_files,
                "task_intent": task_intent,
                "task_parameters": task_parameters or {},
                "conversation_state": conversation_state or {},
                "app_language": app_language,
                "hidden_context": hidden_context,
                "client_capabilities": capabilities,
                "mode": mode,
            },
        )

    def get_agent_run(self, run_id: str) -> dict[str, Any]:
        payload = self._request("GET", f"/v1/agent/runs/{run_id}")
        return _with_agent_privacy_receipt(_with_agent_delivery(payload))

    def continue_agent_clarification(
        self,
        run_id: str,
        *,
        clarification_id: str | None = None,
        value: str | None = None,
        answer: str | None = None,
        answers: dict[str, str] | None = None,
        client_request_id: str | None = None,
        wait: bool = False,
        include_events: bool = False,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        previous = self.get_agent_run(run_id)
        clarifications = _unique_agent_clarifications([
            item
            for item in previous.get("clarifications") or []
            if isinstance(item, dict)
        ])
        resolved = _resolve_agent_clarifications(
            clarifications,
            clarification_id=clarification_id,
            value=value,
            answer=answer,
            answers=answers,
        )

        previous_conversation_state = previous.get("conversation_state")
        previous_conversation_state = (
            previous_conversation_state
            if isinstance(previous_conversation_state, dict)
            else {}
        )
        conversation_state = {
            str(key): str(item)
            for key, item in previous_conversation_state.items()
            if item is not None
        }
        task_frame = previous.get("task_frame")
        if not isinstance(task_frame, dict) or not task_frame:
            raise CliError(
                "invalid_agent_clarification",
                "The previous CinLink Agent run does not include the task frame required to continue this clarification.",
                {"run_id": run_id},
            )
        conversation_state["agent_task_frame_json"] = json.dumps(
            task_frame,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        context_descriptors = _continuation_context_descriptors(
            previous.get("context_files")
        )
        resolved, file_selection_parameters = _resolve_agent_file_clarifications(
            resolved,
            context_descriptors,
        )
        task_parameters = {
            str(item["clarification"]["slot_key"]).strip(): item["value"]
            for item in resolved
        }
        task_parameters.update(file_selection_parameters)
        app_language = str(previous.get("app_language") or "").strip()
        if app_language:
            task_parameters["__clarification_reply_language"] = app_language
        prompt = "；".join(item["label"] for item in resolved)
        workflow_ids = [
            str(item["clarification"].get("workflow_id") or "").strip()
            for item in resolved
        ]
        task_intent = next((item for item in workflow_ids if item), None)
        created = self.create_agent_run(
            prompt,
            conversation_id=str(previous.get("conversation_id") or "") or None,
            context_descriptors=context_descriptors,
            mode=str(previous.get("mode") or "execute"),
            task_intent=task_intent,
            task_parameters=task_parameters,
            conversation_state=conversation_state,
            client_request_id=client_request_id,
            app_language=app_language or None,
        )
        if wait and created.get("run_id"):
            result = self.wait_for_agent_run(
                str(created["run_id"]),
                timeout=timeout,
                include_events=include_events,
            )
        else:
            result = created
        answered_clarifications = [
            {
                "id": item["clarification"].get("id"),
                "slot_key": item["clarification"].get("slot_key"),
                "value": item["value"],
                "label": item["label"],
            }
            for item in resolved
        ]
        return {
            **result,
            "continued_from_run_id": run_id,
            "answered_clarifications": answered_clarifications,
            "answered_clarification": answered_clarifications[0] if len(answered_clarifications) == 1 else None,
        }

    def upload_agent_artifact(
        self,
        input_path: Path,
        *,
        kind: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        checked = require_existing_file(input_path)
        resolved_kind = kind or infer_artifact_kind(checked)
        if resolved_kind == "video":
            raise CliError(
                "invalid_input",
                "CinLink keeps source videos local. Extract audio or report another explicitly requested non-video input instead of uploading a video.",
                {"path": str(checked)},
            )
        uploaded = self._upload_agent_file(checked, kind=resolved_kind)
        uploaded_artifact = uploaded.get("artifact")
        artifact = dict(uploaded_artifact) if isinstance(uploaded_artifact, dict) else {}
        artifact_metadata = artifact.get("metadata")
        artifact_metadata = dict(artifact_metadata) if isinstance(artifact_metadata, dict) else {}
        artifact_metadata.update(
            {
                str(key): str(item)
                for key, item in (metadata or {}).items()
                if item is not None
            }
        )
        artifact_metadata.update(
            {
                "local_path": str(checked),
                "cloud_accessible": "true",
                "agent_server_input": "true",
            }
        )
        cloud_file_id = _agent_upload_cloud_file_id(uploaded)
        if cloud_file_id:
            artifact_metadata["cloud_file_id"] = cloud_file_id
        artifact.update(
            {
                "name": str(uploaded.get("name") or artifact.get("name") or checked.name),
                "kind": resolved_kind,
                "path": str(checked),
                "url": uploaded.get("url") or artifact.get("url"),
                "cloud_file_id": cloud_file_id,
                "metadata": artifact_metadata,
            }
        )
        return artifact

    def stream_agent_events(
        self,
        run_id: str,
        *,
        last_event_id: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        try:
            import httpx
        except ImportError as exc:
            raise CliError(
                "dependency_missing",
                "The Python package `httpx` is required for CinLink Agent events.",
            ) from exc

        headers = dict(self.settings.auth_headers)
        if last_event_id:
            headers["Last-Event-ID"] = last_event_id
        stream_timeout = max(
            1.0,
            min(190.0, float(timeout or self.settings.timeout_sec)),
        )
        events: list[dict[str, Any]] = []
        cursor = last_event_id
        completed = False
        try:
            with httpx.Client(
                timeout=httpx.Timeout(stream_timeout, connect=30.0, write=60.0, pool=30.0)
            ) as client:
                with client.stream(
                    "GET",
                    f"{self.settings.runtime_base.rstrip('/')}/v1/agent/runs/{run_id}/events",
                    headers=headers,
                ) as response:
                    if response.status_code >= 400:
                        content = response.read()
                        try:
                            payload: Any = json.loads(content)
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            payload = {"raw": content.decode("utf-8", errors="replace")[:1000]}
                        raise normalize_remote_error(response.status_code, payload)
                    for event in _iter_sse_events(response.iter_lines()):
                        event_type = str(event.get("type") or "message")
                        if event.get("event_id"):
                            cursor = str(event["event_id"])
                        if event_type == "error":
                            error = event.get("data")
                            error = error if isinstance(error, dict) else {}
                            raise CliError(
                                str(error.get("code") or "remote_error"),
                                str(error.get("message") or "CinLink Agent event stream failed."),
                                {"run_id": run_id},
                            )
                        events.append(event)
                        if event_type == "done":
                            completed = True
                            break
        except httpx.HTTPError as exc:
            raise CliError(
                "network_error",
                f"Could not reach CinLink Agent event stream: {exc}",
                {"run_id": run_id, "last_event_id": cursor},
            ) from exc
        return {
            "run_id": run_id,
            "events": events,
            "last_event_id": cursor,
            "stream_completed": completed,
        }

    def wait_for_agent_run(
        self,
        run_id: str,
        timeout: float | None = None,
        *,
        include_events: bool = False,
    ) -> dict[str, Any]:
        deadline = time.time() + (timeout or self.settings.timeout_sec)
        planning_events: list[dict[str, Any]] = []
        event_stream_error: dict[str, Any] | None = None
        try:
            streamed = self.stream_agent_events(
                run_id,
                timeout=max(1.0, deadline - time.time()),
            )
            planning_events = list(streamed.get("events") or [])
        except CliError as exc:
            event_stream_error = exc.to_payload()["error"]
        while True:
            payload = self.get_agent_run(run_id)
            if payload.get("status") in {"done", "failed", "requires_user_input", "waiting_for_local"}:
                if include_events:
                    payload["agent_events"] = planning_events
                    if event_stream_error:
                        payload["agent_event_stream_error"] = event_stream_error
                return payload
            if time.time() > deadline:
                raise CliError("timeout", f"Agent run did not finish within {timeout or self.settings.timeout_sec} seconds.", {"run_id": run_id})
            time.sleep(self.settings.poll_interval_sec)

    def list_local_tool_calls(self, run_id: str, device_id: str | None = None) -> dict[str, Any]:
        suffix = f"?device_id={device_id}" if device_id else ""
        return self._request("GET", f"/v1/agent/runs/{run_id}/local-tool-calls{suffix}")

    def report_local_tool_result(self, run_id: str, result: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/v1/agent/runs/{run_id}/local-tool-results", json_body=result)

    def wait_for_job(self, job_id: str, timeout: float) -> dict[str, Any]:
        deadline = time.time() + timeout
        while True:
            payload = self._request("GET", f"/v1/jobs/{job_id}")
            if payload.get("status") in {"done", "failed"}:
                if payload.get("status") == "failed":
                    error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
                    details = {"job_id": job_id}
                    details.update(
                        {
                            key: error[key]
                            for key in _SAFE_JOB_ERROR_DETAIL_KEYS
                            if error.get(key) is not None
                        }
                    )
                    raise CliError(
                        str(error.get("code") or "processing_failed"),
                        str(error.get("message") or "Remote job failed."),
                        details,
                    )
                return payload
            if time.time() > deadline:
                raise CliError("timeout", f"Job did not finish within {timeout} seconds.", {"job_id": job_id})
            time.sleep(self.settings.poll_interval_sec)

    def _localize_job_outputs(self, payload: dict[str, Any], out: Path, keys: tuple[str, ...]) -> dict[str, Any]:
        outputs = payload.get("outputs")
        output_dir = out.expanduser().resolve()
        result = dict(payload)
        localized_outputs = dict(outputs) if isinstance(outputs, dict) else None
        for key in keys:
            remote_value = outputs.get(key) if isinstance(outputs, dict) else payload.get(key)
            if not remote_value:
                continue
            remote_path = Path(str(remote_value)).expanduser()
            if remote_path.exists():
                localized_path = str(remote_path.resolve())
            else:
                localized_path = str(self._download_hosted_file(str(remote_value), output_dir, fallback_filename=remote_path.name or f"{key}.txt"))
            if localized_outputs is not None:
                localized_outputs[key] = localized_path
            result[key] = localized_path
        if localized_outputs is not None:
            result["outputs"] = localized_outputs
            for key, value in localized_outputs.items():
                result.setdefault(key, value)
        return result

    def _localize_generated_file(self, payload: dict[str, Any], out: Path, *, path_key: str, source_url_key: str | None = None) -> dict[str, Any]:
        outputs = payload.get("outputs")
        output_values = outputs if isinstance(outputs, dict) else payload
        remote_value = output_values.get(path_key) if isinstance(output_values, dict) else None
        if not remote_value:
            return payload
        remote_path = Path(str(remote_value)).expanduser()
        if remote_path.exists():
            local_path = str(remote_path.resolve())
        else:
            source_url = output_values.get(source_url_key) if source_url_key and isinstance(output_values, dict) else None
            local_path = str(self._download_hosted_file(str(remote_value), out.expanduser().resolve(), fallback_filename=remote_path.name or f"{path_key}.bin", source_url=str(source_url) if source_url else None))
        if isinstance(outputs, dict):
            localized_outputs = dict(outputs)
            localized_outputs[path_key] = local_path
            result = {**payload, "outputs": localized_outputs}
        else:
            result = dict(payload)
        result[path_key] = local_path
        return result

    def _download_hosted_file(self, remote_path: str, output_dir: Path, fallback_filename: str, source_url: str | None = None) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        destination = _unique_destination(output_dir, fallback_filename)
        try:
            import httpx
        except ImportError as exc:
            raise CliError("dependency_missing", "The Python package `httpx` is required to download CinLink hosted artifacts.") from exc
        timeout = httpx.Timeout(
            max(60.0, float(self.settings.timeout_sec)),
            connect=30.0,
            write=60.0,
            pool=30.0,
        )
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.get(f"{self.settings.runtime_base.rstrip('/')}/v1/files", headers=self.settings.auth_headers, params={"path": remote_path})
        except httpx.HTTPError as exc:
            raise CliError("network_error", f"Could not download hosted artifact: {exc}", {"remote_path": remote_path}) from exc
        if response.status_code >= 400:
            if source_url:
                return self._download_external_file(source_url, destination)
            try:
                payload: Any = response.json()
            except json.JSONDecodeError:
                payload = {"raw": response.text[:1000]}
            error = normalize_remote_error(response.status_code, payload)
            raise CliError(error.code, f"Could not download hosted artifact: {error.message}", {"remote_path": remote_path, **error.details})
        destination.write_bytes(response.content)
        return destination

    def _download_external_file(self, source_url: str, destination: Path) -> Path:
        try:
            import httpx
        except ImportError as exc:
            raise CliError("dependency_missing", "The Python package `httpx` is required to download generated media.") from exc
        timeout = httpx.Timeout(
            max(60.0, float(self.settings.timeout_sec)),
            connect=30.0,
            write=60.0,
            pool=30.0,
        )
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                response = client.get(source_url)
        except httpx.HTTPError as exc:
            raise CliError("network_error", f"Could not download generated media: {exc}") from exc
        if response.status_code >= 400:
            raise CliError("remote_error", f"Generated media download failed with HTTP {response.status_code}.")
        destination.write_bytes(response.content)
        return destination

    def _multipart(self, path: str, input_path: Path, fields: dict[str, Any]) -> dict[str, Any]:
        checked = require_existing_file(input_path)
        data = {key: value for key, value in fields.items() if value is not None}
        with checked.open("rb") as file_handle:
            return self._request("POST", path, data=data, files={"file": (checked.name, file_handle)})

    def _upload_reference_images_if_needed(self, values: list[str]) -> list[str]:
        uploaded: list[str] = []
        for raw in values:
            value = str(raw or "").strip()
            if not value:
                continue
            if value.lower().startswith(("http://", "https://")):
                uploaded.append(value)
                continue
            if value.lower().startswith("file://"):
                from urllib.parse import unquote, urlparse

                image_path = Path(unquote(urlparse(value).path))
            else:
                image_path = Path(value)
            checked = require_existing_file(image_path)
            with checked.open("rb") as handle:
                payload = self._request(
                    "POST",
                    "/v1/reference-images",
                    files={"file": (checked.name, handle)},
                )
            reference_url = str(payload.get("reference_image_url") or "").strip()
            if not reference_url:
                raise CliError(
                    "invalid_response",
                    "CinLink reference image upload did not return reference_image_url.",
                    {"path": str(checked)},
                )
            uploaded.append(reference_url)
        return uploaded

    def _submit_shorten_audio(
        self,
        audio_path: Path,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        checked = require_existing_file(audio_path)
        try:
            uploaded = self._upload_agent_file(checked, kind="audio")
        except CliError as exc:
            if not _is_cloud_file_shorten_compatibility_error(exc):
                raise
            return self._multipart("/v1/shorten", checked, fields)

        cloud_file_id = _agent_upload_cloud_file_id(uploaded)
        if not cloud_file_id:
            return self._multipart("/v1/shorten", checked, fields)

        data = {key: value for key, value in fields.items() if value is not None}
        try:
            return self._request(
                "POST",
                "/v1/shorten",
                data=data,
                files={"cloud_file_id": (None, cloud_file_id)},
            )
        except CliError as exc:
            if not _is_cloud_file_shorten_compatibility_error(exc):
                raise
            return self._multipart("/v1/shorten", checked, fields)

    def _upload_agent_file(self, input_path: Path, *, kind: str) -> dict[str, Any]:
        checked = require_existing_file(input_path)
        with checked.open("rb") as handle:
            return self._request(
                "POST",
                "/v1/agent/files",
                data={"kind": kind},
                files={"file": (checked.name, handle)},
            )

    def _multipart_audio_or_file(
        self,
        path: str,
        input_path: Path,
        fields: dict[str, Any],
        *,
        temp_prefix: str,
    ) -> dict[str, Any]:
        checked = require_existing_file(input_path)
        if not _looks_like_video(checked):
            return self._multipart(path, checked, fields)
        with tempfile.TemporaryDirectory(prefix=temp_prefix) as temp_dir:
            audio_path = Path(temp_dir) / "source.m4a"
            _extract_audio_for_upload(checked, audio_path)
            return self._multipart(path, audio_path, fields)

    def _request(
        self,
        method: str,
        path: str,
        *,
        auth: bool = True,
        json_body: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        base = self.settings.runtime_base.rstrip("/")
        headers = self.settings.auth_headers if auth else {}
        try:
            import httpx
        except ImportError as exc:
            raise CliError("dependency_missing", "The Python package `httpx` is required for CinLink hosted requests. Install the CLI with `pip install git+https://github.com/SvenShii/Cinlink.git`.") from exc
        try:
            timeout = httpx.Timeout(
                max(60.0, float(self.settings.timeout_sec)),
                connect=30.0,
                write=max(300.0, min(float(self.settings.timeout_sec), 900.0)),
                pool=30.0,
            )
            with httpx.Client(timeout=timeout) as client:
                response = client.request(method, f"{base}{path}", headers=headers, json=json_body, data=data, files=files)
        except httpx.HTTPError as exc:
            raise CliError("network_error", f"Could not reach runtime service: {exc}") from exc
        try:
            payload: Any = response.json()
        except json.JSONDecodeError:
            payload = {"raw": response.text[:1000]}
        if response.status_code >= 400:
            raise normalize_remote_error(response.status_code, payload)
        if not isinstance(payload, dict):
            raise CliError("invalid_response", "Runtime returned a non-object JSON response.", {"type": type(payload).__name__})
        return payload


def require_existing_file(path: Path) -> Path:
    expanded = path.expanduser().resolve()
    if not expanded.exists():
        raise CliError("invalid_input", f"File does not exist: {expanded}")
    if not expanded.is_file():
        raise CliError("invalid_input", f"Path is not a file: {expanded}")
    return expanded


def _looks_like_video(path: Path) -> bool:
    return path.suffix.lower() in {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm", ".mpg", ".mpeg", ".flv"}


def _annotate_local_media_payload(
    payload: dict[str, Any],
    media_path: Path,
    *,
    cloud_step: str | None = None,
) -> dict[str, Any]:
    result = dict(payload)
    resolved = str(media_path.expanduser().resolve())
    result.setdefault("source_media_path", resolved)
    hosted_inputs: list[str] = []
    local_steps: list[str] = []
    if _looks_like_video(media_path):
        result.setdefault("source_video_path", resolved)
        result.setdefault("hosted_input_kind", "audio")
        hosted_inputs.append("audio")
        local_steps.append("extract_audio")
        source_video = "stayed_local"
    else:
        source_video = "not_included"
        hosted_inputs.append(_privacy_input_kind(media_path))
    result["privacy_receipt"] = {
        "source_video": source_video,
        "hosted_inputs": hosted_inputs,
        "local_steps": local_steps,
        "cloud_steps": [cloud_step] if cloud_step else [],
        "local_final_video_processing": False,
    }
    return result


def _annotate_dub_payload(payload: dict[str, Any], media_path: Path, *, media_is_video: bool) -> dict[str, Any]:
    result = _annotate_local_media_payload(payload, media_path, cloud_step="synthesize_dub_audio")
    result.setdefault("hosted_input_kind", "audio")
    if media_is_video:
        result.setdefault("requires_local_video_composition", True)
    return result


def _extract_audio_for_upload(video_path: Path, audio_path: Path) -> None:
    ffmpeg = resolve_ffmpeg(require_subtitles=False)
    if not ffmpeg:
        raise CliError("dependency_missing", "ffmpeg was not found. CinLink needs local ffmpeg to extract audio before hosted transcription.")
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(ffmpeg),
        "-nostdin",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "aac",
        "-b:a",
        "96k",
        str(audio_path),
    ]
    completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    if completed.returncode != 0 or not audio_path.exists():
        raise CliError("processing_failed", "ffmpeg failed to extract audio before hosted upload.", {"stderr": completed.stderr[-2000:]})


def _unique_destination(output_dir: Path, filename: str) -> Path:
    safe_name = filename.strip() or "artifact"
    candidate = output_dir / safe_name
    if not candidate.exists():
        return candidate
    stem = candidate.stem or "artifact"
    suffix = candidate.suffix
    for index in range(2, 1000):
        next_candidate = output_dir / f"{stem}-{index}{suffix}"
        if not next_candidate.exists():
            return next_candidate
    return output_dir / f"{stem}-{uuid4().hex}{suffix}"


def default_client_capabilities() -> dict[str, bool]:
    return default_client_capabilities_from_dependencies()


def _compact(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _agent_upload_cloud_file_id(payload: dict[str, Any]) -> str | None:
    artifact = payload.get("artifact")
    artifact = artifact if isinstance(artifact, dict) else {}
    metadata = artifact.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    value = (
        payload.get("cloud_file_id")
        or artifact.get("cloud_file_id")
        or metadata.get("cloud_file_id")
    )
    normalized = str(value or "").strip()
    return normalized or None


def _is_cloud_file_shorten_compatibility_error(error: CliError) -> bool:
    normalized_code = error.code.strip().lower().replace("-", "_")
    if normalized_code not in {
        "invalid_input",
        "invalid_response",
        "job_not_found",
        "not_found",
        "processing_failed",
        "remote_error",
        "unsupported",
    }:
        return False
    status_code = (error.details or {}).get("status_code")
    normalized = f"{normalized_code} {error.message}".lower().replace("-", "_")
    return status_code == 404 or any(
        marker in normalized
        for marker in (
            "agent file",
            "agent_file",
            "cloud file",
            "cloud_file",
            "missing upload",
            "not found",
            "not_found",
            "unsupported",
        )
    )


def _discover_reference_subtitle(translated_subtitle: Path) -> Path | None:
    translated = translated_subtitle.expanduser().resolve()
    for filename in ("source.reference.srt", "subtitle.reference.srt", "source.srt"):
        candidate = translated.parent / filename
        if candidate == translated or not candidate.is_file():
            continue
        if _subtitle_file_has_usable_cues(candidate):
            return candidate.resolve()
    return None


def _select_agent_clarification(
    clarifications: list[dict[str, Any]],
    *,
    clarification_id: str | None,
) -> dict[str, Any]:
    if clarification_id:
        for item in clarifications:
            if str(item.get("id") or "") == clarification_id:
                return item
        raise CliError(
            "clarification_not_found",
            "The requested CinLink Agent clarification was not found on this run.",
            {
                "clarification_id": clarification_id,
                "available_clarification_ids": [
                    str(item.get("id")) for item in clarifications if item.get("id")
                ],
            },
        )
    if len(clarifications) == 1:
        return clarifications[0]
    if not clarifications:
        raise CliError(
            "clarification_not_found",
            "This CinLink Agent run does not expose a structured clarification. Poll the run and handle its requires_user_input message directly.",
        )
    raise CliError(
        "clarification_id_required",
        "This CinLink Agent run has multiple clarifications. Pass clarification_id for the one being answered.",
        {
            "available_clarifications": [
                {
                    "id": item.get("id"),
                    "slot_key": item.get("slot_key"),
                    "question": item.get("question"),
                }
                for item in clarifications
            ]
        },
    )


def _unique_agent_clarifications(
    clarifications: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in clarifications:
        slot_key = _normalized_clarification_key(item.get("slot_key"))
        identity = f"slot:{slot_key}" if slot_key else f"id:{str(item.get('id') or '').strip()}"
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(item)
    return unique


def _resolve_agent_clarifications(
    clarifications: list[dict[str, Any]],
    *,
    clarification_id: str | None,
    value: str | None,
    answer: str | None,
    answers: dict[str, str] | None,
) -> list[dict[str, Any]]:
    if not clarifications:
        _select_agent_clarification([], clarification_id=clarification_id)
    submitted = {
        str(key).strip(): str(item)
        for key, item in (answers or {}).items()
        if str(key).strip() and item is not None
    }
    if clarification_id or value is not None or answer is not None:
        selected = _select_agent_clarification(
            clarifications,
            clarification_id=clarification_id,
        )
        selected_key = str(selected.get("id") or selected.get("slot_key") or "").strip()
        submitted[selected_key] = str(answer if answer is not None else value or "")

    resolved: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for clarification in clarifications:
        slot_key = str(clarification.get("slot_key") or "").strip()
        if not slot_key:
            raise CliError(
                "invalid_agent_clarification",
                "A CinLink clarification does not include a slot_key.",
                {"clarification_id": clarification.get("id")},
            )
        clarification_id_value = str(clarification.get("id") or "").strip()
        raw_answer = submitted.get(clarification_id_value)
        if raw_answer is None:
            raw_answer = submitted.get(slot_key)
        if raw_answer is None:
            raw_answer = submitted.get(_normalized_clarification_key(slot_key))
        if raw_answer is None:
            selected_value = str(clarification.get("selected_value") or "").strip()
            if selected_value:
                raw_answer = selected_value
        if raw_answer is None:
            missing.append(
                {
                    "id": clarification.get("id"),
                    "slot_key": slot_key,
                    "question": clarification.get("question"),
                }
            )
            continue
        selected_value, label = _resolve_agent_clarification_answer(
            clarification,
            value=None,
            answer=raw_answer,
        )
        resolved.append(
            {"clarification": clarification, "value": selected_value, "label": label}
        )
    if missing:
        raise CliError(
            "clarification_answers_required",
            "Answer every unresolved clarification before continuing the CinLink Agent run.",
            {
                "missing_clarifications": missing,
                "hint": "Pass repeated --response ID_OR_SLOT=VALUE or --answers-json with all answers.",
            },
        )
    return resolved


def _resolve_agent_file_clarifications(
    resolved: list[dict[str, Any]],
    context_descriptors: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    required_kinds_by_slot = {
        "media_id": {"video"},
        "video_id": {"video"},
        "video_file_id": {"video"},
        "video_entity_id": {"video"},
        "source_video": {"video"},
        "source_video_id": {"video"},
        "source_video_entity_id": {"video"},
        "subtitle_id": {"subtitle"},
        "subtitle_file_id": {"subtitle"},
        "subtitle_entity_id": {"subtitle"},
    }
    extra_parameters: dict[str, str] = {}
    for item in resolved:
        clarification = item["clarification"]
        slot_key = _normalized_clarification_key(clarification.get("slot_key"))
        required_kinds = required_kinds_by_slot.get(slot_key)
        if not required_kinds:
            continue
        response = str(item["value"]).strip()
        normalized_response = response.strip("@\"'“”‘’ ").casefold()
        candidates = [
            descriptor
            for descriptor in context_descriptors
            if str(descriptor.get("kind") or "other") in required_kinds
        ]
        matches = [
            descriptor
            for descriptor in candidates
            if normalized_response in _agent_context_descriptor_match_values(descriptor)
        ]
        if len(matches) != 1:
            raise CliError(
                "invalid_clarification_answer",
                "The file clarification answer must identify exactly one matching context file.",
                {
                    "clarification_id": clarification.get("id"),
                    "slot_key": clarification.get("slot_key"),
                    "answer": response,
                    "expected_kinds": sorted(required_kinds),
                    "available_files": [
                        {"id": descriptor.get("id"), "name": descriptor.get("name")}
                        for descriptor in candidates
                    ],
                },
            )
        selected = matches[0]
        entity_id = next(
            (
                str(selected.get(key)).strip()
                for key in ("entity_id", "id", "local_asset_id", "cloud_file_id")
                if selected.get(key) and str(selected.get(key)).strip()
            ),
            "",
        )
        if not entity_id:
            raise CliError(
                "invalid_agent_clarification",
                "The selected context file has no stable identity for Agent continuation.",
                {"name": selected.get("name"), "slot_key": clarification.get("slot_key")},
            )
        item["value"] = entity_id
        metadata = selected.get("metadata")
        metadata = dict(metadata) if isinstance(metadata, dict) else {}
        metadata.update(
            {"selection_scope": "current_submission", "input_priority": "highest"}
        )
        selected["metadata"] = metadata
        extra_parameters["selected_entity_id"] = entity_id
        if "video" in required_kinds:
            extra_parameters.update(
                {
                    "media_id": entity_id,
                    "source_entity_id": entity_id,
                    "video_entity_id": entity_id,
                }
            )
    return resolved, extra_parameters


def _agent_context_descriptor_match_values(descriptor: dict[str, Any]) -> set[str]:
    values = {
        str(descriptor.get(key) or "").strip().casefold()
        for key in ("entity_id", "id", "local_asset_id", "cloud_file_id", "name")
        if descriptor.get(key)
    }
    name = str(descriptor.get("name") or "").strip()
    if name:
        values.add(Path(name).stem.casefold())
    return {value for value in values if value}


def _resolve_agent_clarification_answer(
    clarification: dict[str, Any],
    *,
    value: str | None,
    answer: str | None,
) -> tuple[str, str]:
    options = [
        item for item in clarification.get("options") or [] if isinstance(item, dict)
    ]
    raw_answer = str(answer if answer is not None else value or "").strip()
    input_kind = str(clarification.get("input_kind") or "text")
    if input_kind == "single_select" or options:
        if not raw_answer:
            raise CliError(
                "clarification_answer_required",
                "Pass value with one of the clarification option values or labels.",
                {"clarification_id": clarification.get("id")},
            )
        normalized = raw_answer.casefold()
        for option in options:
            option_value = str(option.get("value") or "").strip()
            option_label = str(option.get("label") or option_value).strip()
            if normalized in {option_value.casefold(), option_label.casefold()}:
                return option_value, option_label
        if _normalized_clarification_key(clarification.get("slot_key")) == "target_duration_sec":
            normalized_duration = _normalize_custom_duration_seconds(raw_answer)
            if normalized_duration is not None:
                return normalized_duration, normalized_duration
        raise CliError(
            "invalid_clarification_answer",
            "The answer does not match a CinLink clarification option.",
            {
                "clarification_id": clarification.get("id"),
                "options": [
                    {
                        "value": item.get("value"),
                        "label": item.get("label"),
                    }
                    for item in options
                ],
            },
        )
    if not raw_answer:
        raise CliError(
            "clarification_answer_required",
            "Pass answer for this text clarification.",
            {"clarification_id": clarification.get("id")},
        )
    return raw_answer, raw_answer


def _normalized_clarification_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _normalize_custom_duration_seconds(value: str) -> str | None:
    normalized = value.strip().lower().replace("：", ":")
    seconds: float | None = None
    if ":" in normalized:
        parts = normalized.split(":")
        if len(parts) in {2, 3}:
            try:
                numbers = [float(item.strip()) for item in parts]
                seconds = (
                    numbers[0] * 60 + numbers[1]
                    if len(numbers) == 2
                    else numbers[0] * 3600 + numbers[1] * 60 + numbers[2]
                )
            except ValueError:
                seconds = None
    else:
        try:
            seconds = float(normalized)
        except ValueError:
            units = {
                "hours": r"([0-9]+(?:\.[0-9]+)?)\s*(?:hours?|hrs?|hr|h|小时|小時|時間)",
                "minutes": r"([0-9]+(?:\.[0-9]+)?)\s*(?:minutes?|mins?|min|m|分钟|分鐘|分)",
                "seconds": r"([0-9]+(?:\.[0-9]+)?)\s*(?:seconds?|secs?|sec|s|秒)",
            }
            matches = {
                key: re.search(pattern, normalized)
                for key, pattern in units.items()
            }
            if any(matches.values()):
                seconds = sum(
                    (float(match.group(1)) if match else 0.0) * multiplier
                    for match, multiplier in (
                        (matches["hours"], 3600),
                        (matches["minutes"], 60),
                        (matches["seconds"], 1),
                    )
                )
    rounded = math.floor(seconds + 0.5) if seconds is not None else None
    if rounded is None or not 10 <= rounded <= 600:
        return None
    return str(rounded)


def _continuation_context_descriptors(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    descriptors: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        descriptor = dict(item)
        for key in ("path", "local_path", "local_hint"):
            local_value = descriptor.get(key)
            if local_value and not Path(str(local_value)).expanduser().is_file():
                descriptor.pop(key, None)
        descriptors.append(descriptor)
    return descriptors


def _context_file_payload(
    path: Path,
    *,
    current_submission: bool,
) -> dict[str, Any]:
    checked = require_existing_file(path)
    kind = "subtitle" if checked.suffix.lower() == ".txt" else infer_artifact_kind(checked)
    metadata = {
        "file_size_bytes": str(checked.stat().st_size),
        "artifact_original_name": checked.name,
    }
    if current_submission:
        metadata.update(
            {
                "selection_scope": "current_submission",
                "input_priority": "highest",
            }
        )
    if kind == "subtitle" and _subtitle_file_has_usable_cues(checked):
        metadata.update(
            {
                "subtitle_has_usable_cues": "true",
                "subtitle_reuse_eligible": "true",
            }
        )
    return {
        "id": None,
        "name": checked.name,
        "kind": kind,
        "local_path": str(checked),
        "local_hint": str(checked),
        "metadata": metadata,
    }


def _subtitle_file_has_usable_cues(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix not in {".srt", ".vtt", ".ass", ".ssa"}:
        return False
    try:
        content = path.read_text(encoding="utf-8", errors="replace")[:200_000]
    except OSError:
        return False
    if suffix in {".ass", ".ssa"}:
        for line in content.splitlines():
            if not line.lstrip().startswith("Dialogue:"):
                continue
            fields = line.split(",", 9)
            if len(fields) == 10 and fields[-1].replace(r"\N", " ").strip():
                return True
        return False
    lines = content.splitlines()
    for index, line in enumerate(lines):
        if "-->" not in line:
            continue
        for cue_line in lines[index + 1 :]:
            stripped = cue_line.strip()
            if "-->" in cue_line or not stripped:
                break
            if stripped and not stripped.isdigit():
                return True
    return False


def _annotate_context_relationships(
    context_files: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    videos = [item for item in context_files if item.get("kind") == "video"]
    duration_cache: dict[str, float | None] = {}
    annotated: list[dict[str, Any]] = []
    for item in context_files:
        if item.get("kind") != "subtitle":
            annotated.append(item)
            continue
        metadata = dict(item.get("metadata") or {})
        has_source = any(
            str(metadata.get(key) or "").strip()
            for key in (
                "subtitle_source_video_id",
                "subtitle_source_video_entity_id",
                "subtitle_source_video_name",
            )
        )
        if not has_source:
            source = _unique_context_video_for_subtitle(item, videos)
            if source is not None:
                if source.get("id"):
                    metadata["subtitle_source_video_id"] = str(source["id"])
                elif source.get("entity_id"):
                    metadata["subtitle_source_video_entity_id"] = str(
                        source["entity_id"]
                    )
                else:
                    metadata["subtitle_source_video_name"] = str(source.get("name") or "")
        else:
            source = _linked_context_video_for_subtitle(metadata, videos)
        if source is not None:
            _annotate_subtitle_timeline_fit(
                item,
                source,
                metadata,
                duration_cache=duration_cache,
            )
        annotated.append({**item, "metadata": metadata})
    return annotated


def _linked_context_video_for_subtitle(
    metadata: dict[str, Any],
    videos: list[dict[str, Any]],
) -> dict[str, Any] | None:
    references = (
        ("subtitle_source_video_id", "id"),
        ("subtitle_source_video_entity_id", "entity_id"),
        ("subtitle_source_video_name", "name"),
    )
    for metadata_key, video_key in references:
        expected = str(metadata.get(metadata_key) or "").strip()
        if not expected:
            continue
        matches = [
            video
            for video in videos
            if str(video.get(video_key) or "").strip() == expected
        ]
        if len(matches) == 1:
            return matches[0]
    return None


def _annotate_subtitle_timeline_fit(
    subtitle: dict[str, Any],
    video: dict[str, Any],
    metadata: dict[str, Any],
    *,
    duration_cache: dict[str, float | None],
) -> None:
    subtitle_path = _existing_context_local_path(subtitle)
    video_path = _existing_context_local_path(video)
    if subtitle_path is None or video_path is None:
        return
    bounds = _subtitle_timeline_bounds(subtitle_path)
    if bounds is None:
        return
    cache_key = str(video_path)
    if cache_key not in duration_cache:
        duration_cache[cache_key] = _probe_media_duration(video_path)
    duration = duration_cache[cache_key]
    if duration is None:
        return
    max_start, max_end = bounds
    start_grace = 1.5
    end_grace = max(3.0, min(10.0, duration * 0.05))
    if max_start <= duration + start_grace and max_end <= duration + end_grace:
        return
    metadata.update(
        {
            "subtitle_reuse_eligible": "false",
            "subtitle_timeline_mismatch": "true",
            "subtitle_max_start_sec": f"{max_start:.3f}",
            "subtitle_end_sec": f"{max_end:.3f}",
            "source_video_duration_sec": f"{duration:.3f}",
        }
    )


def _existing_context_local_path(item: dict[str, Any]) -> Path | None:
    for key in ("local_path", "local_hint", "path"):
        raw = item.get(key)
        if not raw:
            continue
        candidate = Path(str(raw)).expanduser()
        if candidate.is_file():
            return candidate.resolve()
    return None


def _subtitle_timeline_bounds(path: Path) -> tuple[float, float] | None:
    try:
        content = path.read_text(encoding="utf-8", errors="replace")[:1_000_000]
    except OSError:
        return None
    timestamps: list[float] = []
    for match in _SUBTITLE_TIMESTAMP_PATTERN.finditer(content):
        fraction = match.group(4)
        timestamps.append(
            int(match.group(1)) * 3600
            + int(match.group(2)) * 60
            + int(match.group(3))
            + int(fraction) / (10 ** len(fraction))
        )
    if not timestamps:
        return None
    max_start = 0.0
    max_end = 0.0
    for index in range(0, len(timestamps), 2):
        start = timestamps[index]
        end = timestamps[index + 1] if index + 1 < len(timestamps) else start
        max_start = max(max_start, start)
        max_end = max(max_end, end)
    return max_start, max_end


def _probe_media_duration(path: Path) -> float | None:
    ffmpeg = resolve_ffmpeg(require_subtitles=False)
    ffprobe = resolve_ffprobe(ffmpeg)
    if not ffprobe:
        return None
    try:
        completed = subprocess.run(
            [
                str(ffprobe),
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        duration = float(completed.stdout.strip()) if completed.returncode == 0 else 0.0
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    return duration if duration > 0 else None


def _unique_context_video_for_subtitle(
    subtitle: dict[str, Any],
    videos: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if len(videos) == 1:
        return videos[0]
    subtitle_stem = Path(str(subtitle.get("name") or "")).stem.lower()
    stem_matches = [
        video
        for video in videos
        if Path(str(video.get("name") or "")).stem.lower() == subtitle_stem
    ]
    return stem_matches[0] if len(stem_matches) == 1 else None


def _context_descriptor_payload(
    value: dict[str, Any],
    *,
    current_submission: bool,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CliError("invalid_input", "Each context descriptor must be a JSON object.")
    raw_path = value.get("path") or value.get("local_path") or value.get("local_hint")
    payload = (
        _context_file_payload(
            Path(str(raw_path)),
            current_submission=current_submission,
        )
        if raw_path
        else {}
    )
    metadata = dict(payload.get("metadata") or {})
    supplied_metadata = value.get("metadata")
    if supplied_metadata is not None and not isinstance(supplied_metadata, dict):
        raise CliError("invalid_input", "Context descriptor metadata must be a JSON object.")
    metadata.update(
        {
            str(key): str(item)
            for key, item in (supplied_metadata or {}).items()
            if item is not None
        }
    )
    for key in (
        "id",
        "entity_id",
        "local_asset_id",
        "device_id",
        "public_url",
        "cloud_file_id",
        "name",
        "kind",
    ):
        if value.get(key) is not None:
            payload[key] = str(value[key])
    if not payload.get("name"):
        reference = payload.get("cloud_file_id") or payload.get("public_url") or payload.get("id")
        if not reference:
            raise CliError(
                "invalid_input",
                "A context descriptor requires a local path, name, public_url, cloud_file_id, or id.",
            )
        payload["name"] = Path(str(reference).split("?", 1)[0]).name or "context-artifact"
    if not payload.get("kind"):
        name_path = Path(str(payload["name"]))
        payload["kind"] = "subtitle" if name_path.suffix.lower() == ".txt" else infer_artifact_kind(name_path)
    payload["metadata"] = metadata
    return payload


def _dedupe_context_files(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for item in items:
        key = tuple(
            str(item.get(name) or "")
            for name in ("id", "entity_id", "local_asset_id", "cloud_file_id", "public_url", "local_path", "name")
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def infer_artifact_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm", ".mpg", ".mpeg", ".flv"}:
        return "video"
    if suffix in {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus"}:
        return "audio"
    if suffix in {".srt", ".vtt", ".ass", ".ssa"}:
        return "subtitle"
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif"}:
        return "image"
    if suffix in {".txt", ".md", ".pdf", ".doc", ".docx", ".json"}:
        return "document"
    return "other"


def artifact_ref_from_path(
    path: Path,
    *,
    kind: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    checked = require_existing_file(path)
    normalized_metadata = {
        str(key): str(value)
        for key, value in (metadata or {}).items()
        if value is not None
    }
    normalized_metadata.setdefault("artifact_original_name", checked.name)
    return {
        "id": None,
        "name": checked.name,
        "kind": kind or infer_artifact_kind(checked),
        "path": str(checked),
        "metadata": normalized_metadata,
    }


def _privacy_input_kind(path: Path) -> str:
    kind = infer_artifact_kind(path)
    if kind in {"subtitle", "document"}:
        return "subtitles_or_text"
    return kind


_FINAL_ARTIFACT_ROLES = {
    "burned_video",
    "dubbed_video",
    "edited_video",
    "enhanced_video",
    "final",
    "final_image",
    "final_output",
    "final_video",
    "generated_image",
    "generated_video",
    "highlight_video",
    "primary",
    "shortened_video",
    "subtitled_video",
}
_SUPPORTING_ARTIFACT_ROLES = {"captions", "supporting", "translated_subtitle"}
_INTERNAL_ARTIFACT_ROLES = {
    "dubbed_audio",
    "intermediate",
    "reference_subtitle",
    "source_audio",
    "source_subtitle",
    "transcript",
}


def _iter_sse_events(lines: Any):
    event_type = "message"
    event_id: str | None = None
    data_lines: list[str] = []

    def consume() -> dict[str, Any] | None:
        nonlocal event_type, event_id, data_lines
        if not data_lines and event_id is None and event_type == "message":
            return None
        raw_data = "\n".join(data_lines)
        try:
            payload: Any = json.loads(raw_data) if raw_data else {}
        except json.JSONDecodeError:
            payload = {"text": raw_data}
        event: dict[str, Any] = {
            "type": event_type,
            "event_id": event_id,
            "data": payload,
        }
        if isinstance(payload, dict):
            event.update(payload)
            event["type"] = event_type
            event["event_id"] = event_id or payload.get("event_id")
            event["data"] = payload
        event_type = "message"
        event_id = None
        data_lines = []
        return event

    for raw_line in lines:
        line = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, bytes) else str(raw_line)
        if line == "":
            event = consume()
            if event is not None:
                yield event
            continue
        if line.startswith(":"):
            continue
        field, separator, value = line.partition(":")
        if not separator:
            value = ""
        elif value.startswith(" "):
            value = value[1:]
        if field == "event":
            event_type = value or "message"
        elif field == "id":
            event_id = value or None
        elif field == "data":
            data_lines.append(value)
    event = consume()
    if event is not None:
        yield event


def _with_agent_delivery(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    artifact_values = payload.get("artifacts")
    artifacts = [item for item in artifact_values if isinstance(item, dict)] if isinstance(artifact_values, list) else []
    completion = payload.get("completion")
    completion = completion if isinstance(completion, dict) else {}
    primary_ids = {str(value) for value in completion.get("primary_artifact_ids") or [] if value}
    supporting_ids = {str(value) for value in completion.get("supporting_artifact_ids") or [] if value}

    def role(artifact: dict[str, Any], key: str) -> str:
        metadata = artifact.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        return str(metadata.get(key) or "").strip().lower()

    primary_indexes = {
        index
        for index, artifact in enumerate(artifacts)
        if str(artifact.get("id") or "") in primary_ids
    }
    if not primary_indexes:
        primary_indexes = {
            index
            for index, artifact in enumerate(artifacts)
            if role(artifact, "delivery_role") == "primary"
            or role(artifact, "artifact_role") in _FINAL_ARTIFACT_ROLES
        }
    if not primary_indexes:
        completed_node_ids = {
            str(step.get("node_id"))
            for step in payload.get("plan") or []
            if isinstance(step, dict) and step.get("node_id") and step.get("status") == "done"
        }
        dependency_ids = {
            str(dependency)
            for step in payload.get("plan") or []
            if isinstance(step, dict)
            for dependency in step.get("depends_on") or []
        }
        terminal_ids = completed_node_ids - dependency_ids
        primary_indexes = {
            index
            for index, artifact in enumerate(artifacts)
            if role(artifact, "artifact_role") not in _INTERNAL_ARTIFACT_ROLES
            and role(artifact, "plan_node_id") in terminal_ids
        }
    if not primary_indexes:
        deliverable = [
            index
            for index, artifact in enumerate(artifacts)
            if str(artifact.get("kind") or "").lower()
            in {"video", "image", "document", "summary", "subtitle", "translation"}
            and role(artifact, "artifact_role") not in _INTERNAL_ARTIFACT_ROLES
        ]
        if deliverable:
            primary_indexes = {deliverable[-1]}
        elif artifacts:
            primary_indexes = {len(artifacts) - 1}

    supporting_indexes = {
        index
        for index, artifact in enumerate(artifacts)
        if index not in primary_indexes
        and (
            str(artifact.get("id") or "") in supporting_ids
            or role(artifact, "delivery_role") == "supporting"
            or role(artifact, "artifact_role") in _SUPPORTING_ARTIFACT_ROLES
        )
    }
    result["primary_artifacts"] = [
        artifact for index, artifact in enumerate(artifacts) if index in primary_indexes
    ]
    result["supporting_artifacts"] = [
        artifact for index, artifact in enumerate(artifacts) if index in supporting_indexes
    ]
    result["intermediate_artifacts"] = [
        artifact
        for index, artifact in enumerate(artifacts)
        if index not in primary_indexes and index not in supporting_indexes
    ]
    result["completion_message"] = str(completion.get("message") or "").strip() or None
    result["completion_title"] = str(completion.get("title") or "").strip() or None
    return result


def _with_agent_privacy_receipt(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    context_files = payload.get("context_files")
    contexts = context_files if isinstance(context_files, list) else []
    source_videos = [
        item
        for item in contexts
        if isinstance(item, dict) and str(item.get("kind") or "").lower() == "video"
    ]
    if any(item.get("cloud_file_id") or item.get("public_url") for item in source_videos):
        source_video = "cloud_reference_detected"
    elif source_videos:
        source_video = "stayed_local"
    else:
        source_video = "not_included"

    plan_value = payload.get("plan")
    plan = plan_value if isinstance(plan_value, list) else []
    completed_local_steps = [
        str(item.get("step") or item.get("name") or "")
        for item in plan
        if isinstance(item, dict)
        and str(item.get("executor") or "").lower() in {"local", "client"}
        and str(item.get("status") or "").lower() == "done"
    ]
    completed_cloud_steps = [
        str(item.get("step") or item.get("name") or "")
        for item in plan
        if isinstance(item, dict)
        and str(item.get("executor") or "").lower() == "server"
        and str(item.get("status") or "").lower() == "done"
    ]
    hosted_inputs: set[str] = set()
    artifact_values = payload.get("artifacts")
    artifacts = artifact_values if isinstance(artifact_values, list) else []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        metadata = artifact.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        if not artifact.get("cloud_file_id") and str(metadata.get("agent_server_input") or "").lower() != "true":
            continue
        kind = str(artifact.get("kind") or "").lower()
        if kind in {"audio", "speech", "voice", "dub_audio"}:
            hosted_inputs.add("audio")
        elif kind in {"image", "frame", "frames", "sampled_frames", "video_frames"}:
            hosted_inputs.add("sampled_frames")
        elif kind in {"subtitle", "subtitles", "transcript", "text", "document", "markdown", "json"}:
            hosted_inputs.add("subtitles_or_text")
    if completed_cloud_steps and "extract_audio" in completed_local_steps:
        hosted_inputs.add("audio")
    if completed_cloud_steps and "extract_video_frames" in completed_local_steps:
        hosted_inputs.add("sampled_frames")
    final_local_steps = {
        "trim_video",
        "crop_resize_video",
        "transcode_video",
        "apply_watermark",
        "burn_subtitles",
        "render_highlight_clips",
        "render_visual_match_clips",
        "render_styled_edit",
        "mix_background_music",
        "merge_video_clips",
        "enhance_video",
        "compose_dubbed_video",
        "clean_cut",
    }
    result["privacy_receipt"] = {
        "source_video": source_video,
        "hosted_inputs": sorted(hosted_inputs),
        "local_steps": completed_local_steps,
        "cloud_steps": completed_cloud_steps,
        "local_final_video_processing": any(step in final_local_steps for step in completed_local_steps),
    }
    return result
