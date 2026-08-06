import gradio as gr
import subprocess
import os
import sys
import json
import psutil
import shutil
import datetime
import time
import urllib.parse
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import uvicorn

import re
import library # Module for Library Logic
import subtitle_handler as subs # Module for Subtitles
import subtitle_editor as editor # Module for Editor Logic
import segments_review # Module for Segments Review Logic
import batch_queue # Module for Batch Queue Logic
import settings_store # Module for persistent AI settings (save/load Gemini key)

# Path to the main script
MAIN_SCRIPT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main_improved.py")
WORKING_DIR = os.path.dirname(MAIN_SCRIPT_PATH)
sys.path.append(WORKING_DIR)

from i18n.i18n import I18nAuto, DEFAULT_LANGUAGE
i18n = I18nAuto(DEFAULT_LANGUAGE)

# Version banner at startup — helps confirm you run the latest code
try:
    from app_version import VERSION as _VERSION
    print(f"ViralCutter WebUI v{_VERSION} (update: git reset --hard origin/main)")
except Exception:
    pass

def tr(key):
    return i18n(key)


# --- AI model lists (were referenced but never defined — fixed in v6.1) ---
GEMINI_MODELS = [
    "gemini-2.5-flash-lite-preview-09-2025",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-pro",
]
G4F_MODELS = [
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-4-turbo",
    "gpt-3.5-turbo",
    "claude-3-haiku",
    "llama-3.1-8b",
    "gemini-1.5-flash",
    "gemini-pro",
    "mistral-7b",
    "mixtral-8x7b",
]


def get_local_models():
    """List .gguf models in the models/ folder (local LLM backend)."""
    models_dir = os.path.join(WORKING_DIR, "models")
    if not os.path.isdir(models_dir):
        return []
    return sorted(f for f in os.listdir(models_dir) if f.endswith(".gguf"))



# --- PRESETS DEFINITIONS ---
FACE_PRESETS = {
    "Default (Balanced)": {"thresh": 0.35, "two_face": 0.60, "conf": 0.40, "dead_zone": 150},
    "Stable (Focus Main)": {"thresh": 0.60, "two_face": 0.80, "conf": 0.60, "dead_zone": 200},
    "Sensitive (Catch All)": {"thresh": 0.10, "two_face": 0.40, "conf": 0.30, "dead_zone": 100},
    "High Precision": {"thresh": 0.40, "two_face": 0.65, "conf": 0.75, "dead_zone": 150},
}

EXPERIMENTAL_PRESETS = {
    "Default (Off)": {"focus": False, "mar": 0.03, "score": 1.5, "motion": False, "motion_th": 3.0, "motion_sens": 0.05, "decay": 2.0},
    "Active Speaker (Balanced)": {"focus": True, "mar": 0.03, "score": 1.5, "motion": True, "motion_th": 3.0, "motion_sens": 0.05, "decay": 2.0},
    "Active Speaker (Sensitive)": {"focus": True, "mar": 0.02, "score": 1.0, "motion": True, "motion_th": 2.0, "motion_sens": 0.10, "decay": 1.0},
    "Active Speaker (Stable)": {"focus": True, "mar": 0.05, "score": 2.5, "motion": False, "motion_th": 5.0, "motion_sens": 0.02, "decay": 3.0},
}
# ---------------------------

VIRALS_DIR = os.path.join(WORKING_DIR, "VIRALS")
MODELS_DIR = os.path.join(WORKING_DIR, "models")

# Ensure directories exist
os.makedirs(VIRALS_DIR, exist_ok=True)
os.makedirs(MODELS_DIR, exist_ok=True)

# Global variables
current_process = None

from pipeline import build_command
from utils import (
    PROGRESS_STAGES,
    empty_progress_state,
    convert_color_to_ass,
    build_subtitle_config,
    normalize_path,
    safe_int,
    safe_float,
    render_progress_html,
    render_tasks_html,
    render_error_html,
    summarize_error,
)
PROGRESS_ORDER = PROGRESS_STAGES
_safe_int = safe_int
_safe_float = safe_float
_normalize_path = normalize_path
_build_subtitle_config = build_subtitle_config


# ---------------------------------------------------------------------------
# v6.1 fixes — helpers that were referenced by the UI but never defined
# (face presets, experimental presets, subtitle template persistence)
# ---------------------------------------------------------------------------

TEMPLATES_FILE = os.path.join(WORKING_DIR, "subtitle_templates.json")


