"""Pipeline command construction for the WebUI.

Pure logic extracted from app.py: given the run parameters, build the CLI
command for main_improved.py. No side effects, no gradio imports — fully
unit-testable.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils import safe_int

WORKFLOW_MAP = {"Full": "1", "Cut Only": "2", "Subtitles Only": "3"}


def build_command(main_script_path, source_args, *, segments=None, viral=False,
                  themes=None, min_duration=None, max_duration=None, model=None,
                  ai_backend=None, api_key=None, ai_model_name=None, chunk_size=None,
                  workflow=None, face_model=None, face_mode=None,
                  face_detect_interval=None, no_face_mode=None,
                  face_filter_thresh=None, face_two_thresh=None,
                  face_conf_thresh=None, face_dead_zone=None,
                  focus_active_speaker=False, active_speaker_mar=None,
                  active_speaker_score_diff=None, include_motion=False,
                  active_speaker_motion_threshold=None,
                  active_speaker_motion_sensitivity=None, active_speaker_decay=None,
                  translate_target=None, subtitle_config_path=None,
                  safety_mode=None, safety_ai=None,
                  # --- v6 features (Roadmap 5.2 / Sprint 3 / 4.2 / 2.4) ---
                  platform=None, polish=False, music=None, logo=None,
                  checkpoint=None, metadata_gate=None, cookies_browser=None,
                  title_language=None):
    """Assemble the full CLI command for main_improved.py.

    `source_args` holds the input-source-specific flags already resolved by
    the caller (e.g. ["--url", url] or ["--project-path", path]).
    """
    workflow = workflow or "Full"
    ai_backend = ai_backend or "manual"
    face_mode = face_mode or "auto"
    no_face_mode = no_face_mode or "padding"

    cmd = [sys.executable, main_script_path, *source_args]

    if translate_target and translate_target != "None":
        cmd.extend(["--translate-target", translate_target])

    cmd.extend(["--segments", str(safe_int(segments, 3))])
    if viral:
        cmd.append("--viral")
    if themes:
        cmd.extend(["--themes", themes])
    cmd.extend(["--min-duration", str(safe_int(min_duration, 15))])
    cmd.extend(["--max-duration", str(safe_int(max_duration, 90))])
    cmd.extend(["--model", model or "large-v3-turbo"])
    cmd.extend(["--ai-backend", ai_backend])
    if api_key:
        cmd.extend(["--api-key", api_key])
    if ai_model_name:
        cmd.extend(["--ai-model-name", str(ai_model_name)])
    if chunk_size not in (None, ""):
        cmd.extend(["--chunk-size", str(safe_int(chunk_size, 70000))])

    cmd.extend(["--workflow", WORKFLOW_MAP.get(workflow, "1")])
    cmd.extend(["--face-model", face_model])
    cmd.extend(["--face-mode", face_mode])
    if face_detect_interval:
        cmd.extend(["--face-detect-interval", str(face_detect_interval)])
    if no_face_mode:
        cmd.extend(["--no-face-mode", no_face_mode])

    if face_filter_thresh is not None:
        cmd.extend(["--face-filter-threshold", str(face_filter_thresh)])
    if face_two_thresh is not None:
        cmd.extend(["--face-two-threshold", str(face_two_thresh)])
    if face_conf_thresh is not None:
        cmd.extend(["--face-confidence-threshold", str(face_conf_thresh)])
    if face_dead_zone is not None:
        cmd.extend(["--face-dead-zone", str(face_dead_zone)])

    cmd.append("--skip-prompts")
    if focus_active_speaker:
        cmd.append("--focus-active-speaker")
        if active_speaker_mar is not None:
            cmd.extend(["--active-speaker-mar", str(active_speaker_mar)])
        if active_speaker_score_diff is not None:
            cmd.extend(["--active-speaker-score-diff", str(active_speaker_score_diff)])
        if include_motion:
            cmd.append("--include-motion")
        if active_speaker_motion_threshold is not None:
            cmd.extend(["--active-speaker-motion-threshold", str(active_speaker_motion_threshold)])
        if active_speaker_motion_sensitivity is not None:
            cmd.extend(["--active-speaker-motion-sensitivity", str(active_speaker_motion_sensitivity)])
        if active_speaker_decay is not None:
            cmd.extend(["--active-speaker-decay", str(active_speaker_decay)])

    if subtitle_config_path:
        cmd.extend(["--subtitle-config", subtitle_config_path])

    if safety_mode and safety_mode != "block":
        # "block" is the CLI default; only pass explicit overrides
        cmd.extend(["--safety-mode", str(safety_mode)])

    if safety_ai and safety_ai != "on":
        # "on" is the CLI default; only pass explicit overrides
        cmd.extend(["--safety-ai", str(safety_ai)])

    # --- v6 flags (only when the user explicitly enables them) ---
    if platform:
        cmd.extend(["--platform", str(platform)])
    if polish:
        cmd.append("--polish")
        cmd.append("on")
        if music:
            cmd.extend(["--music", music])
        if logo:
            cmd.extend(["--logo", logo])
    if checkpoint and checkpoint != "on":
        # "on" is the CLI default; only pass explicit overrides
        cmd.extend(["--checkpoint", str(checkpoint)])
    if metadata_gate and metadata_gate != "warn":
        # "warn" is the CLI default; only pass explicit overrides
        cmd.extend(["--metadata-gate", str(metadata_gate)])

    if cookies_browser:
        cmd.extend(["--cookies-from-browser", str(cookies_browser)])

    if title_language and title_language != "auto":
        cmd.extend(["--title-language", str(title_language)])

    return cmd
