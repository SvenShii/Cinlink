from __future__ import annotations

from contextlib import ExitStack
import json
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any
from uuid import uuid4

from .config import Settings
from .dependencies import resolve_ffmpeg
from .dependencies import default_client_capabilities_from_dependencies
from .errors import CliError, normalize_remote_error


class RuntimeClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/v1/health", auth=False)

    def transcribe(self, input_path: Path, lang: str = "auto", out: Path | None = None, timeout: float | None = None) -> dict[str, Any]:
        checked = require_existing_file(input_path)
        if _looks_like_video(checked):
            with tempfile.TemporaryDirectory(prefix="cinlink-transcribe-audio-") as temp_dir:
                audio_path = Path(temp_dir) / "source.m4a"
                _extract_audio_for_upload(checked, audio_path)
                payload = self._multipart("/v1/transcribe", audio_path, {"source_lang": lang})
                result = self.wait_for_job(payload["job_id"], timeout or self.settings.timeout_sec)
                return self._localize_job_outputs(result, out or checked.parent / f"{checked.stem}.cinlink", ("subtitle_path", "transcript_path", "source_reference_subtitle_path", "elevenlabs_payload_path"))
        payload = self._multipart("/v1/transcribe", checked, {"source_lang": lang})
        result = self.wait_for_job(payload["job_id"], timeout or self.settings.timeout_sec)
        return self._localize_job_outputs(result, out or checked.parent / f"{checked.stem}.cinlink", ("subtitle_path", "transcript_path", "source_reference_subtitle_path", "elevenlabs_payload_path"))

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
        payload = self._multipart(
            "/v1/translate",
            input_path,
            {
                "from_lang": from_lang,
                "to_lang": to_lang,
                "bilingual": "true" if bilingual else "false",
                "delivery": delivery,
                "output_dir": str(out) if out else None,
            },
        )
        if isinstance(payload, dict) and "job_id" in payload and payload.get("status") not in {"done", "failed"}:
            payload = self.wait_for_job(payload["job_id"], timeout or self.settings.timeout_sec)
        return self._localize_job_outputs(
            payload,
            out or input_path.parent / f"{input_path.stem}.cinlink",
            (
                "subtitle_path",
                "translated_subtitle_path",
                "output_subtitle_path",
                "source_subtitle_path",
                "source_reference_subtitle_path",
                "translated_text_path",
            ),
        )

    def dub(
        self,
        video_path: Path,
        subtitle_path: Path,
        reference_subtitle_path: Path | None = None,
        voice: str | None = None,
        language: str = "zh",
        out: Path | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        video = require_existing_file(video_path)
        subtitle = require_existing_file(subtitle_path)
        reference_subtitle = require_existing_file(reference_subtitle_path) if reference_subtitle_path else None
        data = {
            "language": language,
            "voice": voice,
            "output_dir": str(out) if out else None,
        }
        fields = {key: value for key, value in data.items() if value is not None}
        with ExitStack() as stack:
            video_handle = stack.enter_context(video.open("rb"))
            subtitle_handle = stack.enter_context(subtitle.open("rb"))
            files: dict[str, Any] = {
                "file": (video.name, video_handle),
                "subtitle": (subtitle.name, subtitle_handle),
            }
            if reference_subtitle:
                reference_handle = stack.enter_context(reference_subtitle.open("rb"))
                files["reference_subtitle"] = (reference_subtitle.name, reference_handle)
            payload = self._request("POST", "/v1/dub", data=fields, files=files)
        if isinstance(payload, dict) and "job_id" in payload and payload.get("status") not in {"done", "failed"}:
            return self.wait_for_job(payload["job_id"], timeout or self.settings.timeout_sec)
        return payload

    def summarize(self, input_path: Path, out: Path | None = None, max_highlights: int = 3) -> dict[str, Any]:
        return self._multipart("/v1/summarize", input_path, {"output_dir": str(out) if out else None, "max_highlights": str(max_highlights)})

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
        return self._multipart(
            "/v1/shorten",
            video_path,
            {
                "output_dir": str(out) if out else None,
                "max_clips": str(max_clips),
                "target_duration_sec": str(target_duration),
                "style_preset": style_preset,
                "music_mode": music_mode,
                "music_prompt": music_prompt,
            },
        )

    def image(self, prompt: str, out: Path | None = None, aspect_ratio: str = "1:1", image_size: str = "1K", model: str | None = None) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/image",
            json_body=_compact({"prompt": prompt, "output_dir": str(out) if out else None, "aspect_ratio": aspect_ratio, "image_size": image_size, "model": model}),
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
        generation_mode: str = "text",
        first_frame_image_url: str | None = None,
        reference_image_urls: list[str] | None = None,
        reference_video_urls: list[str] | None = None,
        reference_audio_urls: list[str] | None = None,
        model: str | None = None,
        model_name: str | None = None,
        model_version: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
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
                    "generation_mode": generation_mode,
                    "first_frame_image_url": first_frame_image_url,
                    "reference_image_urls": reference_image_urls or [],
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
        mode: str = "execute",
        client_capabilities: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        request_files = [_context_file_payload(path) for path in (context_files or [])]
        return self._request(
            "POST",
            "/v1/agent/runs",
            json_body={
                "conversation_id": conversation_id or f"cli-{uuid4()}",
                "prompt": prompt,
                "context_files": request_files,
                "client_capabilities": client_capabilities or default_client_capabilities(),
                "mode": mode,
            },
        )

    def get_agent_run(self, run_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/agent/runs/{run_id}")

    def wait_for_agent_run(self, run_id: str, timeout: float | None = None) -> dict[str, Any]:
        deadline = time.time() + (timeout or self.settings.timeout_sec)
        while True:
            payload = self.get_agent_run(run_id)
            if payload.get("status") in {"done", "failed", "requires_user_input", "waiting_for_local"}:
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
                    raise CliError(str(error.get("code") or "processing_failed"), str(error.get("message") or "Remote job failed."), {"job_id": job_id})
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
            raise CliError("dependency_missing", "The Python package `httpx` is required to download generated videos.") from exc
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
            raise CliError("network_error", f"Could not download generated video: {exc}") from exc
        if response.status_code >= 400:
            raise CliError("remote_error", f"Generated video download failed with HTTP {response.status_code}.")
        destination.write_bytes(response.content)
        return destination

    def _multipart(self, path: str, input_path: Path, fields: dict[str, Any]) -> dict[str, Any]:
        checked = require_existing_file(input_path)
        data = {key: value for key, value in fields.items() if value is not None}
        with checked.open("rb") as file_handle:
            return self._request("POST", path, data=data, files={"file": (checked.name, file_handle)})

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
        raise CliError("processing_failed", "ffmpeg failed to extract audio before transcription.", {"stderr": completed.stderr[-2000:]})


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


def _context_file_payload(path: Path) -> dict[str, Any]:
    checked = require_existing_file(path)
    suffix = checked.suffix.lower()
    if suffix in {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm", ".mpg", ".mpeg"}:
        kind = "video"
    elif suffix in {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}:
        kind = "audio"
    elif suffix in {".srt", ".vtt", ".ass", ".ssa", ".txt"}:
        kind = "subtitle"
    elif suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        kind = "image"
    else:
        kind = "other"
    return {"id": None, "name": checked.name, "kind": kind, "local_hint": str(checked), "metadata": {}}