def load_templates():
    """All saved subtitle/settings templates ({} when none)."""
    if not os.path.exists(TEMPLATES_FILE):
        return {}
    try:
        with open(TEMPLATES_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_template(name, payload):
    """Persist a template dict. Returns an error string or None."""
    templates = load_templates()
    templates[name] = payload
    try:
        with open(TEMPLATES_FILE, "w", encoding="utf-8") as f:
            json.dump(templates, f, ensure_ascii=False, indent=2)
        return None
    except Exception as e:
        return str(e)


def template_choices():
    return sorted(load_templates().keys())


def apply_face_preset(preset_name):
    preset = FACE_PRESETS.get(preset_name, {})
    return (
        gr.update(value=preset.get("thresh", 0.35)),
        gr.update(value=preset.get("two_face", 0.60)),
        gr.update(value=preset.get("conf", 0.40)),
        gr.update(value=preset.get("dead_zone", 150)),
    )


def apply_experimental_preset(preset_name):
    preset = EXPERIMENTAL_PRESETS.get(preset_name, {})
    return (
        gr.update(value=bool(preset.get("focus", False))),
        gr.update(value=preset.get("mar", 0.03)),
        gr.update(value=preset.get("score", 1.5)),
        gr.update(value=bool(preset.get("motion", False))),
        gr.update(value=preset.get("motion_th", 3.0)),
        gr.update(value=preset.get("motion_sens", 0.05)),
        gr.update(value=preset.get("decay", 2.0)),
    )


# ---------------------------------------------------------------------------
# Persistent AI settings (v6.9) — save the Gemini key once, never retype it
# ---------------------------------------------------------------------------

_KEY_SOURCE_LABELS = {
    settings_store.KEY_SOURCE_ENV: i18n("from environment variable"),
    settings_store.KEY_SOURCE_SECURE: i18n("from encrypted store"),
    settings_store.KEY_SOURCE_FILE: i18n("saved in api_config.json"),
    settings_store.KEY_SOURCE_NONE: "",
}


def settings_status_text(api_key=None):
    """Status line for the AI settings card: masked key + where it lives."""
    saved = settings_store.load_ui_settings()
    current_key = (api_key if api_key is not None else saved["api_key"]) or ""
    current_key = current_key.strip()
    saved_key = (saved["api_key"] or "").strip()
    if current_key:
        line = "🔑 **{}:** `{}`".format(
            i18n("Gemini API Key"), settings_store.mask_key(current_key))
        if current_key == saved_key:
            src = _KEY_SOURCE_LABELS.get(saved["key_source"], "")
            line += " — ✅ " + i18n("saved") + (f" ({src})" if src else "")
        else:
            line += " — 💾 " + i18n("not saved yet")
    else:
        line = "⚠️ **{}:** {}".format(
            i18n("Gemini API Key"),
            i18n("not set — paste your key once and it will be remembered"))
    return line


def _model_choices_for(backend, saved_model):
    """Model dropdown choices/value per backend, keeping the saved model."""
    if backend == "gemini":
        choices, default = list(GEMINI_MODELS), GEMINI_MODELS[1]
        model_visible, refresh_visible, api_visible = True, False, True
    elif backend == "g4f":
        choices, default = list(G4F_MODELS), G4F_MODELS[5]
        model_visible, refresh_visible, api_visible = True, False, False
    elif backend == "local":
        models = get_local_models()
        choices = models if models else [i18n("No models found")]
        default = choices[0]
        model_visible, refresh_visible, api_visible = True, True, False
    else:
        choices, default = [], saved_model or ""
        model_visible, refresh_visible, api_visible = False, False, False
    val = saved_model or default
    if val and val not in choices:
        choices = choices + [val]
    return choices, val, model_visible, refresh_visible, api_visible


def load_saved_settings():
    """On UI load: prefill AI settings from the saved config (no retyping)."""
    s = settings_store.load_ui_settings()
    backend = s["ai_backend"]
    choices, val, model_visible, refresh_visible, api_visible = _model_choices_for(
        backend, s["ai_model"])
    chunk = s["chunk_size"]
    if backend == "local" and not chunk:
        chunk = 30000
    return (
        gr.update(value=backend),
        gr.update(value=s["api_key"], visible=api_visible),
        gr.update(choices=choices, value=val, visible=model_visible),
        gr.update(visible=refresh_visible),
        gr.update(value=chunk),
        settings_status_text(s["api_key"]),
    )


def _save_and_status(backend, api_key, model, chunk, note=None):
    ok, err = settings_store.save_ui_settings(
        ai_backend=backend, api_key=api_key, ai_model=model, chunk_size=chunk)
    status = settings_status_text(api_key)
    stamp = datetime.datetime.now().strftime("%H:%M:%S")
    if ok:
        tail = "💾 {} {}".format(
            note or i18n("Settings saved automatically"), stamp)
    else:
        tail = "❌ {}: {}".format(i18n("Error saving settings"), err)
    return status + "\n\n" + tail


def on_backend_change(backend, api_key, model, chunk):
    """Backend switched: refresh model choices AND remember the choice."""
    show_api, model_upd, refresh_upd, chunk_upd = update_ai_ui(backend)
    if backend == "manual":
        chunk_upd = gr.update(value=chunk)
    status = _save_and_status(backend, api_key, model, chunk)
    return show_api, model_upd, refresh_upd, chunk_upd, status


def on_settings_changed(backend, api_key, model, chunk):
    """Any AI setting edited: remember it immediately (silent on empty key)."""
    return _save_and_status(backend, api_key, model, chunk)


def save_settings_click(backend, api_key, model, chunk):
    return _save_and_status(backend, api_key, model, chunk,
                            note=i18n("Settings saved"))


def test_api_connection(backend, api_key, model):
    """Ping Gemini with the current key — instant feedback, no surprise mid-run."""
    if backend != "gemini":
        return "ℹ️ " + i18n("Connection test is only available for Gemini.")
    ok, msg = settings_store.test_gemini_connection(
        api_key, model if model in GEMINI_MODELS else "gemini-2.5-flash")
    if ok:
        return "✅ " + i18n("Connection OK — the key works.")
    return "❌ " + i18n("Connection failed:") + " " + str(msg)[:300]


def kill_process():
    global current_process
    if current_process:
        try:
            parent = psutil.Process(current_process.pid)
            for child in parent.children(recursive=True):
                child.kill()
            parent.kill()
            current_process = None
            state = empty_progress_state(tr("Process stopped by user."))
            return (
                tr("Process terminated."),
                gr.update(value=tr("Start Processing"), interactive=True),
                gr.update(interactive=False),
                render_progress_html(state),
                render_tasks_html(state),
                render_error_html([tr("Process stopped by user.")]),
            )
        except Exception as e:
            return (tr("Error terminating process: {}").format(e), gr.update(), gr.update(), gr.update(), gr.update(), gr.update())
    state = empty_progress_state(tr("No process running."))
    return (tr("No process running."), gr.update(), gr.update(interactive=False), render_progress_html(state), render_tasks_html(state), render_error_html([]))



def run_viral_cutter(input_source, project_name, url, video_file, segments, viral, themes, min_duration, max_duration, model, ai_backend, api_key, ai_model_name, chunk_size, workflow, face_model, face_mode, face_detect_interval, no_face_mode, 
                     face_filter_thresh, face_two_thresh, face_conf_thresh, face_dead_zone, focus_active_speaker, active_speaker_mar, active_speaker_score_diff, include_motion, active_speaker_motion_threshold, active_speaker_motion_sensitivity, active_speaker_decay,
                     use_custom_subs, font_name, font_size, font_color, highlight_color, outline_color, outline_thickness, shadow_color, shadow_size, is_bold, is_italic, is_uppercase, vertical_pos, alignment,
                     h_size, w_block, gap, mode, under, strike, border_s, remove_punc, video_quality, use_youtube_subs, translate_target, safety_mode="block", safety_ai=True,
                     platform=None, metadata_gate=None, title_language=None, polish=False, music=None, logo=None,
                     cookies_browser=None):
    # NOTE: parameter order MUST match the `inputs=[...]` order of every
    # .click() that targets this function (start / review-render / batch).
    # v6.8 fix: the tail used to be (platform, polish, music, logo,
    # metadata_gate, cookies, title_language) while the UI sent (platform,
    # metadata_gate, title_language, polish, music, logo, cookies) — so
    # polish was always "warn" (truthy → --polish on) and cookies/title
    # language selections silently landed in the wrong parameters.
    
    global current_process
    progress_state = empty_progress_state(i18n("Starting"))
    error_items = []
    logs = []

    def fail(message, *, keep_start_enabled=False):
        error_items.append(message)
        progress_state["current"] = message
        return (
            "\n".join(logs + [f"ERROR: {message}"]),
            gr.update(value=i18n("Start Processing"), interactive=True),
            gr.update(visible=False, interactive=not keep_start_enabled),
            None,
            render_progress_html(progress_state),
            render_tasks_html(progress_state),
            render_error_html(error_items),
        )

    def set_progress(stage, percent, message):
        progress_state[stage] = {"percent": int(percent), "message": message}
        progress_state["current"] = message
        progress_state["overall"] = int(sum(progress_state[s]["percent"] for s in PROGRESS_ORDER) / len(PROGRESS_ORDER))

    def emit_log(message):
        logs.append(message)
        return "\n".join(logs)

    try:
        set_progress("download", 0, i18n("Preparing"))
        emit_log(i18n("Preparing run..."))
        yield "", gr.update(value=i18n("Running..."), interactive=False), gr.update(visible=True, interactive=True), None, render_progress_html(progress_state), render_tasks_html(progress_state), render_error_html(error_items)

        input_source = input_source or "YouTube URL"

        source_args = []
        if input_source == "Existing Project":
            if not project_name:
                yield fail(i18n("Error: No project selected."))
                return
            full_project_path = os.path.join(VIRALS_DIR, project_name)
            if not os.path.exists(full_project_path):
                yield fail(i18n("Error: Project path not found."))
                return
            source_args = ["--project-path", full_project_path]
        elif input_source == "Upload Video":
            if not video_file:
                yield fail(i18n("Error: No video file uploaded."))
                return
            original_filename = os.path.basename(video_file)
            name_no_ext = os.path.splitext(original_filename)[0]
            safe_name = "".join([c for c in name_no_ext if c.isalnum() or c in " _-"]).strip() or "Untitled_Upload"
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            project_name_upload = f"{safe_name}_{timestamp}"
            project_path = os.path.join(VIRALS_DIR, project_name_upload)
            os.makedirs(project_path, exist_ok=True)
            target_path = os.path.join(project_path, "input.mp4")
            shutil.copy2(video_file, target_path)
            source_args = ["--project-path", project_path, "--skip-youtube-subs"]
            emit_log(f"Copied upload to {target_path}")
        else:
            if not url:
                yield fail(i18n("Error: No URL provided."))
                return
            source_args = ["--url", url]
            if video_quality:
                source_args.extend(["--video-quality", video_quality])
            if not use_youtube_subs:
                source_args.append("--skip-youtube-subs")

        subtitle_config_path = None
        if use_custom_subs:
            subtitle_config = _build_subtitle_config(
                font_name, font_size, font_color, highlight_color, outline_color,
                outline_thickness, shadow_color, shadow_size, is_bold, is_italic,
                is_uppercase, vertical_pos, alignment, h_size, w_block, gap, mode,
                under, strike, border_s, remove_punc,
            )
            subtitle_config_path = os.path.join(WORKING_DIR, "temp_subtitle_config.json")
            with open(subtitle_config_path, "w", encoding="utf-8") as f:
                json.dump(subtitle_config, f, indent=4)

        # v6.9 preflight: fail fast with a clear message instead of letting
        # the run die mid-pipeline on an obvious configuration error.
        if ai_backend == "gemini":
            preflight_key = (api_key or "").strip()
            if not preflight_key:
                # the field may be empty even though a key is saved — the CLI
                # resolves env/secure/file on its own, so only hard-fail when
                # NOTHING is configured anywhere.
                saved = settings_store.load_ui_settings()
                if not saved["api_key"]:
                    yield fail(i18n("Error: Gemini API key is missing. Paste it in the AI settings (saved automatically) or set the GEMINI_API_KEY environment variable."))
                    return
            elif not settings_store.looks_like_gemini_key(preflight_key):
                emit_log(i18n("Warning: the API key does not look like a Gemini key (usually starts with 'AIza'). Continuing anyway."))

        cmd = build_command(
            MAIN_SCRIPT_PATH, source_args,
            segments=segments, viral=viral, themes=themes,
            min_duration=min_duration, max_duration=max_duration, model=model,
            ai_backend=ai_backend, api_key=api_key, ai_model_name=ai_model_name,
            chunk_size=chunk_size, workflow=workflow, face_model=face_model,
            face_mode=face_mode, face_detect_interval=face_detect_interval,
            no_face_mode=no_face_mode, face_filter_thresh=face_filter_thresh,
            face_two_thresh=face_two_thresh, face_conf_thresh=face_conf_thresh,
            face_dead_zone=face_dead_zone, focus_active_speaker=focus_active_speaker,
            active_speaker_mar=active_speaker_mar,
            active_speaker_score_diff=active_speaker_score_diff,
            include_motion=include_motion,
            active_speaker_motion_threshold=active_speaker_motion_threshold,
            active_speaker_motion_sensitivity=active_speaker_motion_sensitivity,
            active_speaker_decay=active_speaker_decay,
            translate_target=translate_target,
            subtitle_config_path=subtitle_config_path,
            safety_mode=safety_mode,
            safety_ai="on" if safety_ai else "off",
            # v6 features (Roadmap 5.2 / Sprint 3 / 2.4)
            platform=platform,
            polish=polish,
            music=music,
            logo=logo,
            metadata_gate=metadata_gate,
            cookies_browser=cookies_browser,
            title_language=title_language,
        )

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
        # mask the API key in the echoed command — never print secrets to
        # the visible log (v6.9 fix: keys leaked into screenshots/logs before)
        def _mask_cmd(cmd_list):
            masked = []
            skip_next = False
            for part in cmd_list:
                if skip_next:
                    masked.append(settings_store.mask_key(str(part)) or "***")
                    skip_next = False
                    continue
                masked.append(str(part))
                if part == "--api-key":
                    skip_next = True
            return " ".join(masked)
        debug_cmd = _mask_cmd([x for x in cmd if x])
        emit_log(f"Command: {debug_cmd}")
        yield "\n".join(logs), gr.update(value=i18n("Running..."), interactive=False), gr.update(visible=True, interactive=True), None, render_progress_html(progress_state), render_tasks_html(progress_state), render_error_html(error_items)

        current_process = subprocess.Popen(
            cmd,
            cwd=WORKING_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            env=env,
        )
        project_folder_path = None
        last_update_time = time.time()
        last_progress_tick = 0.0
        current_stage = None
        current_buffer = []

        while True:
            line = current_process.stdout.readline()
            if not line and current_process.poll() is not None:
                break
            if not line:
                continue

            line = line.rstrip("\n")
            if line.startswith("PROGRESS|"):
                try:
                    _, stage, percent, message = line.split("|", 3)
                    if stage in progress_state:
                        progress_state[stage] = {"percent": int(percent), "message": message}
                        progress_state["current"] = message
                        progress_state["overall"] = int(sum(progress_state[s]["percent"] for s in PROGRESS_ORDER) / len(PROGRESS_ORDER))
                    current_stage = stage
                    last_progress_tick = time.time()
                except Exception as e:
                    error_items.append({"title": "Bad progress line: {}".format(e),
                                         "detail": str(e), "hint": ""})
                continue

            current_buffer.append(line)
            if len(current_buffer) > 200:
                current_buffer = current_buffer[-200:]
            logs.append(line)
            if len(logs) > 1000:
                del logs[: len(logs) - 1000]
            if "Project Folder:" in line:
                parts = line.split("Project Folder:")
                if len(parts) > 1:
                    project_folder_path = parts[1].strip()

            current_time = time.time()
            if current_time - last_update_time > 0.2:
                yield "\n".join(logs), gr.update(visible=True, interactive=False), gr.update(visible=True, interactive=True), None, render_progress_html(progress_state), render_tasks_html(progress_state), render_error_html(error_items)
                last_update_time = current_time

        return_code = current_process.poll()
        if return_code not in (0, None):
            tail = "\n".join(current_buffer[-30:])
            title, detail, hint = summarize_error(
                tail or "Process exited with code {}".format(return_code))
            error_items.append({"title": title, "detail": detail,
                                "hint": hint, "code": return_code})
            yield "\n".join(logs), gr.update(value=i18n("Start Processing"), interactive=True), gr.update(visible=True, interactive=True), None, render_progress_html(progress_state), render_tasks_html(progress_state), render_error_html(error_items)
            return

        yield "\n".join(logs), gr.update(visible=True, interactive=False), gr.update(visible=True, interactive=True), None, render_progress_html(progress_state), render_tasks_html(progress_state), render_error_html(error_items)
    except FileNotFoundError as e:
        yield fail(f"{i18n('Error: Missing file or tool.')} {e}")
        return
    except subprocess.CalledProcessError as e:
        yield fail(f"{i18n('Error: Process failed.')} {e}")
        return
    except Exception as e:
        title, detail, hint = summarize_error(str(e))
        error_items.append({"title": "Error running process: {}".format(title),
                            "detail": detail, "hint": hint})
        yield "\n".join(logs + [f"Error running process: {str(e)}"]), gr.update(visible=True, interactive=False), gr.update(visible=True, interactive=True), None, render_progress_html(progress_state), render_tasks_html(progress_state), render_error_html(error_items)
    finally:
        if current_process:
            if current_process.stdout:
                try:
                    current_process.stdout.close()
                except Exception:
                    pass
            if current_process.poll() is None:
                try:
                    current_process.terminate()
                    current_process.wait(timeout=5)
                except Exception:
                    try:
                        current_process.kill()
                    except Exception:
                        pass
            current_process = None
        time.sleep(0.5)
        if use_custom_subs:
            try:
                subtitle_config_path = os.path.join(WORKING_DIR, "temp_subtitle_config.json")
                if os.path.exists(subtitle_config_path):
                    os.remove(subtitle_config_path)
            except Exception:
                pass

    html_output = ""
    if project_folder_path and os.path.exists(project_folder_path):
        html_output = library.generate_project_gallery(project_folder_path, is_full_path=True)
    else:
        html_output = f"<h3>{i18n('Error: Project folder could not be determined from logs.')}</h3>"
    set_progress("done", 100, i18n("Completed"))
    yield "\n".join(logs), gr.update(value=tr("Start Processing"), interactive=True), gr.update(visible=True, interactive=False), html_output, render_progress_html(progress_state), render_tasks_html(progress_state), render_error_html(error_items)

css = """
#logs_output textarea {
    min-height: 300px !important;
    max-height: 520px !important;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace !important;
    line-height: 1.6 !important;
}

.vc-topbar {
    position: sticky;
    top: 0;
    z-index: 20;
    background: rgba(2, 6, 23, 0.92);
    backdrop-filter: blur(10px);
    padding: 10px 0;
    margin-bottom: 12px;
    gap: 12px;
    align-items: center;
}

.vc-topbar > div,
.vc-topbar > button {
    flex: 0 0 auto !important;
}

.vc-panels > div {
    min-width: 0;
}

body, .gradio-container {
    background-color: #0b0b0b !important;
    color: #ffffff !important;
}

input[type="password"], textarea, select {
    background-color: #1f1f1f !important;
    color: #ffffff !important;
    border: 1px solid #333 !important;
}

footer {visibility: hidden}

.gradio-container {
    max-width: 98% !important;
    width: 98% !important;
    margin: 0 auto !important;
}

/* --- RTL layout for the Arabic UI ---
   Text fields keep per-content direction (URLs stay LTR) via plaintext bidi. */
body, .gradio-container {
    direction: rtl !important;
    font-family: "Cairo", "Tajawal", "Segoe UI", Tahoma, Arial, sans-serif !important;
}

/* Section headings inside the app: subtle separator for clean formatting */
.gradio-container h3 {
    margin-top: 16px !important;
    padding-bottom: 4px;
    border-bottom: 1px solid rgba(148, 163, 184, 0.18);
}

/* Header card: force light text regardless of Gradio theme defaults */
#vc-header, #vc-header p, #vc-header li, #vc-header strong, #vc-header ul {
    color: #e2e8f0 !important;
}
#vc-header h1 {
    color: #f8fafc !important;
}

.gradio-container input,
.gradio-container textarea {
    unicode-bidi: plaintext !important;
}
"""

import header

# --- Gradio version compatibility -------------------------------------------
# Gradio 6 moved `theme`/`css` from the Blocks constructor to launch(); on
# Gradio 4/5 they only exist on Blocks. Detect once and route accordingly.
try:
    _GRADIO_MAJOR = int(str(gr.__version__).split(".", 1)[0])
except Exception:
    _GRADIO_MAJOR = 4

vc_theme = gr.themes.Soft(primary_hue="orange", neutral_hue="slate")
# Dark theme: the app CSS targets a dark surface; tint the Gradio theme so
# every component (forms, tables, panels) matches instead of light-on-dark.
vc_theme.set(
    body_background_fill="#0b0b0b",
    body_text_color="#e5e7eb",
    body_text_color_subdued="#94a3b8",
    background_fill_primary="#0b0b0b",
    background_fill_secondary="#111827",
    block_background_fill="#111827",
    block_border_color="#1f2937",
    block_label_text_color="#9ca3af",
    block_info_text_color="#94a3b8",
    input_background_fill="#1f1f1f",
    input_border_color="#333333",
    input_placeholder_color="#6b7280",
    border_color_primary="#1f2937",
    panel_background_fill="#0f172a",
    panel_border_color="#1f2937",
    table_even_background_fill="#111827",
    table_odd_background_fill="#0b0b0b",
    table_border_color="#1f2937",
    table_text_color="#e5e7eb",
    accordion_text_color="#e5e7eb",
    button_secondary_background_fill="#1f2937",
    button_secondary_border_color="#374151",
    button_secondary_text_color="#e5e7eb",
    checkbox_background_color="#1f1f1f",
    checkbox_border_color="#444444",
    checkbox_label_background_fill="#1f2937",
    checkbox_label_background_fill_selected="#f97316",
    checkbox_label_text_color="#e5e7eb",
    checkbox_label_text_color_selected="#ffffff",
    slider_color="#f97316",
    loader_color="#f97316",
    code_background_fill="#1e1e1e",
)
if _GRADIO_MAJOR >= 6:
    _blocks_kwargs = {"title": "ViralCutter"}
    _launch_theme_kwargs = {"theme": vc_theme, "css": css}
else:
    _blocks_kwargs = {"title": "ViralCutter", "theme": vc_theme, "css": css}
    _launch_theme_kwargs = {}

with gr.Blocks(**_blocks_kwargs) as demo:
    if _GRADIO_MAJOR >= 6:
        # mount_gradio_app has no css param — inject the stylesheet inline so
        # the dark surface applies on every Gradio version.
        gr.HTML("<style>{}</style>".format(css))
    gr.HTML(header.description)
    with gr.Row(elem_classes=["vc-topbar"]):
        start_btn = gr.Button("🚀 بدء المعالجة", variant="primary", size="lg", min_width=220)
        stop_btn = gr.Button("⏹️ إيقاف", variant="stop", visible=True, interactive=False, size="lg", min_width=140)
    with gr.Row(elem_classes=["vc-panels"]):
        with gr.Column(scale=1, min_width=280):
            gr.Markdown("### 📊 التقدم")
            progress_panel = gr.HTML(value=render_progress_html(empty_progress_state()))
        with gr.Column(scale=1, min_width=280):
            gr.Markdown("### 🧩 المهام")
            tasks_panel = gr.HTML(value=render_tasks_html(empty_progress_state()))
        with gr.Column(scale=1, min_width=280):
            gr.Markdown("### ⚠️ الأخطاء")
            errors_panel = gr.HTML(value=render_error_html([]))
    with gr.Tabs():
        with gr.Tab("📥 إنشاء جديد"):
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### 1️⃣ المصدر")
                    input_source = gr.Radio([("رابط يوتيوب", "YouTube URL"), ("مشروع موجود", "Existing Project"), ("رفع فيديو", "Upload Video")], label="مصدر الإدخال", value="YouTube URL")
                    url_input = gr.Textbox(label="رابط يوتيوب", placeholder="https://www.youtube.com/watch?v=...", visible=True)
                    video_upload = gr.File(label=i18n("Drag & drop a video here or click to browse"), file_count="single", file_types=["video"], visible=False, elem_id="video_upload_box")
                    upload_hint = gr.Markdown(i18n("Drop a video here for fastest upload."), visible=False)

                    with gr.Row():
                        video_quality_input = gr.Dropdown(choices=["best", "1080p", "720p", "480p"], label="جودة الفيديو", value="best")
                        translate_input = gr.Dropdown(choices=["None", "pt", "en", "es", "fr", "de", "it", "ru", "ja", "ko", "zh-CN", "ar"], label="ترجمة الترجمة إلى", value="None")
                        use_youtube_subs_input = gr.Checkbox(label="استخدام ترجمات يوتيوب", value=True, info=i18n("Download and use official subtitles if available. (Recommended, it speeds up the process)"))

                    project_selector = gr.Dropdown(choices=[], label="اختر مشروعًا", visible=False)

                    def on_source_change(source):
                        if source == "YouTube URL":
                            return gr.update(visible=True), gr.update(visible=False), gr.update(visible=False), gr.update(value="Full"), gr.update(visible=False)
                        if source == "Upload Video":
                            return gr.update(visible=False), gr.update(visible=False), gr.update(visible=True), gr.update(value="Full"), gr.update(visible=True)
                        projs = library.get_existing_projects(force_refresh=True)
                        return gr.update(visible=False), gr.update(choices=projs, visible=True), gr.update(visible=False), gr.update(value="Subtitles Only"), gr.update(visible=False)

                    gr.Markdown("### ✂️ القص والترجمة")
                    with gr.Row():
                        segments_input = gr.Number(label="عدد المقاطع", value=3, precision=0)
                        viral_input = gr.Checkbox(label="وضع الفيروسية", value=True)
                    themes_input = gr.Textbox(label="المواضيع", placeholder=i18n("funny, sad..."), visible=False)
                    viral_input.change(lambda x: gr.update(visible=not x), viral_input, themes_input)
                    with gr.Row():
                        min_dur_input = gr.Number(label="أقل مدة (ث)", value=15)
                        max_dur_input = gr.Number(label="أقصى مدة (ث)", value=90)
                with gr.Column(scale=1):
                    gr.Markdown("### 🤖 الذكاء الاصطناعي")
                    with gr.Row():
                        ai_backend_input = gr.Dropdown(choices=[(i18n("Gemini"), "gemini"), (i18n("G4F"), "g4f"), (i18n("Local (GGUF)"), "local"), (i18n("Manual"), "manual")], label="محرك الذكاء الاصطناعي", value="gemini", scale=2)
                        api_key_input = gr.Textbox(label="مفتاح Gemini API", type="password", scale=3)
                    settings_status = gr.Markdown(elem_id="ai_settings_status")
                    with gr.Row():
                        save_settings_btn = gr.Button("💾 " + i18n("Save Settings"), variant="secondary", size="sm", scale=1)
                        test_key_btn = gr.Button("🔌 " + i18n("Test Connection"), variant="secondary", size="sm", scale=1)
                        settings_hint = gr.Markdown("💡 " + i18n("The key is saved automatically — no need to re-enter it each time."), scale=3)
                    with gr.Row():
                        ai_model_input = gr.Dropdown(choices=GEMINI_MODELS, label="نموذج الذكاء الاصطناعي", value=GEMINI_MODELS[1], allow_custom_value=True, visible=True, scale=5)
                        refresh_models_btn = gr.Button("🔄", size="sm", visible=False, scale=0, min_width=50)
                        chunk_size_input = gr.Number(label="حجم الجزء", value=70000, precision=0, scale=2)

                    def update_ai_ui(backend):
                        show_api = (backend == "gemini")
                        show_refresh = (backend == "local")
                        if backend == "gemini":
                            new_choices = GEMINI_MODELS
                            new_val = GEMINI_MODELS[1]
                            new_chunk = 70000
                        elif backend == "g4f":
                            new_choices = G4F_MODELS
                            new_val = G4F_MODELS[5]
                            new_chunk = 70000
                        elif backend == "local":
                            models = get_local_models()
                            new_choices = models if models else [i18n("No models found")]
                            new_val = new_choices[0]
                            new_chunk = 30000
                        else:
                            new_choices = ai_model_input.choices or []
                            new_val = ai_model_input.value
                            new_chunk = chunk_size_input.value
                        return gr.update(visible=show_api), gr.update(choices=new_choices, value=new_val, visible=(backend != "manual")), gr.update(visible=show_refresh), gr.update(value=new_chunk)

                    def refresh_local_models():
                        models = get_local_models()
                        val = models[0] if models else i18n("No models found")
                        return gr.update(choices=models, value=val)

                    refresh_models_btn.click(refresh_local_models, outputs=ai_model_input)
                    # v6.9: backend switch now also PERSISTS the settings
                    ai_backend_input.change(on_backend_change, inputs=[ai_backend_input, api_key_input, ai_model_input, chunk_size_input], outputs=[api_key_input, ai_model_input, refresh_models_btn, chunk_size_input, settings_status])
                    # v6.9: typing the key / changing model or chunk auto-saves
                    api_key_input.change(on_settings_changed, inputs=[ai_backend_input, api_key_input, ai_model_input, chunk_size_input], outputs=settings_status)
                    ai_model_input.change(on_settings_changed, inputs=[ai_backend_input, api_key_input, ai_model_input, chunk_size_input], outputs=settings_status)
                    chunk_size_input.change(on_settings_changed, inputs=[ai_backend_input, api_key_input, ai_model_input, chunk_size_input], outputs=settings_status)
                    save_settings_btn.click(save_settings_click, inputs=[ai_backend_input, api_key_input, ai_model_input, chunk_size_input], outputs=settings_status)
                    test_key_btn.click(test_api_connection, inputs=[ai_backend_input, api_key_input, ai_model_input], outputs=settings_status)
                    # v6.9: prefill the saved key/model/backend on startup
                    demo.load(load_saved_settings, outputs=[ai_backend_input, api_key_input, ai_model_input, refresh_models_btn, chunk_size_input, settings_status])
                    model_input = gr.Dropdown(["tiny", "small", "medium", "large", "large-v1", "large-v2", "large-v3", "turbo", "large-v3-turbo", "distil-large-v2", "distil-medium.en", "distil-small.en", "distil-large-v3"], label="نموذج Whisper", value="large-v3-turbo")
                    with gr.Row():
                        workflow_input = gr.Dropdown(choices=[(i18n("Full"), "Full"), (i18n("Cut Only"), "Cut Only"), (i18n("Subtitles Only"), "Subtitles Only")], label="طريقة العمل", value="Full")
                        face_model_input = gr.Dropdown(["insightface", "mediapipe"], label="نموذج الوجه", value="insightface")
                    gr.Markdown("### 🛡️ الأمان")
                    safety_mode_input = gr.Dropdown(
                        choices=[(i18n("Block violating segments (recommended)"), "block"), (i18n("Bleep violating words (keep clip)"), "censor"), (i18n("Flag only (keep segments)"), "flag"), (i18n("Off"), "off")],
                        label=i18n("🛡️ Safety filter (hate speech)"),
                        value="block",
                        info=i18n("Blocks clips containing hate speech / incitement to violence before cutting — protects your channel from YouTube strikes."),
                    )
                    safety_ai_input = gr.Checkbox(
                        label=i18n("Extra AI review (catches contextual violations)"),
                        value=True,
                        info=i18n("Sends surviving clips to the AI for a second policy check (Gemini/G4F only)."),
                    )
                    # --- v6: platform template + professional polish (Roadmap 5.2 / Sprint 3) ---
                    with gr.Accordion(i18n("✨ Pro editing & platforms (v6)"), open=False):
                        gr.Markdown("### " + i18n("🎯 Platform & publishing"))
                        with gr.Row():
                            platform_input = gr.Dropdown(
                                choices=[(i18n("(No platform template)"), ""), (i18n("YouTube Shorts (9:16, ≤60s)"), "yt_shorts"),
                                         (i18n("TikTok (9:16, ≤90s)"), "tiktok"),
                                         (i18n("Instagram Reels (9:16, ≤90s)"), "reels"),
                                         (i18n("YouTube Standard (16:9, ≤10min)"), "yt_standard")],
                                label=i18n("📱 Platform template"),
                                value="",
                            )
                            metadata_gate_input = gr.Dropdown(
                                choices=[(i18n("Warn (flag risky metadata)"), "warn"),
                                         (i18n("Block (stop run on risky metadata)"), "block"),
                                         (i18n("Off"), "off")],
                                label=i18n("Metadata gate (title/caption/hashtags)"),
                                value="warn",
                            )
                        title_language_input = gr.Dropdown(
                            choices=[(i18n("Auto (same as video language)"), "auto"),
                                     (i18n("Arabic"), "ar"),
                                     (i18n("English"), "en"),
                                     (i18n("Français"), "fr"),
                                     (i18n("Español"), "es"),
                                     (i18n("Português"), "pt"),
                                     (i18n("Deutsch"), "de"),
                                     (i18n("Türkçe"), "tr")],
                            label=i18n("🌐 Titles & captions language"),
                            value="auto",
                            info=i18n("'Auto' matches the video language; choose Arabic to force all titles/captions in Arabic."),
                        )
                        gr.Markdown("### " + i18n("🎬 Editing quality"))
                        polish_input = gr.Checkbox(
                            label=i18n("✨ Professional polish (jump cuts + punch zoom + music + watermark)"),
                            value=False,
                            info=i18n("Removes silence/fillers, adds punch-in zoom, background music with auto-duck and your logo."),
                        )
                        with gr.Row():
                            music_input = gr.Textbox(label=i18n("Background music file"), placeholder="music/bed.m4a", value="")
                            logo_input = gr.Textbox(label=i18n("Channel logo (PNG)"), placeholder="logo.png", value="")
                        gr.Markdown("### " + i18n("🔒 YouTube login"))
                        cookies_input = gr.Dropdown(
                            choices=[(i18n("(No cookies — public videos only)"), ""),
                                     (i18n("Chrome cookies (private/age-restricted)"), "chrome"),
                                     (i18n("Edge cookies"), "edge"),
                                     (i18n("Firefox cookies"), "firefox")],
                            label=i18n("🔒 YouTube login (cookies)"),
                            value="",
                            info=i18n("Useful for private or age-restricted videos you have access to."),
                        )
                    with gr.Row():
                        safety_update_btn = gr.Button(i18n("🔄 Update safety word list"), size="sm")
                        safety_update_status = gr.Markdown(i18n("Loading…"), elem_id="safety_update_status")

                    def safety_list_status_text():
                        try:
                            from scripts.safety_updater import load_cached_pack
                            pack = load_cached_pack()
                            if pack:
                                return i18n("Safety word list: v{} ({} terms)").format(
                                    pack.get("version", "?"), len(pack.get("terms", [])))
                            return i18n("Safety word list: built-in (no updates downloaded yet)")
                        except Exception:
                            return i18n("Safety word list: built-in")

                    def run_safety_update():
                        try:
                            from scripts.safety_updater import check_and_update
                            result = check_and_update(force=True)
                            status = result.get("status")
                            if status == "updated":
                                msg = i18n("Safety list updated: {}").format(result.get("message", ""))
                            elif status == "up-to-date":
                                msg = i18n("Safety list is current (v{})").format(result.get("version", "?"))
                            elif status == "offline":
                                msg = i18n("Safety list update failed (offline). Using local list.")
                            else:
                                msg = i18n("Safety list update failed. Using local list.")
                            return msg + "\n\n" + safety_list_status_text()
                        except Exception as e:
                            return i18n("Safety list update failed: {}").format(e)

                    demo.load(lambda: safety_list_status_text(), outputs=safety_update_status)
                    safety_update_btn.click(run_safety_update, outputs=safety_update_status)
                    with gr.Row():
                        face_mode_input = gr.Dropdown(choices=[(i18n("Auto"), "auto"), ("1", "1"), ("2", "2")], label="وضع الوجه", value="auto")
                        face_detect_interval_input = gr.Textbox(label="فاصل كشف الوجه", value="0.17,1.0")
                        no_face_mode_input = gr.Dropdown(choices=[(i18n("Padding (9:16)"), "padding"), (i18n("Zoom (Center)"), "zoom")], label=i18n("No Face Fallback"), value="zoom")
                    input_source.change(on_source_change, inputs=input_source, outputs=[url_input, project_selector, video_upload, workflow_input, upload_hint])

            
            with gr.Accordion(i18n("Advanced Face Settings"), open=False):
                face_preset_input = gr.Dropdown(choices=[(i18n(k), k) for k in FACE_PRESETS.keys()], label=i18n("Configuration Presets"), value="Default (Balanced)", interactive=True)
                with gr.Row():
                    face_filter_thresh_input = gr.Slider(label=i18n("Ignore Small Faces (0.0 - 1.0)"), minimum=0.0, maximum=1.0, value=0.35, step=0.05, info=i18n("Relative size to ignore background."))
                    face_two_thresh_input = gr.Slider(label=i18n("Threshold for 2 Faces (0.0 - 1.0)"), minimum=0.0, maximum=1.0, value=0.60, step=0.05, info=i18n("Size of 2nd face to activate split mode."))
                    face_conf_thresh_input = gr.Slider(label=i18n("Minimum Confidence (0.0 - 1.0)"), minimum=0.0, maximum=1.0, value=0.40, step=0.05, info=i18n("Ignore detections with low confidence."))
                    face_dead_zone_input = gr.Slider(label=i18n("Dead Zone (Stabilization)"), minimum=0, maximum=200, value=150, step=5, info=i18n("Movement pixels to ignore."))
                face_preset_input.change(apply_face_preset, inputs=face_preset_input, outputs=[face_filter_thresh_input, face_two_thresh_input, face_conf_thresh_input, face_dead_zone_input])
                with gr.Accordion(i18n("Experimental: Active Speaker & Motion"), open=False):
                    experimental_preset_input = gr.Dropdown(choices=[(i18n(k), k) for k in EXPERIMENTAL_PRESETS.keys()], label=i18n("Configuration Presets"), value="Default (Off)", interactive=True)
                    focus_active_speaker_input = gr.Checkbox(label=i18n("Experimental: Focus on Speaker"), value=False, info=i18n("Tries to focus only on the speaking person instead of split screen."))
                    with gr.Row():
                        active_speaker_mar_input = gr.Slider(label=i18n("MAR Threshold (Mouth Open)"), minimum=0.01, maximum=0.20, value=0.03, step=0.005, info=i18n("Mouth open sensitivity."))
                        active_speaker_score_diff_input = gr.Slider(label=i18n("Score Difference"), minimum=0.5, maximum=10.0, value=1.5, step=0.5, info=i18n("Minimum difference to focus on 1 face."))
                    with gr.Row():
                        include_motion_input = gr.Checkbox(label=i18n("Consider Motion"), value=False, info=i18n("Increases score with motion (gestures)."))
                    with gr.Row():
                        active_speaker_motion_threshold_input = gr.Slider(label=i18n("Motion Dead Zone"), minimum=0.0, maximum=20.0, value=3.0, step=0.5, info=i18n("Pixels ignored."))
                        active_speaker_motion_sensitivity_input = gr.Slider(label=i18n("Motion Sensitivity"), minimum=0.01, maximum=0.5, value=0.05, step=0.01, info=i18n("Points per pixel."))
                        active_speaker_decay_input = gr.Slider(label=i18n("Switch Speed"), minimum=0.5, maximum=5.0, value=2.0, step=0.5, info=i18n("Speed to lose focus."))
                    experimental_preset_input.change(apply_experimental_preset, inputs=experimental_preset_input, outputs=[focus_active_speaker_input, active_speaker_mar_input, active_speaker_score_diff_input, include_motion_input, active_speaker_motion_threshold_input, active_speaker_motion_sensitivity_input, active_speaker_decay_input])
            with gr.Accordion("إعدادات الترجمة (تجريبي)", open=False):
                preset_input = gr.Dropdown(choices=[(i18n("Manual"), "Manual")] + [(i18n(k), k) for k in subs.SUBTITLE_PRESETS.keys()], label="إعدادات سريعة", value="Hormozi (Classic)")
                use_custom_subs = gr.Checkbox(label="تفعيل تخصيص الترجمة (يشمل الإعداد المسبق)", value=True)
                preview_html = gr.HTML(value=f"<div style='text-align:center; padding:10px; color:#666;'>{i18n('Select options or preset to preview')}</div>")
                with gr.Row():
                    preview_vid_btn = gr.Button(i18n("🎬 Render Animated Preview (Slow)"), size="sm")
                preview_vid = gr.Video(label="معاينة متحركة", height=300, autoplay=True, interactive=False)
                with gr.Accordion("إعدادات متقدمة", open=False):
                    gr.Markdown("### " + tr("Appearance"))
                    with gr.Row():
                        font_name_input = gr.Textbox(label="اسم الخط", value="Montserrat-Regular")
                        font_size_input = gr.Slider(label="حجم الخط (الأساسي)", minimum=8, maximum=80, value=12)
                        highlight_size_input = gr.Slider(label="حجم التمييز", minimum=8, maximum=80, value=14)
                    with gr.Row():
                        font_color_input = gr.ColorPicker(label="اللون الأساسي", value="#FFFFFF")
                        highlight_color_input = gr.ColorPicker(label="لون التمييز", value="#00FF00")
                        outline_color_input = gr.ColorPicker(label="لون الإطار", value="#000000")
                        shadow_color_input = gr.ColorPicker(label="لون الظل", value="#000000")
                    gr.Markdown("### " + tr("Styling & Effects"))
                    with gr.Row():
                        outline_thickness_input = gr.Slider(label="سماكة الإطار", minimum=0, maximum=10, value=1.5)
                        shadow_size_input = gr.Slider(label="حجم الظل", minimum=0, maximum=10, value=2)
                        border_style_input = gr.Dropdown(choices=[(i18n("Outline"), 1), (i18n("Opaque Box"), 3)], label="نمط الإطار", value=1)
                    with gr.Row():
                        bold_input = gr.Checkbox(label="عريض")
                        italic_input = gr.Checkbox(label="مائل")
                        uppercase_input = gr.Checkbox(label="أحرف كبيرة")
                        remove_punc_input = gr.Checkbox(label=i18n("Remove Punctuation"), value=True)
                        underline_input = gr.Checkbox(label="تحته خط")
                        strikeout_input = gr.Checkbox(label="مشطوب")
                    gr.Markdown("### " + tr("Positioning & Layout"))
                    with gr.Row():
                        vertical_pos_input = gr.Slider(label=i18n("V-Pos (Margin V)"), minimum=0, maximum=500, value=210)
                        alignment_input = gr.Dropdown(choices=[(i18n("Left"), 1), (i18n("Center"), 2), (i18n("Right"), 3)], label="المحاذاة", value=2)
                        gap_limit_input = gr.Slider(label="حد الفجوة", minimum=0.0, maximum=5.0, value=0.5, step=0.1)
                        mode_input = gr.Dropdown(choices=[(i18n("Highlight"), "highlight"), (i18n("Word by Word"), "word_by_word"), (i18n("No Highlight"), "no_highlight")], label="الوضع", value="highlight")
                        words_per_block_input = gr.Slider(label="كلمات بكل كتلة", minimum=1, maximum=20, value=3, step=1)

                manual_inputs = [
                    font_name_input, font_size_input, font_color_input, highlight_color_input,
                    outline_color_input, outline_thickness_input, shadow_color_input, shadow_size_input,
                    bold_input, italic_input, uppercase_input,
                    highlight_size_input, words_per_block_input, gap_limit_input, mode_input,
                    underline_input, strikeout_input, border_style_input,
                    vertical_pos_input, alignment_input,
                    remove_punc_input
                ]
                preset_input.change(subs.apply_preset, inputs=[preset_input], outputs=manual_inputs)
                for inp in manual_inputs:
                    inp.change(subs.generate_preview_html, inputs=manual_inputs, outputs=preview_html)
                preview_vid_btn.click(subs.render_preview_video, inputs=manual_inputs, outputs=preview_vid)
                demo.load(subs.generate_preview_html, inputs=manual_inputs, outputs=preview_html)
                demo.load(subs.apply_preset, inputs=[preset_input], outputs=manual_inputs)

                with gr.Accordion(i18n("Saved Settings Templates"), open=False):
                    with gr.Row():
                        template_name_input = gr.Textbox(label="اسم القالب", placeholder=i18n("e.g. clean-shorts"))
                        save_template_btn = gr.Button(tr("Save Template"), variant="primary")
                    with gr.Row():
                        template_dropdown = gr.Dropdown(choices=template_choices(), label="تحميل القالب", value=None)
                        load_template_btn = gr.Button(tr("Apply Template"), variant="secondary")
                    template_status = gr.Textbox(label="حالة القالب", interactive=False)

                def save_settings_template(name, use_custom, font_name, font_size, font_color, highlight_color, outline_color, outline_thickness, shadow_color, shadow_size, is_bold, is_italic, is_uppercase, vertical_pos, alignment, h_size, w_block, gap, mode, under, strike, border_s, remove_punc, face_mode, face_model, no_face_mode, face_detect_interval):
                    """Save current subtitle + face settings as a named template."""
                    name = (name or "").strip()
                    if not name:
                        return i18n("Template name is required."), gr.update(choices=template_choices())
                    payload = {
                        "subtitle": {
                            "use_custom": bool(use_custom),
                            "font_name": font_name,
                            "font_size": int(font_size),
                            "font_color": font_color,
                            "highlight_color": highlight_color,
                            "outline_color": outline_color,
                            "outline_thickness": outline_thickness,
                            "shadow_color": shadow_color,
                            "shadow_size": shadow_size,
                            "is_bold": bool(is_bold),
                            "is_italic": bool(is_italic),
                            "is_uppercase": bool(is_uppercase),
                            "vertical_pos": int(vertical_pos),
                            "alignment": alignment,
                            "highlight_size": int(h_size),
                            "words_per_block": int(w_block),
                            "gap": gap,
                            "mode": mode,
                            "under": bool(under),
                            "strike": bool(strike),
                            "border_s": border_s,
                            "remove_punc": bool(remove_punc),
                        },
                        "face": {
                            "face_mode": face_mode,
                            "face_model": face_model,
                            "no_face_mode": no_face_mode,
                            "face_detect_interval": face_detect_interval,
                        },
                    }
                    err = save_template(name, payload)
                    if err:
                        return i18n("Error saving template: {}").format(err), gr.update(choices=template_choices())
                    return i18n("Template saved: {}").format(name), gr.update(choices=template_choices(), value=name)

                def load_settings_template(name):
                    """Apply a saved template to subtitle + face settings."""
                    templates = load_templates()
                    payload = templates.get(name)
                    if not payload:
                        return [gr.update() for _ in range(26)] + [i18n("Template not found.")]
                    sub = payload.get("subtitle", payload)  # tolerate legacy flat format
                    face = payload.get("face", {})
                    return [
                        gr.update(value=sub.get("use_custom", True)),
                        gr.update(value=sub.get("font_name", "Montserrat-Regular")),
                        gr.update(value=sub.get("font_size", 12)),
                        gr.update(value=sub.get("font_color", "#FFFFFF")),
                        gr.update(value=sub.get("highlight_color", "#00FF00")),
                        gr.update(value=sub.get("outline_color", "#000000")),
                        gr.update(value=sub.get("outline_thickness", 1.5)),
                        gr.update(value=sub.get("shadow_color", "#000000")),
                        gr.update(value=sub.get("shadow_size", 2)),
                        gr.update(value=sub.get("is_bold", False)),
                        gr.update(value=sub.get("is_italic", False)),
                        gr.update(value=sub.get("is_uppercase", False)),
                        gr.update(value=sub.get("vertical_pos", 210)),
                        gr.update(value=sub.get("alignment", 2)),
                        gr.update(value=sub.get("highlight_size", 14)),
                        gr.update(value=sub.get("words_per_block", 3)),
                        gr.update(value=sub.get("gap", 0.5)),
                        gr.update(value=sub.get("mode", "highlight")),
                        gr.update(value=sub.get("under", False)),
                        gr.update(value=sub.get("strike", False)),
                        gr.update(value=sub.get("border_s", 1)),
                        gr.update(value=sub.get("remove_punc", True)),
                        gr.update(value=face.get("face_mode", "auto")),
                        gr.update(value=face.get("face_model", "insightface")),
                        gr.update(value=face.get("no_face_mode", "zoom")),
                        gr.update(value=face.get("face_detect_interval", "0.17,1.0")),
                        i18n("Template loaded: {}").format(name),
                    ]

                save_template_btn.click(save_settings_template, inputs=[template_name_input, use_custom_subs] + manual_inputs + [face_mode_input, face_model_input, no_face_mode_input, face_detect_interval_input], outputs=[template_status, template_dropdown])
                load_template_btn.click(load_settings_template, inputs=template_dropdown, outputs=[use_custom_subs] + manual_inputs + [face_mode_input, face_model_input, no_face_mode_input, face_detect_interval_input, template_status])

                results_html = gr.HTML(label=tr("Results"))

        with gr.Tab("👀 " + i18n("Review Segments")):
            gr.Markdown(f"### {i18n('Review Segments')}")
            gr.Markdown(i18n("Review the AI-suggested segments, uncheck what you don't want, then render only the selected ones."))
            with gr.Row():
                review_project_dropdown = gr.Dropdown(choices=library.get_existing_projects(), label=tr("Select Project"), value=None)
                review_refresh_btn = gr.Button(tr("Refresh"), size="sm")
                review_load_btn = gr.Button(i18n("Load Segments"), variant="primary")

            review_df = gr.Dataframe(
                headers=segments_review.HEADERS,
                datatype=["bool", "str", "number", "str", "str", "str", "str", "str", "str"],
                interactive=True,
                label=i18n("Segments"),
            )

            with gr.Row():
                review_apply_btn = gr.Button(i18n("Apply Selection"))
                review_restore_btn = gr.Button(i18n("Restore All"))
                review_render_btn = gr.Button(i18n("Render Selected Segments"), variant="primary")
            review_status = gr.Markdown()
            with gr.Row():
                review_export_btn = gr.Button(i18n("Export Publish Metadata"))
            review_export_out = gr.Textbox(label=i18n("Publish Metadata"), lines=8, interactive=False)

            def load_review_segments(project_name):
                if not project_name:
                    return None, i18n("Error: No project selected.")
                project_path = os.path.join(VIRALS_DIR, project_name)
                segments = segments_review.load_segments(project_path)
                if not segments:
                    return None, i18n("No viral segments found in this project.")
                return segments_review.rows_from_segments(segments, segments_review.load_safety_map(project_path)), f"**{len(segments)}** ✔"

            def apply_review_selection(project_name, df):
                if not project_name:
                    return i18n("Error: No project selected.")
                project_path = os.path.join(VIRALS_DIR, project_name)
                kept, total, cuts_cleared = segments_review.apply_selection(project_path, df)
                msg = i18n("Applied: {} of {} segments selected.").format(kept, total)
                if cuts_cleared:
                    msg += " " + i18n("Stale cuts cleared — they will be re-cut on render.")
                return msg

            def restore_review_segments(project_name):
                if not project_name:
                    return None, i18n("Error: No project selected.")
                project_path = os.path.join(VIRALS_DIR, project_name)
                if not segments_review.restore_all(project_path):
                    return None, i18n("No backup found for this project.")
                segments = segments_review.load_segments(project_path)
                return segments_review.rows_from_segments(segments, segments_review.load_safety_map(project_path)), i18n("Selection restored from backup.")

            def run_review_render(project_name, df, *rest):
                if project_name and df is not None:
                    project_path = os.path.join(VIRALS_DIR, project_name)
                    try:
                        segments_review.apply_selection(project_path, df)
                    except Exception:
                        pass
                yield from run_viral_cutter("Existing Project", project_name, *rest)

            def export_review_metadata(project_name):
                if not project_name:
                    return i18n("Error: No project selected.")
                project_path = os.path.join(VIRALS_DIR, project_name)
                path, text = segments_review.export_publish_metadata(project_path)
                if not path:
                    return i18n("No viral segments found in this project.")
                return text

            review_refresh_btn.click(library.refresh_projects, outputs=review_project_dropdown)
            review_load_btn.click(load_review_segments, inputs=review_project_dropdown, outputs=[review_df, review_status])
            review_apply_btn.click(apply_review_selection, inputs=[review_project_dropdown, review_df], outputs=review_status)
            review_restore_btn.click(restore_review_segments, inputs=review_project_dropdown, outputs=[review_df, review_status])
            review_export_btn.click(export_review_metadata, inputs=review_project_dropdown, outputs=review_export_out)
        with gr.Tab("📋 " + i18n("Batch Queue")):
            gr.Markdown(f"### {i18n('Batch Queue')}")
            gr.Markdown(i18n("One YouTube URL per line. The queue processes them one by one with the current settings."))
            batch_urls_input = gr.Textbox(
                label=i18n("YouTube URLs"), lines=6,
                placeholder="https://youtube.com/watch?v=...\nhttps://youtube.com/watch?v=...",
            )
            batch_df = gr.Dataframe(
                headers=batch_queue.HEADERS,
                datatype=["number", "str", "str"],
                interactive=False,
                label=i18n("Queue Status"),
            )
            batch_run_btn = gr.Button(i18n("Run Queue"), variant="primary")
            batch_summary = gr.Markdown()

            def run_batch(urls_text, *rest):
                urls = batch_queue.parse_queue_text(urls_text)
                if not urls:
                    yield ([], i18n("Queue is empty."), "", gr.update(), gr.update(),
                           None, gr.update(), gr.update(), gr.update())
                    return

                items = batch_queue.make_items(urls)
                progress_state = empty_progress_state(i18n("Starting"))
                yield (batch_queue.rows_from_items(items), "",
                       "", gr.update(value=i18n("Running..."), interactive=False),
                       gr.update(visible=True, interactive=True), None,
                       render_progress_html(progress_state),
                       render_tasks_html(progress_state),
                       render_error_html([]))

                for i, item in enumerate(items):
                    batch_queue.mark(items, i, "running")
                    rows = batch_queue.rows_from_items(items)
                    final_logs = ""
                    for update in run_viral_cutter("YouTube URL", None, item["url"], *rest):
                        final_logs = update[0]
                        yield (rows, "", *update)
                    batch_queue.mark(items, i, "done" if batch_queue.looks_completed(final_logs) else "failed")

                ok, failed = batch_queue.summary_counts(items)
                yield (batch_queue.rows_from_items(items),
                       i18n("Finished: {} succeeded, {} failed.").format(ok, failed),
                       "", gr.update(value=i18n("Start Processing"), interactive=True),
                       gr.update(visible=True, interactive=False), None,
                       gr.update(), gr.update(), gr.update())

        with gr.Tab("✍️ " + i18n("Subtitle Editor")):
            gr.Markdown("### تحرير الترجمات (الوضع الذكي)")
            with gr.Row():
                editor_project_dropdown = gr.Dropdown(choices=library.get_existing_projects(), label="اختر مشروعًا", value=None, scale=4)
                editor_refresh_btn = gr.Button(tr("Refresh"), size="sm", scale=1)
            editor_file_dropdown = gr.Dropdown(choices=[], label="ملف الترجمة (من مجلد subs)", value=None)
            with gr.Group():
                editor_status = gr.Textbox(label="الحالة", interactive=False)
            with gr.Row():
                editor_render_single_btn = gr.Button(i18n("🎬 Render Selected (single clip)"), size="sm")
                editor_render_all_btn = gr.Button(i18n("🎬 Render All (background)"), size="sm")
                editor_export_all_btn = gr.Button(i18n("📤 Export All Segments"), size="sm")
            editor_refresh_btn.click(library.refresh_projects, outputs=editor_project_dropdown)


            def update_file_list(proj_name):
                if not proj_name:
                    return gr.update(choices=[], value=None)
                proj_path = os.path.join(VIRALS_DIR, proj_name)
                files = editor.list_editable_files(proj_path)
                return gr.update(choices=files, value=files[0] if files else None)

            # v6.8 fix: the file list used to be written into the status Textbox
            # (a Dropdown update into a Textbox) and current_json_path was never
            # set — "Render Selected" could never work. Now a real dropdown.
            editor_project_dropdown.change(update_file_list, inputs=editor_project_dropdown, outputs=editor_file_dropdown)

            def render_single(proj_name, json_file, use_custom, font_name, font_size, font_color, highlight_color, 
                              outline_color, outline_thickness, shadow_color, shadow_size, 
                              is_bold, is_italic, is_uppercase, 
                              h_size, w_block, gap, mode, under, strike, border_s, 
                              vertical_pos, alignment, remove_punc):
                if not proj_name:
                    return i18n("No project selected.")
                if not json_file:
                    return i18n("No file loaded.")
                json_path = os.path.join(VIRALS_DIR, proj_name, "subs", json_file)
                subtitle_config_path = os.path.join(WORKING_DIR, "temp_subtitle_config.json")
                if use_custom:
                    subtitle_config = _build_subtitle_config(font_name, font_size, font_color, highlight_color, outline_color, outline_thickness, shadow_color, shadow_size, is_bold, is_italic, is_uppercase, vertical_pos, alignment, h_size, w_block, gap, mode, under, strike, border_s, remove_punc)
                    with open(subtitle_config_path, "w", encoding="utf-8") as f:
                        json.dump(subtitle_config, f, indent=4)
                else:
                    try:
                        if os.path.exists(subtitle_config_path):
                            os.remove(subtitle_config_path)
                    except Exception:
                        pass
                return editor.render_specific_video(json_path)

            editor_render_single_btn.click(render_single, inputs=[editor_project_dropdown, editor_file_dropdown, use_custom_subs] + manual_inputs, outputs=editor_status)

            def render_all(proj_name, use_custom, font_name, font_size, font_color, highlight_color, 
                           outline_color, outline_thickness, shadow_color, shadow_size, 
                           is_bold, is_italic, is_uppercase, 
                           h_size, w_block, gap, mode, under, strike, border_s, 
                           vertical_pos, alignment, remove_punc):
                if not proj_name:
                    return i18n("No project selected.")
                if use_custom:
                    subtitle_config = _build_subtitle_config(font_name, font_size, font_color, highlight_color, outline_color, outline_thickness, shadow_color, shadow_size, is_bold, is_italic, is_uppercase, vertical_pos, alignment, h_size, w_block, gap, mode, under, strike, border_s, remove_punc)
                    subtitle_config_path = os.path.join(WORKING_DIR, "temp_subtitle_config.json")
                    with open(subtitle_config_path, "w", encoding="utf-8") as f:
                        json.dump(subtitle_config, f, indent=4)
                proj_path = os.path.join(VIRALS_DIR, proj_name)
                cmd = [sys.executable, MAIN_SCRIPT_PATH, "--project-path", proj_path, "--workflow", "3", "--skip-prompts"]
                if use_custom and os.path.exists(os.path.join(WORKING_DIR, "temp_subtitle_config.json")):
                    cmd.extend(["--subtitle-config", os.path.join(WORKING_DIR, "temp_subtitle_config.json")])
                try:
                    subprocess.Popen(cmd, cwd=WORKING_DIR)
                    return i18n("Render All started in background... Check terminal/logs.")
                except Exception as e:
                    return i18n("Error starting render: {}").format(e)

            editor_render_all_btn.click(render_all, inputs=[editor_project_dropdown, use_custom_subs] + manual_inputs, outputs=editor_status)

            def export_all(project_name):
                if not project_name:
                    return i18n("No project selected.")
                proj_path = os.path.join(VIRALS_DIR, project_name)
                return editor.export_all_segments(proj_path)

            editor_export_all_btn.click(export_all, inputs=[editor_project_dropdown], outputs=editor_status)

        with gr.Tab("🗂️ " + i18n("Library")):
            gr.Markdown(f"### {i18n('Existing Projects')}")
            with gr.Row():
                lib_query_input = gr.Textbox(label=i18n("Search by name"), placeholder=i18n("Type part of a project name"))
                lib_date_from_input = gr.Textbox(label=i18n("From date"), placeholder="YYYY-MM-DD")
                lib_date_to_input = gr.Textbox(label=i18n("To date"), placeholder="YYYY-MM-DD")
                lib_filter_btn = gr.Button(i18n("Filter"))
            with gr.Row():
                project_dropdown = gr.Dropdown(choices=library.get_existing_projects(force_refresh=True), label="اختر مشروعًا", value=None)
                refresh_btn = gr.Button(i18n("Refresh List"))
            project_gallery_html = gr.HTML()
            refresh_btn.click(library.refresh_projects, outputs=project_dropdown)
            lib_filter_btn.click(library.filter_projects, inputs=[lib_query_input, lib_date_from_input, lib_date_to_input], outputs=project_dropdown)
            def on_select_project(proj_name): return library.generate_project_gallery(proj_name)
            project_dropdown.change(on_select_project, project_dropdown, project_gallery_html)
    


    gr.Markdown("---")
    with gr.Row():
        logs_output = gr.Textbox(label="📜 السجل — تظهر تحديثات التقدم هنا أثناء التشغيل", lines=12, autoscroll=True, elem_id="logs_output", scale=9)
        with gr.Column(scale=1, min_width=110):
            gr.Markdown("&nbsp;")
            clear_log_btn = gr.Button("🗑️ مسح السجل", size="sm")
    logs_output.change(fn=None, inputs=[], outputs=[], js="function() { var ta = document.querySelector('#logs_output textarea'); if (ta) { if (!ta._scrollerSetup) { ta._isSticky = true; ta.addEventListener('scroll', function() { var diff = ta.scrollHeight - ta.scrollTop - ta.clientHeight; ta._isSticky = diff <= 50; }); ta._scrollerSetup = true; } if (ta._isSticky === undefined || ta._isSticky === true) { ta.scrollTop = ta.scrollHeight; } } }")
    clear_log_btn.click(lambda: "", outputs=logs_output)

    # kill_process returns 6 values (logs, start, stop, progress, tasks, errors)
    stop_btn.click(kill_process, outputs=[logs_output, start_btn, stop_btn, progress_panel, tasks_panel, errors_panel])


    start_btn.click(run_viral_cutter, inputs=[
    input_source, project_selector, url_input, video_upload, segments_input, viral_input, themes_input, min_dur_input, max_dur_input,
    model_input, ai_backend_input, api_key_input, ai_model_input, chunk_size_input,
    workflow_input, face_model_input, face_mode_input, face_detect_interval_input, no_face_mode_input,
    face_filter_thresh_input, face_two_thresh_input, face_conf_thresh_input, face_dead_zone_input, focus_active_speaker_input,
    active_speaker_mar_input, active_speaker_score_diff_input, include_motion_input, active_speaker_motion_threshold_input, active_speaker_motion_sensitivity_input, active_speaker_decay_input,
    use_custom_subs,
    font_name_input, font_size_input, font_color_input, highlight_color_input,
    outline_color_input, outline_thickness_input, shadow_color_input, shadow_size_input,
    bold_input, italic_input, uppercase_input, vertical_pos_input, alignment_input,
    highlight_size_input, words_per_block_input, gap_limit_input, mode_input,
    underline_input, strikeout_input, border_style_input, remove_punc_input,
    video_quality_input, use_youtube_subs_input, translate_input, safety_mode_input, safety_ai_input,
    platform_input, metadata_gate_input, title_language_input, polish_input, music_input, logo_input, cookies_input
    ], outputs=[logs_output, start_btn, stop_btn, results_html, progress_panel, tasks_panel, errors_panel])

    review_render_btn.click(run_review_render, inputs=[
    review_project_dropdown, review_df, url_input, video_upload, segments_input, viral_input, themes_input, min_dur_input, max_dur_input,
    model_input, ai_backend_input, api_key_input, ai_model_input, chunk_size_input,
    workflow_input, face_model_input, face_mode_input, face_detect_interval_input, no_face_mode_input,
    face_filter_thresh_input, face_two_thresh_input, face_conf_thresh_input, face_dead_zone_input, focus_active_speaker_input,
    active_speaker_mar_input, active_speaker_score_diff_input, include_motion_input, active_speaker_motion_threshold_input, active_speaker_motion_sensitivity_input, active_speaker_decay_input,
    use_custom_subs,
    font_name_input, font_size_input, font_color_input, highlight_color_input,
    outline_color_input, outline_thickness_input, shadow_color_input, shadow_size_input,
    bold_input, italic_input, uppercase_input, vertical_pos_input, alignment_input,
    highlight_size_input, words_per_block_input, gap_limit_input, mode_input,
    underline_input, strikeout_input, border_style_input, remove_punc_input,
    video_quality_input, use_youtube_subs_input, translate_input, safety_mode_input, safety_ai_input,
    platform_input, metadata_gate_input, title_language_input, polish_input, music_input, logo_input, cookies_input
    ], outputs=[logs_output, start_btn, stop_btn, results_html, progress_panel, tasks_panel, errors_panel])

    batch_run_btn.click(run_batch, inputs=[
    batch_urls_input, video_upload, segments_input, viral_input, themes_input, min_dur_input, max_dur_input,
    model_input, ai_backend_input, api_key_input, ai_model_input, chunk_size_input,
    workflow_input, face_model_input, face_mode_input, face_detect_interval_input, no_face_mode_input,
    face_filter_thresh_input, face_two_thresh_input, face_conf_thresh_input, face_dead_zone_input, focus_active_speaker_input,
    active_speaker_mar_input, active_speaker_score_diff_input, include_motion_input, active_speaker_motion_threshold_input, active_speaker_motion_sensitivity_input, active_speaker_decay_input,
    use_custom_subs,
    font_name_input, font_size_input, font_color_input, highlight_color_input,
    outline_color_input, outline_thickness_input, shadow_color_input, shadow_size_input,
    bold_input, italic_input, uppercase_input, vertical_pos_input, alignment_input,
    highlight_size_input, words_per_block_input, gap_limit_input, mode_input,
    underline_input, strikeout_input, border_style_input, remove_punc_input,
    video_quality_input, use_youtube_subs_input, translate_input, safety_mode_input, safety_ai_input,
    platform_input, metadata_gate_input, title_language_input, polish_input, music_input, logo_input, cookies_input
    ], outputs=[batch_df, batch_summary, logs_output, start_btn, stop_btn, results_html, progress_panel, tasks_panel, errors_panel])

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--colab", action="store_true", help="Run in Google Colab mode")
    args = parser.parse_args()


    if args.colab:
        print("Running in Colab mode. Generating public link with Static Mounts...")
        library.set_url_mode("fastapi")
        allowed_dirs = [VIRALS_DIR, WORKING_DIR, os.getcwd(), "."]
        try:
            gr.set_static_paths(paths=allowed_dirs)
        except AttributeError:
            pass
        app, local_url, share_url = demo.queue().launch(
            share=True,
            allowed_paths=allowed_dirs,
            prevent_thread_lock=True,
            **_launch_theme_kwargs
        )
        app.mount("/virals", StaticFiles(directory=VIRALS_DIR), name="virals")
        demo.block_thread()
    else:
        is_windows = (os.name == 'nt')
        library.set_url_mode("fastapi")
        allowed_dirs = [VIRALS_DIR, WORKING_DIR, os.getcwd(), "."]
        try:
            gr.set_static_paths(paths=allowed_dirs)
        except AttributeError:
            pass
        from fastapi.responses import FileResponse
        from fastapi import BackgroundTasks

        def attach_extra_routes(fastapi_app):
            fastapi_app.mount("/virals", StaticFiles(directory=VIRALS_DIR), name="virals")
            @fastapi_app.get("/export_xml_api")
            def export_xml_api(project: str, segment: int, background_tasks: BackgroundTasks, format: str = "premiere"):
                try:
                    project_path = os.path.join(VIRALS_DIR, project)
                    script_path = os.path.join(WORKING_DIR, "scripts", "export_xml.py")
                    if not os.path.exists(project_path):
                        return {"error": "Project not found."}
                    if not os.path.exists(script_path):
                        return {"error": "Export script not found."}
                    cmd = [sys.executable, script_path, "--project", project_path, "--segment", str(segment), "--format", format]
                    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
                    if result.returncode != 0:
                        return {"error": result.stderr.strip() or result.stdout.strip() or "Export failed."}
                    proj_name = os.path.basename(project_path)
                    zip_filename = f"export_{proj_name}_seg{segment}.zip"
                    file_path = os.path.join(project_path, zip_filename)
                    if os.path.exists(file_path):
                        return FileResponse(file_path, filename=zip_filename, media_type='application/zip')
                    return {"error": f"File generation failed. Expected: {file_path}"}
                except Exception as e:
                    return {"error": str(e)}
            print(f"Mounted /virals to {VIRALS_DIR}")

        if is_windows:
            print("Running in Windows environment (using Gradio launch for convenience).")
            app, local_url, share_url = demo.queue().launch(
                share=False,
                allowed_paths=allowed_dirs,
                inbrowser=True,
                server_name="0.0.0.0",
                server_port=7860,
                prevent_thread_lock=True,
                **_launch_theme_kwargs
            )
            attach_extra_routes(app)
            demo.block_thread()
        else:
            print("Running in Linux/Container environment (using Uvicorn for stability).")
            app = FastAPI()
            attach_extra_routes(app)
            if _GRADIO_MAJOR >= 6:
                # mount_gradio_app resets theme/css unless passed explicitly, and
                # builds the page config BEFORE applying them — so pass them in
                # and refresh the config afterwards.
                app = gr.mount_gradio_app(app, demo.queue(), path="/", allowed_paths=allowed_dirs,
                                          ssr_mode=False, theme=vc_theme, css=css, css_paths=[])
                demo.config = demo.get_config_file()
                demo.config["is_custom_theme"] = True
            else:
                app = gr.mount_gradio_app(app, demo.queue(), path="/", allowed_paths=allowed_dirs, ssr_mode=False)
            uvicorn.run(app,
                host="0.0.0.0",
                port=7860,
                log_level="info",
            )
