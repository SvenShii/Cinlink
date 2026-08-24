from __future__ import annotations

from typing import Any


TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "configure": {
        "description": "Store a CinLink API key and optional runtime/billing base URLs for later tool calls.",
        "input_schema": {
            "type": "object",
            "required": ["api_key"],
            "properties": {
                "api_key": {"type": "string", "description": "CinLink API key, for example as_live_xxx."},
                "runtime_base": {"type": "string", "default": "https://runtime.cinlink.ai"},
                "billing_base": {"type": "string", "default": "https://app.cinlink.ai"},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "config_path": {"type": "string"},
                "runtime_base": {"type": "string"},
                "billing_base": {"type": "string"},
            },
        },
    },
    "doctor": {
        "description": "Check hosted runtime health and local dependency status. Use this before local-only tasks such as subtitle burn or voice separation.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "runtime_health": {"type": "object"},
                "local_dependencies": {"type": "object"},
            },
        },
    },
    "setup_local_deps": {
        "description": "Check and optionally install CinLink local dependencies. Prompts or requires explicit yes before installing ffmpeg; optional voice-separation and enhancement components install only when requested.",
        "input_schema": {
            "type": "object",
            "properties": {
                "yes": {"type": "boolean", "default": False, "description": "Install recommended dependencies without prompting."},
                "dry_run": {"type": "boolean", "default": False, "description": "Return the commands that would run without installing anything."},
                "skip_ffmpeg": {"type": "boolean", "default": False},
                "with_voice_separation": {"type": "boolean", "default": False, "description": "Also install optional demucs and soundfile for local voice separation/background preservation."},
                "skip_voice_separation": {"type": "boolean", "default": False},
                "with_enhancement": {"type": "boolean", "default": False, "description": "Also configure the optional local waifu2x image/video enhancement component."},
                "skip_enhancement": {"type": "boolean", "default": False},
            },
        },
        "output_schema": {"type": "object"},
    },
    "transcribe": {
        "description": "Transcribe a local video or audio file into subtitles.",
        "input_schema": {
            "type": "object",
            "required": ["input_path"],
            "properties": {
                "input_path": {"type": "string", "description": "Absolute path to a local media file."},
                "lang": {"type": "string", "default": "auto"},
                "out": {"type": "string"},
                "timeout": {"type": "number", "default": 1800},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "subtitle_path": {"type": "string"},
                "preview_text": {"type": "string"},
                "engine": {"type": "string"},
            },
        },
    },
    "translate": {
        "description": "Translate subtitles, or transcribe then translate a local media file. For local video input, the CLI extracts audio with ffmpeg and keeps the full video local before calling the hosted runtime. Voice delivery uses hosted dubbing when available; it does not require user-side Demucs unless the user asks for local voice separation or preserved background music.",
        "input_schema": {
            "type": "object",
            "required": ["input_path"],
            "properties": {
                "input_path": {"type": "string"},
                "from_lang": {"type": "string", "default": "auto"},
                "to_lang": {"type": "string", "default": "zh"},
                "bilingual": {"type": "boolean", "default": False},
                "delivery": {"type": "string", "enum": ["subtitle", "voice"], "default": "subtitle"},
                "out": {"type": "string"},
                "timeout": {"type": "number", "default": 1800},
            },
        },
        "output_schema": {"type": "object"},
    },
    "add_subtitles": {
        "description": "App-parity workflow for adding subtitles to a video: use an existing subtitle if provided, otherwise transcribe the video, or translate to target_lang, then burn the subtitle into the local video with ffmpeg.",
        "input_schema": {
            "type": "object",
            "required": ["video_path"],
            "properties": {
                "video_path": {"type": "string"},
                "subtitle_path": {"type": "string", "description": "Optional existing .srt/.ass/.vtt file. If omitted, hosted transcribe or translate creates one first."},
                "source_lang": {"type": "string", "default": "auto"},
                "target_lang": {"type": "string", "description": "Optional target language. When set, the workflow translates subtitles before burning."},
                "bilingual": {"type": "boolean", "default": False},
                "out": {"type": "string"},
                "timeout": {"type": "number", "default": 1800},
                "font_size": {"type": "integer", "default": 18},
                "font_name": {"type": "string", "default": "Arial"},
                "font_color": {"type": "string", "description": "#RRGGBB", "default": "#FFFFFF"},
                "outline_color": {"type": "string", "description": "#RRGGBB", "default": "#000000"},
                "outline_width": {"type": "number", "default": 1.0},
                "margin_v": {"type": "integer", "default": 20},
                "position": {"type": "string", "enum": ["top", "bottom"], "default": "bottom"},
                "no_brand_kit": {"type": "boolean", "default": False, "description": "Ignore the saved Brand Kit for this render."},
                "watermark_text": {"type": "string"},
                "watermark_position": {"type": "string", "enum": ["top-left", "top-right", "bottom-left", "bottom-right", "center"], "default": "top-right"},
                "watermark_font_size": {"type": "integer"},
                "watermark_color": {"type": "string", "description": "#RRGGBB"},
                "watermark_opacity": {"type": "number", "default": 0.72},
                "watermark_margin": {"type": "integer", "default": 24},
                "watermark_image_path": {"type": "string"},
                "watermark_image_position": {"type": "string", "enum": ["top-left", "top-right", "bottom-left", "bottom-right", "center"], "default": "top-right"},
                "watermark_image_width": {"type": "integer"},
                "watermark_image_opacity": {"type": "number", "default": 0.72},
                "watermark_image_margin": {"type": "integer", "default": 24},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "video_output_path": {"type": "string"},
                "subtitle_path": {"type": "string"},
                "steps": {"type": "array"},
            },
        },
    },
    "dub": {
        "description": "Generate dubbed speech/audio using an existing translated subtitle. When video_path is a video, the CLI extracts audio locally before calling the hosted /v1/dub runtime. Speaker-aligned or voice-cloned output also needs an original-language reference subtitle with matching cues.",
        "input_schema": {
            "type": "object",
            "required": ["video_path", "subtitle_path"],
            "properties": {
                "video_path": {"type": "string", "description": "Absolute path to a local video or already-extracted reference audio file."},
                "subtitle_path": {"type": "string"},
                "reference_subtitle_path": {
                    "type": "string",
                    "description": "Original-language timed subtitle for speaker alignment. If omitted, the CLI searches sibling source.reference.srt, subtitle.reference.srt, then source.srt.",
                },
                "reference_audio_paths": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "Optional speaker_id to local reference audio path mapping, for example {'speaker_0':'/absolute/ref.wav'}. Sent as reference_audio__<speaker_id> multipart fields.",
                },
                "voice": {"type": "string"},
                "language": {"type": "string", "default": "zh"},
                "out": {"type": "string"},
                "timeout": {"type": "number", "default": 1800},
            },
        },
        "output_schema": {"type": "object"},
    },
    "burn": {
        "description": "Burn subtitles into a local video with ffmpeg. This is local-only and supports subtitle style and watermark options.",
        "input_schema": {
            "type": "object",
            "required": ["video_path", "subtitle_path"],
            "properties": {
                "video_path": {"type": "string"},
                "subtitle_path": {"type": "string"},
                "out": {"type": "string"},
                "font_size": {"type": "integer"},
                "font_name": {"type": "string"},
                "font_color": {"type": "string", "description": "#RRGGBB"},
                "outline_color": {"type": "string", "description": "#RRGGBB"},
                "outline_width": {"type": "number"},
                "margin_v": {"type": "integer"},
                "position": {"type": "string", "enum": ["top", "bottom"], "default": "bottom"},
                "no_brand_kit": {"type": "boolean", "default": False, "description": "Ignore the saved Brand Kit for this render."},
                "watermark_text": {"type": "string"},
                "watermark_position": {"type": "string", "enum": ["top-left", "top-right", "bottom-left", "bottom-right", "center"], "default": "top-right"},
                "watermark_font_size": {"type": "integer"},
                "watermark_color": {"type": "string", "description": "#RRGGBB"},
                "watermark_opacity": {"type": "number", "default": 0.72},
                "watermark_margin": {"type": "integer", "default": 24},
                "watermark_image_path": {"type": "string"},
                "watermark_image_position": {"type": "string", "enum": ["top-left", "top-right", "bottom-left", "bottom-right", "center"], "default": "top-right"},
                "watermark_image_width": {"type": "integer"},
                "watermark_image_opacity": {"type": "number", "default": 0.72},
                "watermark_image_margin": {"type": "integer", "default": 24},
            },
        },
        "output_schema": {"type": "object"},
    },
    "apply_watermark": {
        "description": "Apply a text or image watermark to a local video. Saved Brand Kit logo and watermark settings are used automatically unless no_brand_kit is true.",
        "input_schema": {
            "type": "object",
            "required": ["video_path"],
            "properties": {
                "video_path": {"type": "string"},
                "out": {"type": "string"},
                "no_brand_kit": {"type": "boolean", "default": False},
                "watermark_text": {"type": "string"},
                "watermark_position": {"type": "string", "enum": ["top-left", "top-right", "bottom-left", "bottom-right", "center"]},
                "watermark_font_size": {"type": "integer"},
                "watermark_color": {"type": "string", "description": "#RRGGBB"},
                "watermark_opacity": {"type": "number"},
                "watermark_margin": {"type": "integer"},
                "watermark_image_path": {"type": "string"},
                "watermark_image_position": {"type": "string", "enum": ["top-left", "top-right", "bottom-left", "bottom-right", "center"]},
                "watermark_image_width": {"type": "integer"},
                "watermark_image_opacity": {"type": "number"},
                "watermark_image_margin": {"type": "integer"},
            },
        },
        "output_schema": {"type": "object"},
    },
    "enhance_image": {
        "description": "Enhance a local PNG, JPEG, WebP, HEIC, or GIF image with the CinLink waifu2x component and return a lossless PNG. Local-only; no API key or upload is required.",
        "input_schema": {
            "type": "object",
            "required": ["image_path"],
            "properties": {
                "image_path": {"type": "string"},
                "out": {"type": "string"},
                "scale": {"type": "integer", "enum": [2], "default": 2},
                "noise_level": {"type": "integer", "enum": [-1, 0, 1, 2, 3], "default": 1},
                "model": {"type": "string", "enum": ["photo", "cunet", "anime"], "default": "photo"},
            },
        },
        "output_schema": {"type": "object"},
    },
    "enhance_video": {
        "description": "Enhance a local video frame by frame with the CinLink waifu2x component, preserve its original audio, and return an MP4. Local-only; no API key or upload is required.",
        "input_schema": {
            "type": "object",
            "required": ["video_path"],
            "properties": {
                "video_path": {"type": "string"},
                "out": {"type": "string"},
                "scale": {"type": "integer", "enum": [2], "default": 2},
                "noise_level": {"type": "integer", "enum": [-1, 0, 1, 2, 3], "default": 1},
                "model": {"type": "string", "enum": ["photo", "cunet", "anime"], "default": "photo"},
            },
        },
        "output_schema": {"type": "object"},
    },
    "trim_video": {
        "description": "Cut a precise local video segment. Use matched start/end timestamps returned by library search or understanding workflows.",
        "input_schema": {
            "type": "object",
            "required": ["video_path", "start_sec", "end_sec"],
            "properties": {
                "video_path": {"type": "string"},
                "start_sec": {"type": "number", "minimum": 0},
                "end_sec": {"type": "number", "exclusiveMinimum": 0},
                "out": {"type": "string"},
            },
        },
        "output_schema": {"type": "object"},
    },
    "montage": {
        "description": "Render two or more selected local video ranges in order as a montage.",
        "input_schema": {
            "type": "object",
            "required": ["clips"],
            "properties": {
                "clips": {
                    "type": "array",
                    "minItems": 2,
                    "items": {
                        "type": "object",
                        "required": ["path"],
                        "properties": {
                            "path": {"type": "string"},
                            "start_sec": {"type": "number", "default": 0},
                            "end_sec": {"type": "number"},
                            "duration_sec": {"type": "number"},
                        },
                    },
                },
                "out": {"type": "string"},
            },
        },
        "output_schema": {"type": "object"},
    },
    "clean_cut": {
        "description": "Detect long pauses in a local video with ffmpeg. Use plan_only first to review indexed candidates, then export only user-approved selected_removal_indexes.",
        "input_schema": {
            "type": "object",
            "required": ["video_path"],
            "properties": {
                "video_path": {"type": "string"},
                "out": {"type": "string"},
                "minimum_silence_sec": {"type": "number", "default": 0.85},
                "noise_threshold_db": {"type": "number", "default": -35.0},
                "retained_pause_sec": {"type": "number", "default": 0.24},
                "minimum_removal_sec": {"type": "number", "default": 0.18},
                "plan_only": {
                    "type": "boolean",
                    "default": False,
                    "description": "Analyze and return candidate_removed_ranges without rendering a video.",
                },
                "selected_removal_indexes": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 0},
                    "uniqueItems": True,
                    "description": "Zero-based candidate indexes approved by the user. Omit to export every candidate.",
                },
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["planned", "done"]},
                "changed": {"type": "boolean"},
                "has_candidates": {"type": "boolean"},
                "source_video_path": {"type": "string"},
                "video_output_path": {"type": ["string", "null"]},
                "candidate_removed_ranges": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "index": {"type": "integer"},
                            "start_sec": {"type": "number"},
                            "end_sec": {"type": "number"},
                            "duration_sec": {"type": "number"},
                        },
                    },
                },
                "selected_removal_indexes": {"type": "array", "items": {"type": "integer"}},
                "removed_ranges": {"type": "array"},
                "keep_ranges": {"type": "array"},
                "artifacts": {"type": "array"},
            },
        },
    },
    "brand_kit": {
        "description": "Show, configure, or clear the persistent local Brand Kit used automatically by later caption and watermark exports.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["show", "set", "clear"], "default": "show"},
                "enabled": {"type": "boolean"},
                "font_size": {"type": "integer"},
                "font_name": {"type": "string"},
                "font_color": {"type": "string", "description": "#RRGGBB"},
                "outline_color": {"type": "string", "description": "#RRGGBB"},
                "outline_width": {"type": "number"},
                "margin_v": {"type": "integer"},
                "position": {"type": "string", "enum": ["top", "bottom"]},
                "watermark_text": {"type": "string"},
                "watermark_position": {"type": "string", "enum": ["top-left", "top-right", "bottom-left", "bottom-right", "center"]},
                "watermark_font_size": {"type": "integer"},
                "watermark_color": {"type": "string", "description": "#RRGGBB"},
                "watermark_opacity": {"type": "number"},
                "watermark_margin": {"type": "integer"},
                "watermark_image_path": {"type": ["string", "null"]},
                "watermark_image_position": {"type": "string", "enum": ["top-left", "top-right", "bottom-left", "bottom-right", "center"]},
                "watermark_image_width": {"type": ["integer", "null"]},
                "watermark_image_opacity": {"type": "number"},
                "watermark_image_margin": {"type": "integer"},
            },
        },
        "output_schema": {"type": "object"},
    },
    "mix_dubbed_audio": {
        "description": "Mix a generated dubbed audio track with the original local video audio and mux the result into a video. This is local-only and requires ffmpeg.",
        "input_schema": {
            "type": "object",
            "required": ["video_path", "dubbed_audio_path"],
            "properties": {
                "video_path": {"type": "string"},
                "dubbed_audio_path": {"type": "string"},
                "out": {"type": "string"},
                "original_volume": {"type": "number", "default": 0.65},
                "dubbed_volume": {"type": "number", "default": 1.0},
            },
        },
        "output_schema": {"type": "object"},
    },
    "summarize": {
        "description": "Summarize a local video, audio file, or subtitle file. For video input, the CLI extracts audio locally with ffmpeg and uploads only the audio.",
        "input_schema": {
            "type": "object",
            "required": ["input_path"],
            "properties": {
                "input_path": {"type": "string"},
                "out": {"type": "string"},
                "max_highlights": {"type": "integer", "default": 3, "minimum": 1, "maximum": 8},
            },
        },
        "output_schema": {"type": "object"},
    },
    "shorten": {
        "description": "Create a highlight plan for a long local video. The CLI keeps the video local, uploads extracted audio through the account-scoped Agent file endpoint, reuses its cloud_file_id for hosted analysis when supported, falls back to compatibility multipart upload, and returns source_video_path for local rendering.",
        "input_schema": {
            "type": "object",
            "required": ["video_path"],
            "properties": {
                "video_path": {"type": "string"},
                "out": {"type": "string"},
                "max_clips": {"type": "integer", "default": 5},
                "target_duration": {"type": "integer", "default": 45},
                "style_preset": {"type": "string"},
                "music_mode": {"type": "string", "default": "none"},
                "music_prompt": {"type": "string"},
                "output_language": {
                    "type": "string",
                    "enum": ["zh-Hans", "en", "ja"],
                    "description": "Language for generated clip titles, reasons, and plan presentation.",
                },
            },
        },
        "output_schema": {"type": "object"},
    },
    "image": {
        "description": "Generate an image from a text prompt and up to three remote or local reference images. Local references are uploaded through the authenticated CinLink reference-image endpoint.",
        "input_schema": {
            "type": "object",
            "required": ["prompt"],
            "properties": {
                "prompt": {"type": "string"},
                "out": {"type": "string"},
                "aspect_ratio": {"type": "string", "default": "1:1"},
                "image_size": {"type": "string", "default": "1K"},
                "reference_image_urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 3,
                    "description": "Remote URLs or absolute local image paths.",
                },
                "model": {"type": "string"},
                "timeout": {"type": "number", "default": 1800},
            },
        },
        "output_schema": {"type": "object"},
    },
    "video": {
        "description": "Generate a video from a text prompt or image/video/audio references. Local first-frame and reference image paths are uploaded through the authenticated CinLink reference-image endpoint before generation.",
        "input_schema": {
            "type": "object",
            "required": ["prompt"],
            "properties": {
                "prompt": {"type": "string"},
                "out": {"type": "string"},
                "aspect_ratio": {"type": "string", "default": "16:9"},
                "resolution": {"type": "string", "default": "720P"},
                "duration": {"type": "integer", "default": 5},
                "generate_audio": {"type": "boolean", "default": True},
                "watermark": {"type": "boolean", "default": False},
                "generation_mode": {
                    "type": "string",
                    "enum": ["text", "first_frame", "reference"],
                    "description": "Optional. Defaults to first_frame for a first-frame URL, reference for other reference URLs, otherwise text.",
                },
                "first_frame_image_url": {
                    "type": "string",
                    "description": "Remote URL or absolute local image path.",
                },
                "reference_image_urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 9,
                    "description": "Remote URLs or absolute local image paths.",
                },
                "reference_video_urls": {"type": "array", "items": {"type": "string"}},
                "reference_audio_urls": {"type": "array", "items": {"type": "string"}},
                "model": {"type": "string"},
                "model_name": {"type": "string"},
                "model_version": {"type": "string"},
                "timeout": {"type": "number", "default": 1800},
            },
        },
        "output_schema": {"type": "object"},
    },
    "deconstruct_video": {
        "description": "Deconstruct a local video into an editable shot plan. The full video stays local; CinLink samples scene frames locally and sends only those frames to the hosted deconstruction runtime.",
        "input_schema": {
            "type": "object",
            "required": ["video_path"],
            "properties": {
                "video_path": {"type": "string"},
                "out": {
                    "type": "string",
                    "description": "Output directory or deconstruction.json path.",
                },
                "replacement_references": {
                    "type": "array",
                    "maxItems": 8,
                    "items": {
                        "type": "object",
                        "required": ["role", "path"],
                        "properties": {
                            "role": {
                                "type": "string",
                                "enum": ["person", "product", "scene"],
                            },
                            "path": {"type": "string"},
                        },
                        "additionalProperties": False,
                    },
                },
                "language": {
                    "type": "string",
                    "default": "zh-Hans",
                    "maxLength": 32,
                    "description": "Language for titles, summaries, style analysis, and audio prompt. Generation prompts remain model-friendly English.",
                },
                "analysis_scope": {
                    "type": "string",
                    "default": "",
                    "maxLength": 2000,
                    "description": "Optional focus such as camera movement, product presentation, lighting, or transitions.",
                },
                "scene_threshold": {
                    "type": "number",
                    "default": 0.28,
                    "minimum": 0,
                    "maximum": 1,
                },
                "max_shots": {
                    "type": "integer",
                    "default": 120,
                    "minimum": 1,
                    "maximum": 120,
                },
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "plan_path": {"type": "string"},
                "source_video_path": {"type": "string"},
                "shot_count": {"type": "integer"},
                "privacy_receipt": {"type": "object"},
            },
        },
    },
    "regenerate_deconstruction": {
        "description": "Regenerate an editable CinLink deconstruction plan shot by shot, optionally replacing a person, product, or scene. Generated shots use the hosted runtime; continuity and final assembly happen locally.",
        "input_schema": {
            "type": "object",
            "required": ["plan_path"],
            "properties": {
                "plan_path": {"type": "string"},
                "out": {"type": "string"},
                "replacement_references": {
                    "type": "array",
                    "maxItems": 8,
                    "items": {
                        "type": "object",
                        "required": ["role", "path"],
                        "properties": {
                            "role": {
                                "type": "string",
                                "enum": ["person", "product", "scene"],
                            },
                            "path": {"type": "string"},
                        },
                        "additionalProperties": False,
                    },
                },
                "resolution": {"type": "string", "default": "720P"},
                "preserve_original_audio": {
                    "type": "boolean",
                    "default": True,
                },
                "model": {"type": "string"},
                "model_name": {"type": "string"},
                "model_version": {"type": "string"},
                "timeout": {"type": "number", "default": 1800},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "video_output_path": {"type": "string"},
                "plan_path": {"type": "string"},
                "primary_artifacts": {"type": "array"},
                "supporting_artifacts": {"type": "array"},
                "privacy_receipt": {"type": "object"},
            },
        },
    },
    "export_video": {
        "description": "Export a local edited video as MP4, MOV, AVI, or MKV with ffmpeg. No CinLink API key or cloud upload is required.",
        "input_schema": {
            "type": "object",
            "required": ["video_path"],
            "properties": {
                "video_path": {"type": "string"},
                "output_format": {
                    "type": "string",
                    "enum": ["mp4", "mov", "avi", "mkv"],
                    "default": "mp4",
                },
                "out": {"type": "string"},
            },
        },
        "output_schema": {"type": "object"},
    },
    "export_audio": {
        "description": "Export audio from a local video, or from a supplied local replacement audio track, as WAV or MP3. No CinLink API key or cloud upload is required.",
        "input_schema": {
            "type": "object",
            "required": ["video_path"],
            "properties": {
                "video_path": {"type": "string"},
                "audio_path": {"type": "string"},
                "output_format": {
                    "type": "string",
                    "enum": ["wav", "mp3"],
                    "default": "wav",
                },
                "out": {"type": "string"},
            },
        },
        "output_schema": {"type": "object"},
    },
    "export_editor_project": {
        "description": "Create a local editor handoff for CapCut, Adobe Premiere Pro, Final Cut Pro, or DaVinci Resolve. CinLink creates portable media/XML/FCPXML/SRT assets but does not launch desktop editor applications.",
        "input_schema": {
            "type": "object",
            "required": ["video_path", "target"],
            "properties": {
                "video_path": {"type": "string"},
                "target": {
                    "type": "string",
                    "enum": ["capcut", "premiere", "final-cut", "resolve"],
                },
                "subtitle_path": {"type": "string"},
                "audio_path": {"type": "string"},
                "out": {
                    "type": "string",
                    "description": "Output directory.",
                },
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "project_output_path": {"type": "string"},
                "package_path": {"type": ["string", "null"]},
                "primary_artifacts": {"type": "array"},
                "supporting_artifacts": {"type": "array"},
            },
        },
    },
    "nlu": {
        "description": "Route a natural-language media task into an action.",
        "input_schema": {
            "type": "object",
            "required": ["prompt"],
            "properties": {
                "prompt": {"type": "string"},
                "has_video": {"type": "boolean", "default": False},
                "has_subtitle": {"type": "boolean", "default": False},
                "pending_target_language": {"type": "string"},
                "context_files": {"type": "array", "items": {"type": "string"}},
            },
        },
        "output_schema": {"type": "object"},
    },
    "agent_run": {
        "description": "Submit a server-side agent run and optionally wait for completion. Hosted-first: provider work runs on the server. Local voice separation/preserved background music requires user-installed ffmpeg, Demucs, and soundfile because the hosted server does not provide Demucs.",
        "input_schema": {
            "type": "object",
            "required": ["prompt"],
            "properties": {
                "prompt": {"type": "string"},
                "conversation_id": {"type": "string"},
                "context_file": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Local files explicitly submitted with this run. The CLI marks them selection_scope=current_submission and input_priority=highest so they outrank stale conversation context without hiding ambiguity among multiple current files.",
                },
                "context_descriptors": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "name": {"type": "string"},
                            "kind": {"type": "string", "enum": ["video", "audio", "subtitle", "image", "document", "edit_plan", "other"]},
                            "id": {"type": "string"},
                            "entity_id": {"type": "string"},
                            "local_asset_id": {"type": "string"},
                            "cloud_file_id": {"type": "string"},
                            "public_url": {"type": "string"},
                            "metadata": {"type": "object", "additionalProperties": True},
                        },
                    },
                    "description": "Rich context artifacts for follow-up workflows. Preserve cloud_file_id, public_url, artifact_role, and producer_step from earlier results. For an artifact explicitly selected in the current request, set metadata.selection_scope=current_submission and metadata.input_priority=highest; historical descriptors are not elevated automatically.",
                },
                "client_request_id": {
                    "type": "string",
                    "description": "Optional idempotency/correlation id from the caller. Reusing it in the same conversation lets the hosted runtime dedupe a submitted run.",
                },
                "hidden_context": {
                    "type": "string",
                    "description": "Invisible client UI context such as selected settings. Do not put secrets here; visible user prompt and explicit task parameters override conflicts.",
                },
                "app_language": {
                    "type": "string",
                    "description": "User-facing agent language, for example zh, en, or ja.",
                },
                "mode": {"type": "string", "enum": ["plan", "execute"], "default": "execute"},
                "task_intent": {
                    "type": "string",
                    "description": "High-priority app-surface intent, for example add_subtitles, translate_and_burn_subtitles, dub_video, summarize_video, shorten_video, deconstruct_video, edit_video, watermark, enhance_video, multi_video_montage, generate_image, or generate_video.",
                },
                "task_parameters": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "Explicit app slot values such as target_language=en, output_language=zh-Hans, translation_mode=subtitle|voice, output_delivery=subtitle_file|burned_video, source_language=auto, subtitle_language=en, analysis_scope=camera, target_duration_sec=30, require_audio=true, or watermark style/position values. Free-form translation should resolve translation_mode and subtitle delivery without silently choosing model defaults.",
                },
                "conversation_state": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "Optional persisted agent state. Current prompt and task_parameters override historical defaults.",
                },
                "wait": {"type": "boolean", "default": False},
                "include_events": {
                    "type": "boolean",
                    "default": False,
                    "description": "When waiting, include public planning/reasoning events. Hidden model scratch work is never exposed.",
                },
                "timeout": {"type": "number", "default": 1800},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "completion_message": {"type": ["string", "null"]},
                "completion_title": {"type": ["string", "null"]},
                "primary_artifacts": {"type": "array"},
                "supporting_artifacts": {"type": "array"},
                "intermediate_artifacts": {"type": "array"},
                "clarifications": {
                    "type": "array",
                    "description": "Localized structured questions returned when status is requires_user_input. Present every question, assistant_hint, option label, and description; collect all answers, then call agent_clarify once. file_select and image_select require an exact stable id, exact filename, or authorized local path.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "slot_key": {"type": "string"},
                            "question": {"type": "string"},
                            "question_key": {"type": ["string", "null"]},
                            "input_kind": {
                                "type": "string",
                                "enum": ["single_select", "text", "file_select", "image_select"],
                            },
                            "params": {"type": "object", "additionalProperties": {"type": "string"}},
                            "assistant_hint": {"type": ["string", "null"]},
                            "metadata": {"type": "object", "additionalProperties": {"type": "string"}},
                            "options": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "value": {"type": "string"},
                                        "label": {"type": "string"},
                                        "description": {"type": ["string", "null"]},
                                        "is_default": {"type": "boolean"},
                                        "label_key": {"type": ["string", "null"]},
                                        "description_key": {"type": ["string", "null"]},
                                        "params": {"type": "object", "additionalProperties": {"type": "string"}},
                                    },
                                },
                            },
                        },
                    },
                },
                "workflow_decision": {
                    "type": "object",
                    "description": "Structured route decision. Inspect slot_provenance before execution-sensitive choices; model_default and unknown do not count as user-resolved translation_mode or output_delivery. media_intent is the canonical operation/source/output/parameters envelope for every media workflow.",
                    "properties": {
                        "media_intent": {
                            "type": ["object", "null"],
                            "description": "Canonical media intent. Legacy subtitle-specific top-level fields are input compatibility only.",
                            "properties": {
                                "operation": {"type": "string"},
                                "source": {
                                    "type": "object",
                                    "properties": {
                                        "kind": {"type": "string"},
                                        "bindings": {"type": "object", "additionalProperties": {"type": "string"}},
                                        "reference": {"type": "string"},
                                    },
                                },
                                "output": {
                                    "type": "object",
                                    "properties": {
                                        "kind": {"type": "string"},
                                        "delivery": {"type": "string"},
                                    },
                                },
                                "parameters": {"type": "object", "additionalProperties": {"type": "string"}},
                            },
                        },
                        "slot_provenance": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "slot": {"type": "string"},
                                    "source": {
                                        "type": "string",
                                        "enum": [
                                            "user_explicit",
                                            "structured_parameter",
                                            "resolved_clarification",
                                            "conversation_context",
                                            "model_default",
                                            "unknown",
                                        ],
                                    },
                                    "evidence": {"type": ["string", "null"]},
                                },
                            },
                        }
                    },
                },
                "agent_events": {"type": "array"},
            },
        },
    },
    "agent_clarify": {
        "description": "Answer all structured clarifications from a CinLink Agent run and continue once. Planning clarifications preserve the prior workflow, canonical media intent, task frame, conversation, context artifacts, language, and resolved slots. Runtime dubbing-reference clarifications resume the original run in place.",
        "input_schema": {
            "type": "object",
            "required": ["run_id"],
            "properties": {
                "run_id": {
                    "type": "string",
                    "description": "Run whose status is requires_user_input and whose clarifications array contains the question being answered.",
                },
                "clarification_id": {
                    "type": "string",
                    "description": "Single-question compatibility form. For multiple clarifications, use answers with the complete answer set.",
                },
                "value": {
                    "type": "string",
                    "description": "Option value or localized label for a single_select clarification.",
                },
                "answer": {
                    "type": "string",
                    "description": "Free-form answer for text, or an exact stable id, exact filename, or authorized local path for file_select/image_select. It may also contain an option value or label.",
                },
                "answers": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "All answers keyed by clarification id or slot_key. Required as a complete set when the run exposes multiple unresolved clarifications. target_duration_sec accepts 10-600 seconds, MM:SS, HH:MM:SS, or localized duration units.",
                },
                "client_request_id": {
                    "type": "string",
                    "description": "Optional idempotency/correlation id for the continuation run.",
                },
                "wait": {"type": "boolean", "default": False},
                "include_events": {
                    "type": "boolean",
                    "default": False,
                    "description": "When waiting, include public planning/reasoning events.",
                },
                "timeout": {"type": "number", "default": 1800},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "continued_from_run_id": {"type": "string"},
                "clarification_resolution": {
                    "type": "string",
                    "enum": ["in_place"],
                    "description": "Present when the original Agent run was resumed directly instead of creating a continuation run.",
                },
                "answered_clarification": {"type": "object"},
                "answered_clarifications": {"type": "array"},
                "status": {"type": "string"},
                "clarifications": {"type": "array"},
                "primary_artifacts": {"type": "array"},
                "supporting_artifacts": {"type": "array"},
                "agent_events": {"type": "array"},
            },
        },
    },
    "agent_events": {
        "description": "Read the hosted agent's public SSE planning and reasoning event stream for a run. This returns user-facing progress events, not private model scratch work.",
        "input_schema": {
            "type": "object",
            "required": ["run_id"],
            "properties": {
                "run_id": {"type": "string"},
                "last_event_id": {"type": "string"},
                "timeout": {"type": "number"},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "events": {"type": "array"},
            },
        },
    },
}


def list_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "description": schema["description"],
            "input_schema": schema["input_schema"],
            "output_schema": schema["output_schema"],
        }
        for name, schema in TOOL_SCHEMAS.items()
    ]
