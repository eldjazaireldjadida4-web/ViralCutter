import os
import sys

# Suppress unnecessary logs before importing heavy libs
os.environ["ORT_LOGGING_LEVEL"] = "3" 
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

# Frozen exe: bundled tools (ffmpeg.exe, ffprobe.exe, fpcalc.exe) live in the
# onefile extraction dir (sys._MEIPASS). Put it on PATH so every subprocess
# that calls "ffmpeg"/"ffprobe" by name resolves them — no external install.
if getattr(sys, "frozen", False):
    _bundle_dir = getattr(sys, "_MEIPASS", "") or os.path.dirname(os.path.abspath(sys.executable))
    if _bundle_dir and _bundle_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _bundle_dir + os.pathsep + os.environ.get("PATH", "")

import warnings
warnings.filterwarnings("ignore")

import json
import shutil
import subprocess
import argparse
import time
import atexit
from scripts import (
    download_video,
    transcribe_video,
    create_viral_segments,
    cut_segments,
    edit_video,
    transcribe_cuts,
    adjust_subtitles,
    burn_subtitles,
    save_json,
    organize_output,
    translate_json,
    safety_filter,
    safety_ai,
    censor_engine,
    risk_scorecard,
    checkpoint,
    oom_guard,
    polish,
    upload_gate,
    metadata_compliance,
    secure_config,
    crash_report,
)
from i18n.i18n import I18nAuto, DEFAULT_LANGUAGE

# Inicializa sistema de tradução (default: Arabic; override with VIRALCUTTER_LANG)
i18n = I18nAuto(DEFAULT_LANGUAGE)

BASE_VERBOSE = os.getenv("VIRALCUTTER_VERBOSE", "").strip().lower() in {"1", "true", "yes", "on"}
RUNTIME_VERBOSE = BASE_VERBOSE

def debug(message):
    if RUNTIME_VERBOSE:
        print(f"[debug] {message}", flush=True)

def emit_progress(stage, percent, message):
    try:
        print(f"PROGRESS|{stage}|{int(percent)}|{message}", flush=True)
    except Exception:
        pass
#
TEMP_SUBTITLE_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_subtitle_config.json")

def cleanup_temp_files():
    try:
        if os.path.exists(TEMP_SUBTITLE_CONFIG):
            os.remove(TEMP_SUBTITLE_CONFIG)
    except Exception:
        pass

def load_json_file(path, default=None):
    if default is None:
        default = {}
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        debug(f"Failed to load JSON from {path}: {e}")
        return default

def parse_face_detect_interval(raw_value):
    if not raw_value:
        return None
    try:
        parts = [part.strip() for part in str(raw_value).split(",") if part.strip()]
        if len(parts) == 1:
            value = float(parts[0])
            return {"1": value, "2": value}
        if len(parts) >= 2:
            return {"1": float(parts[0]), "2": float(parts[1])}
    except ValueError:
        debug(f"Invalid face detection interval value: {raw_value}")
    return None

atexit.register(cleanup_temp_files)
#
# Configurações de Legenda (ASS Style)
# Cores no formato BGR (Blue-Green-Red) para o ASS
COLORS = {
    "red": "0000FF",  # Red
    "yellow": "00FFFF",   # Yellow
    "green": "00FF00",     # Green
    "white": "FFFFFF",    # White
    "black": "000000",     # Black
    "grey": "808080",     # Grey
}

def get_subtitle_config(config_path=None):
    """
    Returns the subtitle configuration dictionary.
    Can be expanded to load from a JSON/YAML file in the future.
    """
    # Default Config
    base_color_transparency = "00"
    outline_transparency = "FF" 
    highlight_color_transparency = "00"
    shadow_color_transparency = "00"
    
    config = {
        "font": "Montserrat-Regular",
        "base_size": 30,
        "base_color": f"&H{base_color_transparency}{COLORS['white']}&",
        "highlight_size": 35,
        "words_per_block": 3,
        "gap_limit": 0.5,
        "mode": 'highlight', # Options: 'no_highlight', 'word_by_word', 'highlight'
        "highlight_color": f"&H{highlight_color_transparency}{COLORS['green']}&",
        "vertical_position": 210, # 1=170(top), ... 4=60(default)
        "alignment": 2, # 2=Center
        "bold": 0,
        "italic": 0,
        "underline": 0,
        "strikeout": 0,
        "border_style": 2, # 1=outline, 3=box
        "outline_thickness": 1.5,
        "outline_color": f"&H{outline_transparency}{COLORS['grey']}&",
        "shadow_size": 2,
        "shadow_color": f"&H{shadow_color_transparency}{COLORS['black']}&",
        "remove_punctuation": True,
    }

    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)
                config.update(loaded_config)
                print(i18n("Loaded subtitle config from {}").format(config_path))
        except Exception as e:
            print(i18n("Error loading subtitle config: {}. Using defaults.").format(e))
    
    return config

def interactive_input_int(prompt_text):
    """Solicita um inteiro ao usuário via terminal."""
    while True:
        try:
            value = int(input(i18n(prompt_text)))
            if value > 0:
                return value
            print(i18n("\nError: Number must be greater than 0."))
        except ValueError:
            print(i18n("\nError: The value you entered is not an integer. Please try again."))

def _launch_webui():
    """Launch the Gradio WebUI — the default action when the app is opened
    without arguments (double-click), packaged or from source.

    The WebUI runs a local server on http://localhost:7860 and opens the
    browser. On failure (packaged exe) the console shows the error and stays
    open so the user can read it, and a crash log is written next to the app.
    """
    try:
        print(i18n("Launching ViralCutter WebUI → http://localhost:7860/ "
                   "(keep this window open while using the app)"))
        import threading
        import webbrowser
        threading.Timer(1.5, lambda: webbrowser.open("http://localhost:7860/")).start()
        import os as _os
        webui_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "webui")
        if webui_dir not in sys.path:
            sys.path.insert(0, webui_dir)
        import app as _webui_app  # noqa: F401 — webui/app.py launches and blocks
        return 0
    except Exception as e:
        print(i18n("ViralCutter WebUI failed to start: {}").format(e))
        import traceback
        traceback.print_exc()
        try:
            from scripts import crash_report
            crash_report.report("webui", e, log_path=_os.path.join(
                _os.path.dirname(_os.path.abspath(
                    sys.executable if getattr(sys, "frozen", False) else __file__)),
                "crash_report.log"))
        except Exception:
            pass
        if getattr(sys, "frozen", False):
            try:
                input("Press Enter to close this window...")
            except Exception:
                pass
        return 1


def main():
    if not hasattr(main, "_retried"):
        main._retried = False
    # Double-click UX: no arguments at all → open the WebUI (GUI), not the
    # interactive CLI. Packaged users double-click the exe and expect a GUI.
    if len(sys.argv) == 1:
        return _launch_webui()
    # Configuração de Argumentos via Linha de Comando (CLI)
    parser = argparse.ArgumentParser(description="ViralCutter CLI")
    parser.add_argument("--url", help="YouTube Video URL")
    parser.add_argument("--segments", type=int, help="Number of segments to create")
    parser.add_argument("--viral", action="store_true", help="Enable viral mode")
    parser.add_argument("--themes", help="Comma-separated themes (if not viral mode)")
    parser.add_argument("--burn-only", action="store_true", help="Skip processing and only burn subtitles")
    parser.add_argument("--min-duration", type=int, default=None, help="Minimum segment duration (seconds; default from --platform template or 15)")
    parser.add_argument("--max-duration", type=int, default=None, help="Maximum segment duration (seconds; default from --platform template or 90)")
    parser.add_argument("--platform", choices=["yt_shorts", "tiktok", "reels", "yt_standard"], default=None,
                        help="Platform output template (Roadmap 5.2): sets duration defaults + aspect hint. yt_shorts (9:16 ≤60s), tiktok/reels (9:16 ≤90s), yt_standard (16:9 ≤10min)")
    parser.add_argument("--model", default="large-v3-turbo", help="Whisper model to use")
    
    parser.add_argument("--ai-backend", choices=["manual", "gemini", "g4f", "local"], help="AI backend for viral analysis")
    parser.add_argument("--api-key", help="Gemini API Key (required if ai-backend is gemini)")
    
    parser.add_argument("--chunk-size", help="Override Chunk Size")
    parser.add_argument("--ai-model-name", help="Override AI Model Name")

    parser.add_argument("--project-path", help="Path to existing project folder (overrides URL/Latest)")
    parser.add_argument("--workflow", choices=["1", "2", "3"], default="1", help="Workflow choice: 1=Full, 2=Cut Only, 3=Subtitles Only")
    parser.add_argument("--face-model", choices=["insightface", "mediapipe"], default="insightface", help="Face detection model")
    parser.add_argument("--face-mode", choices=["auto", "1", "2"], default="auto", help="Face tracking mode: auto, 1, 2")
    parser.add_argument("--subtitle-config", help="Path to subtitle configuration JSON file")
    parser.add_argument("--no-face-mode", choices=["padding", "zoom"], default="padding", help="Method to handle segments with no face detected: 'padding' (9:16 frame with black bars) or 'zoom' (Center Crop Zoom)")
    parser.add_argument("--face-detect-interval", type=str, default="0.17,1.0", help="Face detection interval in seconds. Single value or 'interval_1face,interval_2face'")
    parser.add_argument("--face-filter-threshold", type=float, default=0.35, help="Relative area threshold to ignore background faces (default: 0.35)")
    parser.add_argument("--face-two-threshold", type=float, default=0.60, help="Relative area threshold to trigger 2-face mode (default: 0.60)")
    parser.add_argument("--face-confidence-threshold", type=float, default=0.30, help="Face detection confidence threshold (0.0 - 1.0) (default: 0.30)")
    parser.add_argument("--face-dead-zone", type=str, default="40", help="Camera movement dead zone in pixels (default: 40)") # str to support future "auto"
    parser.add_argument("--focus-active-speaker", action="store_true", help="Enable experimental active speaker focus (InsightFace only)")
    parser.add_argument("--active-speaker-mar", type=float, default=0.03, help="Mouth Aspect Ratio threshold for active speaker (0.0 - 1.0) (default: 0.03)")
    parser.add_argument("--active-speaker-score-diff", type=float, default=1.5, help="Score difference to focus on active speaker (default: 1.5)")
    parser.add_argument("--include-motion", action="store_true", help="Include motion (body/head movement) in activity score")
    parser.add_argument("--active-speaker-motion-threshold", type=float, default=3.0, help="Motion deadzone in pixels (default: 3.0)")
    parser.add_argument("--active-speaker-motion-sensitivity", type=float, default=0.05, help="Motion sensitivity multiplier (default: 0.05)")
    parser.add_argument("--active-speaker-decay", type=float, default=2.0, help="Activity score decay rate (default: 2.0)")
    parser.add_argument("--skip-prompts", action="store_true", help="Skip interactive prompts and use defaults/existing files")
    parser.add_argument("--video-quality", choices=["best", "1080p", "720p", "480p"], default="best", help="Video download quality")
    parser.add_argument("--skip-youtube-subs", action="store_true", help="Skip downloading YouTube subtitles")
    parser.add_argument("--translate-target", help="Target language code for subtitle translation (e.g. 'pt', 'en').")
    parser.add_argument("--workers", type=int, help="Number of parallel workers for segment cutting")
    parser.add_argument("--prefer-hardware-acceleration", action="store_true", default=None, help="Prefer hardware video encoding when available")
    parser.add_argument("--verbose", action="store_true", help="Print extra debug information")
    parser.add_argument("--safety-mode", choices=["block", "flag", "censor", "off"], default="block",
                        help="Policy safety filter (hate speech / violence): 'block' removes violating segments before cutting (default), 'flag' only annotates them, 'censor' keeps segments but BLEEPs the violating words (mute audio + mask subtitles), 'off' disables the filter")
    parser.add_argument("--safety-min-severity", choices=["low", "medium", "high"], default="medium",
                        help="Minimum severity that blocks a segment in 'block' mode (default: medium)")
    parser.add_argument("--safety-extra-terms", help="Path to a safety_terms.json file with extra blocked terms")
    parser.add_argument("--safety-ai", choices=["on", "off"], default="on",
                        help="Second-pass AI policy review of surviving segments (context-level violations keywords can't catch). Only used with gemini/g4f backends. Default: on")
    parser.add_argument("--safety-autoupdate", choices=["on", "off"], default="on",
                        help="Auto-update the hate-speech word list from GitHub once a day (offline-safe). Default: on")
    parser.add_argument("--risk-scorecard", choices=["on", "off"], default="on",
                        help="Per-clip YouTube risk scorecard (reused-content / monetization / visual warnings) after rendering. Default: on")
    parser.add_argument("--risk-gate", choices=["off", "warn", "block"], default="warn",
                        help="What to do when a clip fails the compliance gate: 'warn' prints warnings and writes publish_blocklist.json (default), 'block' stops the run, 'off' does nothing")
    parser.add_argument("--music-check", choices=["on", "off", "auto"], default="auto",
                        help="Chromaprint music fingerprint check (Roadmap 2.3): 'auto' runs it only when fpcalc/pyacoustid is installed. Default: auto")
    parser.add_argument("--music-gate", choices=["warn", "block", "off"], default="warn",
                        help="How to treat audio fingerprint matches in the upload gate: 'warn' flags (default), 'block' refuses publishing matched clips, 'off' ignores")
    parser.add_argument("--music-local-db", default=None,
                        help="Local reference-music DB: JSON cache from 'python -m scripts.music_fingerprint --build-local-db' or a folder of songs to fingerprint on the fly")
    parser.add_argument("--acoustid-key", default=None, help="AcoustID API key (or ACOUSTID_API_KEY env) for the music check")

    # --- Sprint 3/4/5 features (added in v6) ---
    parser.add_argument("--checkpoint", choices=["on", "off"], default="on",
                        help="Crash-safe resume: skip stages completed in a previous run (checkpoint.json per project). Default: on")
    parser.add_argument("--check-updates", action="store_true",
                        help="Check GitHub Releases for a newer ViralCutter build at startup")
    parser.add_argument("--polish", choices=["on", "off"], default="off",
                        help="Run the professional polish pass (jump cuts + punch zoom + background music + branding) after editing, before subtitles. Default: off")
    parser.add_argument("--polish-stages", default="jump_cuts,punch_zoom,background_music,branding",
                        help="Comma-separated polish stages to run (with --polish)")
    parser.add_argument("--music", default=None, help="Background music file (with --polish; default: <project>/music/ folder)")
    parser.add_argument("--music-volume", type=float, default=0.15, help="Background music volume (0..1)")
    parser.add_argument("--logo", default=None, help="Channel logo PNG for the watermark (with --polish)")
    parser.add_argument("--intro", default=None, help="Intro clip to prepend (with --polish)")
    parser.add_argument("--outro", default=None, help="Outro clip to append (with --polish)")
    parser.add_argument("--zoom-keywords", default=None,
                        help="Comma-separated keywords that trigger punch-in zoom (with --polish)")
    parser.add_argument("--metadata-gate", choices=["off", "warn", "block"], default="warn",
                        help="Metadata compliance gate (title/caption/hashtags): 'warn' flags + writes to the scorecard (default), 'block' stops the run when any clip has risky metadata, 'off' skips it")
    parser.add_argument("--auto-download-visual", action="store_true",
                        help="Download the small ONNX visual classifier into models/ when missing (Roadmap 2.1)")
    parser.add_argument("--allow-placeholder-transcription", action="store_true",
                        help="When whisperx/torch are missing, continue with placeholder subtitles (for testing editing/safety only — NOT for real viral-segment selection)")
    parser.add_argument("--cookies-from-browser", choices=["chrome", "firefox", "edge", "safari", "brave", "opera", "vivaldi"], default=None,
                        help="Use your browser's login cookies to download private / age-restricted videos (e.g. --cookies-from-browser chrome)")
    parser.add_argument("--cookies", default=None,
                        help="Path to a Netscape-format cookies.txt file exported for yt-dlp (alternative to --cookies-from-browser)")
    parser.add_argument("--title-language", default="auto",
                        help="Output language for titles/captions: 'auto' (match the transcript, default) or a code like 'ar', 'en', 'fr', 'es', 'pt', 'de', 'tr', 'ru', 'hi'")
    parser.add_argument("--webui", action="store_true",
                        help="Launch the Gradio WebUI (GUI). This is also the default when "
                             "the app is opened with NO arguments (double-click) — both in "
                             "the packaged exe and from source.")

    args = parser.parse_args()

    if args.webui:
        return _launch_webui()
    global RUNTIME_VERBOSE
    RUNTIME_VERBOSE = BASE_VERBOSE or args.verbose

    # Version marker — helps support identify stale local copies
    try:
        from app_version import VERSION as _VERSION
        print("ViralCutter v{} (check: git pull / see docs)".format(_VERSION))
    except Exception:
        pass

    # Escape hatch for testing without whisperx/torch (read by transcribe_video)
    if args.allow_placeholder_transcription:
        os.environ["VIRALCUTTER_ALLOW_PLACEHOLDER"] = "1"

    # Platform template (Roadmap 5.2): resolve duration defaults once, up front.
    if args.platform:
        try:
            from scripts import platform_templates
            args.min_duration, args.max_duration, _tpl = platform_templates.resolve_durations(
                args.platform, args.min_duration, args.max_duration)
            print(i18n("Platform template: {}").format(
                platform_templates.describe(args.platform)))
        except Exception as e:
            debug("Platform template failed: {}".format(e))
    if args.min_duration is None:
        args.min_duration = 15
    if args.max_duration is None:
        args.max_duration = 90

    # Optional startup update check (Roadmap 1.2) — never blocks startup.
    if args.check_updates:
        try:
            from scripts import auto_updater
            upd = auto_updater.check_for_update()
            if upd.get("update_available"):
                print(i18n("[auto-update] 🚀 ViralCutter {} available (local: {}). "
                           "Download: {}").format(
                    upd.get("latest_version"), auto_updater.LOCAL_VERSION,
                    upd.get("download_url") or "see GitHub Releases"))
            elif upd.get("error"):
                debug("Update check skipped: {}".format(upd["error"]))
            else:
                debug("Up to date (local: {}).".format(auto_updater.LOCAL_VERSION))
        except Exception as e:
            debug("Update check failed (ignored): {}".format(e))
    
    # Workflow Logic
    workflow_choice = args.workflow
    
    # If Subtitles Only, checking project path
    if workflow_choice == "3" and not args.project_path and not args.url and not args.skip_prompts:
        # Prompt for project path or use latest if not provided?
        pass # Will handle in main flow

    # Modo Apenas Queimar Legenda (Legacy support, mapped to Workflow 3 internally if burn-only is set)
    # Verifica o argumento CLI ou uma variável local hardcoded (para compatibilidade)
    burn_only_mode = args.burn_only

    if burn_only_mode:
        print(i18n("Burn only mode activated. Switching to Workflow 3..."))
        workflow_choice = "3"

    # Obtenção de Inputs (CLI ou Interativo)
    url = args.url
    project_path_arg = args.project_path
    input_video = None

    # Se project_path for fornecido, ignoramos URL
    if project_path_arg:
        if os.path.exists(project_path_arg):
             print(i18n("Using provided project path: {}").format(project_path_arg))
             # Tentar achar o input.mp4 pra manter compatibilidade de variaveis, embora Workflow 3 não precise de download
             possible_input = os.path.join(project_path_arg, "input.mp4")
             if os.path.exists(possible_input):
                 input_video = possible_input
             else:
                 # Se não tiver input.mp4, tudo bem para workflow 3, mas definimos um dummy para não quebrar logica
                 input_video = os.path.join(project_path_arg, "dummy_input.mp4")
             
             # Se for workflow 3, não precisamos de URL
        else:
             print(i18n("Error: Provided project path does not exist."))
             sys.exit(1)

    # Se não temos URL via CLI nem Project Path, pedimos agora
    if not url and not project_path_arg:
        if args.skip_prompts:
             print(i18n("No URL provided and skipping prompts. Trying to load latest project..."))
             # Fallthrough to project loading logic
        else:
            user_input = input(i18n("Enter the YouTube video URL (or press Enter to use latest project): ")).strip()
            if user_input:
                url = user_input
    
    if not url and not input_video:
        # Usuário apertou Enter (Vazio) -> Tentar pegar último projeto
        base_virals = "VIRALS"
        if os.path.exists(base_virals):
            subdirs = [os.path.join(base_virals, d) for d in os.listdir(base_virals) if os.path.isdir(os.path.join(base_virals, d))]
            if subdirs:
                latest_project = max(subdirs, key=os.path.getmtime)
                detected_video = os.path.join(latest_project, "input.mp4")
                if os.path.exists(detected_video):
                    input_video = detected_video
                    print(i18n("Using latest project: {}").format(latest_project))
                else:
                    print(i18n("Latest project found but 'input.mp4' is missing."))
                    sys.exit(1)
            else:
                print(i18n("No existing projects found in VIRALS folder."))
                sys.exit(1)
        else:
             print(i18n("VIRALS folder not found. Cannot load latest project."))
             sys.exit(1)

    # -------------------------------------------------------------------------
    # Checagem Antecipada de Segmentos Virais (Para pular configurações se já existirem)
    # -------------------------------------------------------------------------
    viral_segments = None
    project_folder_anticipated = None

    if input_video:
        # Se já temos o vídeo, podemos deduzir a pasta
        project_folder_anticipated = os.path.dirname(input_video)
        viral_segments_file = os.path.join(project_folder_anticipated, "viral_segments.txt")
        
        if os.path.exists(viral_segments_file):
             print(i18n("\nExisting viral segments found: {}").format(viral_segments_file))
             if args.skip_prompts:
                 use_existing_json = 'yes'
             else:
                 use_existing_json = input(i18n("Use existing viral segments? (yes/no) [default: yes]: ")).strip().lower()
             
             if use_existing_json in ['', 'y', 'yes']:
                try:
                    with open(viral_segments_file, 'r', encoding='utf-8') as f:
                        viral_segments = json.load(f)
                    print(i18n("Loaded existing viral segments. Skipping configuration prompts."))
                    if viral_segments and "segments" in viral_segments:
                        print(f"DEBUG: Loaded {len(viral_segments['segments'])} segments from file.")
                    else:
                        debug("Loaded JSON but 'segments' key is missing or empty.")
                except Exception as e:
                    print(i18n("Error loading JSON: {}.").format(e))

    # Variaveis de config de IA (só necessárias se não tivermos os segmentos)
    num_segments = None
    viral_mode = False
    themes = ""
    ai_backend = "manual" # default
    api_key = None
    
    if not viral_segments:
        num_segments = args.segments
        if not num_segments:
            if args.skip_prompts:
                print(i18n("No segments count provided and skip-prompts is ON. Using default 3."))
                num_segments = 3
            else:
                num_segments = interactive_input_int("Enter the number of viral segments to create: ")

        viral_mode = args.viral
        if not args.viral and not args.themes:
            if args.skip_prompts:
                print(i18n("Viral mode not set, defaulting to True."))
                viral_mode = True
            else:
                response = input(i18n("Do you want viral mode? (yes/no): ")).lower()
                viral_mode = response in ['yes', 'y']
        
        themes = args.themes if args.themes else ""
        if not viral_mode and not themes:
            if not args.skip_prompts:
                 themes = input(i18n("Enter themes (comma-separated, leave blank if viral mode is True): "))

        # Duration Config
        print(i18n("\nCurrent duration settings: {}s - {}s").format(args.min_duration, args.max_duration))
        if not args.skip_prompts:
            change_dur = input(i18n("Change duration? (y/n) [default: n]: ")).strip().lower()
            if change_dur in ['y', 'yes']:
                 try:
                     min_d = input(i18n("Minimum duration [{}]: ").format(args.min_duration)).strip()
                     if min_d: args.min_duration = int(min_d)
                     
                     max_d = input(i18n("Maximum duration [{}]: ").format(args.max_duration)).strip()
                     if max_d: args.max_duration = int(max_d)
                 except ValueError:
                     print(i18n("Invalid number. Using previous values."))

        # Load API Config (env vars and the encrypted store take priority — Roadmap 4.4)
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'api_config.json')
        api_config = secure_config.load_api_config()

        # Seleção do Backend de IA
        ai_backend = args.ai_backend
        
        # Try to load backend from config if not in args
        if not ai_backend and api_config.get("selected_api"):
            ai_backend = api_config.get("selected_api")
            print(i18n("Using AI Backend from config: {}").format(ai_backend))

        if not ai_backend:
            if args.skip_prompts:
                print(i18n("No AI backend selected, defaulting to Manual."))
                ai_backend = "manual"
            else:
                print("\n" + i18n("Select AI Backend for Viral Analysis:"))
                print(i18n("1. Gemini API (Best / Recommended)"))
                print(i18n("2. G4F (Free / Experimental)"))
                print(i18n("3. Local (GGUF via llama.cpp)"))
                print(i18n("4. Manual (Copy/Paste Prompt)"))
                choice = input(i18n("Choose (1-4): ")).strip()
                
                if choice == "1":
                    ai_backend = "gemini"
                elif choice == "2":
                    ai_backend = "g4f"
                elif choice == "3":
                    ai_backend = "local"
                    # Interactive model selection for local
                    # List models
                    models_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
                    if not os.path.exists(models_dir): os.makedirs(models_dir)
                    models = [f for f in os.listdir(models_dir) if f.endswith(".gguf")]
                    
                    if not models:
                        print(i18n("\nNo .gguf models found in 'models' directory."))
                        print(i18n("Please place a module file in: {}").format(models_dir))
                        print(i18n("Falling back to Manual..."))
                        ai_backend = "manual"
                    else:
                        print(i18n("\nAvailable Models:"))
                        for idx, m in enumerate(models):
                            print(f"{idx+1}. {m}")
                        
                        try:
                            m_idx = int(input(i18n("Select Model (Number): "))) - 1
                            if 0 <= m_idx < len(models):
                                args.ai_model_name = models[m_idx] # Set global arg
                            else:
                                print(i18n("Invalid selection. Using first model."))
                                args.ai_model_name = models[0]
                        except:
                             print(i18n("Invalid input. Using first model."))
                             args.ai_model_name = models[0]
                             
                else:
                    ai_backend = "manual"

        api_key = args.api_key
        env_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if ai_backend == "gemini" and not api_key and env_api_key:
            api_key = env_api_key
            debug("Using Gemini API key from GEMINI_API_KEY environment variable.")
        # Check config for API Key if using Gemini
        if ai_backend == "gemini" and not api_key:
            cfg_key = api_config.get("gemini", {}).get("api_key", "")
            if cfg_key and cfg_key != "SUA_KEY_AQUI":
                api_key = cfg_key
        
        if ai_backend == "gemini" and not api_key:
             if args.skip_prompts:
                 print(i18n("Gemini API key missing, but skip-prompts is ON. Might fail."))
             else:
                 print(i18n("Gemini API Key not found in api_config.json or arguments."))
                 api_key = input(i18n("Enter your Gemini API Key: ")).strip()

    # Workflow & Face Config Inputs
    workflow_choice = args.workflow
    face_model = args.face_model
    face_mode = args.face_mode

    # If args weren't provided and we are not skipping prompts, ask user
    # Note: argparse defaults are set, so they "are provided" effectively.
    # To truly detect "not provided", request default=None in argparse. 
    # But for "Simplified Mode", defaults are good.
    # Advanced users use params.
    # We will assume CLI defaults are what we want if skip_prompts is on.
    
    # Logic for detection intervals (Moved out of interactive block to support CLI/WebUI)
    detection_intervals = parse_face_detect_interval(args.face_detect_interval)

    if not args.burn_only and not args.skip_prompts:
        # Interactive Face Config
        print(i18n("\n--- Face Detection Settings ---"))
        print(i18n("Current Face Model: {} | Mode: {}").format(face_model, face_mode))
        
        if detection_intervals:
             print(i18n("Custom detection intervals: {}").format(detection_intervals))
        else:
             print(i18n("Using dynamic intervals: 1s for 2-face, ~0.16s for 1-face."))


    # Pipeline Execution
    try:
        # 1. Download & Project Setup
        print(f"DEBUG: Checking input_video state. input_video={input_video}")
        
        if not input_video:
            if not url:
                print(i18n("Error: No URL provided and no existing video selected."))
                sys.exit(1)
                
            print(i18n("Starting download..."))
            emit_progress("download", 5, "Download started")
            download_subs = not args.skip_youtube_subs
            # Download with an interactive cookies retry: when the video is
            # private/age-restricted and the user runs interactively (not from
            # the WebUI, which has no TTY), offer to retry with browser cookies.
            _interactive_tty = False
            try:
                _interactive_tty = sys.stdin.isatty()
            except Exception:
                pass
            _auth_retried = False
            while True:
                try:
                    download_result = download_video.download(
                        url, download_subs=download_subs, quality=args.video_quality,
                        cookies_from_browser=args.cookies_from_browser,
                        cookies_file=args.cookies)
                    break
                except download_video.AuthNeededError as auth_err:
                    if (_interactive_tty and not args.skip_prompts
                            and not args.cookies_from_browser and not args.cookies
                            and not _auth_retried):
                        _auth_retried = True
                        print(i18n("\nThis video needs a logged-in YouTube account."))
                        resp = input(i18n("Retry using your Chrome browser cookies? (yes/no): ")).strip().lower()
                        if resp in ('y', 'yes'):
                            args.cookies_from_browser = 'chrome'
                            continue
                    raise SystemExit(1)
            
            # Guard FIRST: a failed/empty download must never reach
            # os.path.dirname(None) (this crashed on Windows — v6.3c).
            if not download_result:
                print(i18n("\n[ERROR] The video could not be downloaded. "
                           "Check the URL, or use --cookies-from-browser for "
                           "private / age-restricted videos."))
                sys.exit(1)
            if isinstance(download_result, tuple):
                input_video, project_folder = download_result
            else:
                input_video = download_result
                project_folder = os.path.dirname(input_video)

            if not input_video or not os.path.exists(input_video):
                print(i18n("\n[ERROR] The downloaded video file is missing. "
                           "Check the URL, or use --cookies-from-browser for "
                           "private / age-restricted videos."))
                sys.exit(1)
                
            print(f"DEBUG: Download finished. input_video={input_video}, project_folder={project_folder}")
            emit_progress("download", 15, "Download complete")
            
        else:
            # Reuso de video existente
            print("DEBUG: Using existing video logic.")
            project_folder = os.path.dirname(input_video)
            
        print(f"Project Folder: {project_folder}")
        
        # Crash-safe resume tracker (Roadmap 4.2): completed stages are
        # skipped when a previous run was interrupted.
        tracker = checkpoint.StageTracker(project_folder, enabled=(args.checkpoint == "on"))
        pending = tracker.resume_info()
        if pending["pending"]:
            debug("Checkpoint: stages pending → {}".format(", ".join(pending["pending"])))
        
        # 2. Transcribe
        if workflow_choice == "3":
            print(i18n("Workflow 3: Skipping Transcribe."))
            # We assume transcription exists (SRT/JSON) or we won't need it for 'adjust_subtitles' if it uses 'subs/*.json' which are created by 'cut_segments'
            # Actually 'adjust_subtitles' reads from 'project_folder/subs'.
            # viral_segments = True # Removed to avoid overwritting dict loaded earlier
        else:
            print(i18n("Transcribing with model {}...").format(args.model))
            emit_progress("transcribe", 20, "تفريغ الصوت")
            # Se skip config, args.model é default
            # GPU OOM guard (Roadmap 4.1) + checkpoint resume (Roadmap 4.2)
            _transcribe_result = tracker.run(
                "transcribe",
                oom_guard.transcribe_with_fallback,
                input_video, args.model,
                project_folder=project_folder)
            if _transcribe_result is None:
                # stage already completed in a previous run → reuse files
                base_name = os.path.splitext(os.path.basename(input_video))[0]
                srt_file = os.path.join(project_folder, base_name + ".srt")
                tsv_file = os.path.join(project_folder, base_name + ".tsv")
            else:
                srt_file, tsv_file = _transcribe_result
            emit_progress("transcribe", 65, "تفريغ الصوت")
 
        # 3. Create Viral Segments
        if workflow_choice != "3":
            # Se não carregamos 'viral_segments' lá em cima (ou se era download novo), checamos agora ou criamos
            if not viral_segments:
                # Checagem tardia para downloads novos que por acaso ja tenham json (Ex: URL repetida)
                viral_segments_file_late = os.path.join(project_folder, "viral_segments.txt")
                if os.path.exists(viral_segments_file_late):
                    print(i18n("Found existing viral segments file at {}").format(viral_segments_file_late))
                    if args.skip_prompts:
                        print(i18n("Skipping prompts enabled. Loading existing segments."))
                        try:
                            with open(viral_segments_file_late, 'r', encoding='utf-8') as f:
                                viral_segments = json.load(f)
                        except Exception as e:
                            print(i18n("Error loading existing JSON: {}. Proceeding to create new segments.").format(e))
                    else:
                        print(i18n("Loading existing viral segments found at {}").format(viral_segments_file_late))
                        try:
                            with open(viral_segments_file_late, 'r', encoding='utf-8') as f:
                                viral_segments = json.load(f)
                        except Exception as e:
                            print(i18n("Error loading existing JSON: {}.").format(e))
                    
                if not viral_segments:
                    print(i18n("Creating viral segments using {}...").format(ai_backend.upper()))
                    emit_progress("ai", 30, "تحليل AI")
                    viral_segments = create_viral_segments.create(
                        num_segments, 
                        viral_mode, 
                        themes, 
                        args.min_duration, 
                        args.max_duration,
                        ai_mode=ai_backend,
                        api_key=api_key,
                        project_folder=project_folder,
                        chunk_size_arg=args.chunk_size,
                        model_name_arg=args.ai_model_name,
                        title_language=args.title_language
                    )
                
                emit_progress("ai", 55, "تحليل AI")
                if not viral_segments or not viral_segments.get("segments"):
                    print(i18n("Error: No viral segments were generated."))
                    print(i18n("Possible reasons: API error, Model not found, or empty response."))
                    print(i18n("Stopping execution."))
                    sys.exit(1)
                
                save_json.save_viral_segments(viral_segments, project_folder=project_folder) 

        # 3.5. Fix Raw Segments (missing timestamps)
        if workflow_choice != "3" and viral_segments and "segments" in viral_segments:
            segs = viral_segments.get("segments", [])
            if segs and len(segs) > 0:
                 # Check first segment for duration 0 but having start_time_ref or just check duration
                 first = segs[0]
                 # If duration is effectively 0 and we have a ref tag (or even if we dont, we cant cut 0s video)
                 # We assume if duration is 0, it is raw.
                 if first.get("duration", 0) == 0:
                      print(i18n("Detected raw AI segments without timestamps (Duration 0). Running alignment..."))
                      try:
                          # Load transcript
                          transcript = create_viral_segments.load_transcript(project_folder)
                          # Process (Align)
                          # Use None for output_count to keep all found segments
                          viral_segments = create_viral_segments.process_segments(
                              segs, 
                              transcript, 
                              args.min_duration, 
                              args.max_duration, 
                              output_count=None 
                          )
                          save_json.save_viral_segments(viral_segments, project_folder=project_folder)
                          print(i18n("Segments aligned and saved."))
                      except Exception as e:
                          print(i18n("Failed to align raw segments: {}").format(e))
                          # If alignment fails, it might crash later, but we tried. 

        # 3.7. Safety Filter (YouTube hate-speech / violence policy shield)
        if workflow_choice != "3" and viral_segments and "segments" in viral_segments:
            if args.safety_mode != "off":
                # Auto-update the word list from GitHub (daily throttle, offline-safe)
                if args.safety_autoupdate == "on":
                    try:
                        from scripts import safety_updater
                        upd = safety_updater.check_and_update()
                        if upd.get("status") == "updated":
                            print(i18n("[safety-updater] {}").format(upd["message"]))
                        elif upd.get("status") == "offline":
                            debug("Safety list update skipped (offline) — using local list.")
                    except Exception as e:
                        debug(f"Safety list auto-update failed: {e}")

                print(i18n("Running safety filter (mode: {})...").format(args.safety_mode))
                emit_progress("ai", 58, "فحص الأمان")
                try:
                    filtered = safety_filter.apply_safety_filter(
                        viral_segments,
                        project_folder=project_folder,
                        mode=args.safety_mode,
                        min_severity=args.safety_min_severity,
                        extra_terms_path=args.safety_extra_terms,
                        i18n=i18n,
                    )
                    if filtered is not viral_segments:
                        viral_segments = filtered
                        save_json.save_viral_segments(viral_segments, project_folder=project_folder, overwrite=True)
                except Exception as e:
                    print(i18n("Safety filter failed (continuing without it): {}").format(e))

                # 3.8. Second-pass AI policy review (context-level violations)
                if safety_ai.should_run_ai_review(ai_backend, args.safety_ai) and viral_segments.get("segments"):
                    print(i18n("Running AI safety review..."))
                    try:
                        kept_segments = viral_segments.get("segments", [])
                        transcript_for_review = safety_filter.load_transcript(project_folder)
                        clips = [{
                            "index": pos,
                            "title": seg.get("title", ""),
                            "text": safety_filter.segment_text(seg, transcript_for_review),
                        } for pos, seg in enumerate(kept_segments)]
                        verdicts = safety_ai.review_segments(
                            clips, ai_backend,
                            api_key=api_key, model_name=args.ai_model_name)
                        if verdicts:
                            kept_after, ai_report = safety_ai.apply_ai_review(
                                kept_segments, clips, verdicts, mode=args.safety_mode)
                            flagged_n = len(ai_report)
                            if flagged_n:
                                print(i18n("AI review: {} segment(s) flagged by AI policy review.").format(flagged_n))
                                for entry in ai_report:
                                    print(i18n("[safety-ai]   ✗ '{}' — {}").format(entry["title"], entry["reason"]))
                                viral_segments = dict(viral_segments)
                                viral_segments["segments"] = kept_after
                                save_json.save_viral_segments(viral_segments, project_folder=project_folder, overwrite=True)
                                # merge AI verdicts into the safety report
                                try:
                                    report_path = os.path.join(project_folder, "safety_report.json")
                                    report_data = load_json_file(report_path, default={})
                                    report_data["ai_review"] = ai_report
                                    with open(report_path, "w", encoding="utf-8") as rf:
                                        json.dump(report_data, rf, ensure_ascii=False, indent=2)
                                except Exception as e:
                                    debug(f"Could not merge AI review into report: {e}")
                            else:
                                print(i18n("AI review: all surviving segments look clean ✔"))
                    except Exception as e:
                        print(i18n("AI safety review failed (continuing): {}").format(e))
                elif args.safety_ai == "on" and args.safety_mode != "off":
                    debug(f"AI safety review skipped for backend '{ai_backend}' (needs gemini/g4f).")

                if args.safety_mode in ("block", "censor") and not viral_segments.get("segments"):
                    print(i18n("Error: All segments were blocked by the safety filter (hate speech / policy violations)."))
                    print(i18n("Check safety_report.json in the project folder for details. Nothing was cut."))
                    sys.exit(1)

        # 4. Cut Segments
        # Se workflow for 3, pulamos corte
        if workflow_choice == "3":
            print(i18n("Workflow 3 (Subtitles Only): Skipping Cut and Edit."))
            # Deduzir cuts folder apenas para log
            cuts_folder = os.path.join(project_folder, "cuts")
        else:
            cuts_folder = os.path.join(project_folder, "cuts")
            skip_cutting = False
            
            if os.path.exists(cuts_folder) and os.listdir(cuts_folder):
                print(i18n("\nExisting cuts found in: {}").format(cuts_folder))
                if args.skip_prompts:
                    cut_again_resp = 'no'
                else:
                    cut_again_resp = input(i18n("Cuts already exist. Cut again? (yes/no) [default: no]: ")).strip().lower()
                
                # Default is no (skip) if they just press enter or say no
                if cut_again_resp not in ['y', 'yes']:
                    skip_cutting = True
            
            if skip_cutting:
                print(i18n("Skipping Video Rendering (using existing cuts), but updating Subtitle JSONs..."))
            else:
                print(i18n("Cutting segments..."))
            emit_progress("cut", 70, "Cutting segments")

            tracker.run("cut", cut_segments.cut, viral_segments,
                        project_folder=project_folder, skip_video=skip_cutting,
                        workers=args.workers)
            emit_progress("cut", 80, "Cutting segments")

            # 4.5. Bleep censoring (mute violating words in audio + subtitles)
            if args.safety_mode == "censor":
                print(i18n("Censoring violating words (bleep mode)..."))
                try:
                    censor_engine.censor_project(
                        project_folder,
                        viral_segments,
                        min_severity=args.safety_min_severity,
                        extra_terms_path=args.safety_extra_terms,
                        i18n=i18n,
                    )
                except Exception as e:
                    print(i18n("Censoring failed (continuing without it): {}").format(e))
        
        # 5. Workflow Check
        if workflow_choice == "2":
            print(i18n("Cut Only selected. Skipping Face Crop and Subtitles."))
            print(i18n(f"Process completed! Check your results in: {project_folder}"))
            sys.exit(0)

        # 5. Edit Video (Face Crop)
        if workflow_choice != "3":
            print(i18n("Editing video with {} (Mode: {})...").format(face_model, face_mode))
            
            # Parse dead zone safely
            try:
                dead_zone_val = float(args.face_dead_zone)
            except:
                dead_zone_val = 40.0
                
            emit_progress("edit", 85, "Editing video")
            tracker.run("edit", edit_video.edit,
                        project_folder=project_folder, 
                        face_model=face_model, 
                        face_mode=face_mode, 
                        detection_period=detection_intervals,
                        filter_threshold=args.face_filter_threshold,
                        two_face_threshold=args.face_two_threshold,
                        confidence_threshold=args.face_confidence_threshold,
                        dead_zone=dead_zone_val,
                        focus_active_speaker=args.focus_active_speaker,
                        active_speaker_mar=args.active_speaker_mar,
                        active_speaker_score_diff=args.active_speaker_score_diff,
                        include_motion=args.include_motion,
                        active_speaker_motion_deadzone=args.active_speaker_motion_threshold,
                        active_speaker_motion_sensitivity=args.active_speaker_motion_sensitivity,
                        active_speaker_decay=args.active_speaker_decay,
                        segments_data=viral_segments.get("segments", []) if viral_segments else None,
                        no_face_mode=args.no_face_mode
            )


        else:
            print(i18n("Workflow 3: Skipping Face Crop."))
            # Rename existing files if viral_segments available (since edit_video didn't run)
            if viral_segments and "segments" in viral_segments:
                 segments_data = viral_segments.get("segments", [])
                 final_folder = os.path.join(project_folder, "final")
                 subs_folder = os.path.join(project_folder, "subs")
                 
                 print(i18n("Renaming existing files with titles..."))
                 for idx, segment in enumerate(segments_data):
                     title = segment.get("title", f"Segment_{idx}")
                     safe_title = "".join([c for c in title if c.isalnum() or c in " _-"]).strip()
                     safe_title = safe_title.replace(" ", "_")[:60]
                     
                     new_base_name = f"{idx:03d}_{safe_title}"
                     
                     # 1. MP4
                     old_mp4_name = f"final-output{idx:03d}_processed.mp4"
                     old_mp4_path = os.path.join(final_folder, old_mp4_name)
                     new_mp4_path = os.path.join(final_folder, f"{new_base_name}.mp4")
                     if os.path.exists(old_mp4_path) and not os.path.exists(new_mp4_path):
                         os.rename(old_mp4_path, new_mp4_path)
                         print(f"Renamed (Workflow 3): {old_mp4_name} -> {new_base_name}.mp4")

                     # 2. JSON Sub
                     old_json_name = f"final-output{idx:03d}_processed.json"
                     old_json_path = os.path.join(subs_folder, old_json_name)
                     new_json_path = os.path.join(subs_folder, f"{new_base_name}_processed.json")
                     if os.path.exists(old_json_path) and not os.path.exists(new_json_path):
                         os.rename(old_json_path, new_json_path)
                         print(f"Renamed (Workflow 3): {old_json_name} -> {new_base_name}_processed.json")
                         
                     # 3. Timeline
                     old_tl_name = f"temp_video_no_audio_{idx}_timeline.json"
                     old_tl_path = os.path.join(final_folder, old_tl_name)
                     new_tl_path = os.path.join(final_folder, f"{new_base_name}_timeline.json")
                     if os.path.exists(old_tl_path) and not os.path.exists(new_tl_path):
                         os.rename(old_tl_path, new_tl_path)
                         print(f"Renamed (Workflow 3): {old_tl_name} -> {new_base_name}_timeline.json")

        # 5.5. Polish pass (Sprint 3: jump cuts / punch zoom / music / branding)
        # Runs AFTER editing (final/) and BEFORE subtitle burning so the burned
        # subs land on the polished video and get re-timed automatically.
        if args.polish == "on":
            print(i18n("Running polish pass (stages: {})...").format(args.polish_stages))
            emit_progress("polish", 87, "تحسين المونتاج")
            try:
                polish_reports = polish.polish_project(
                    project_folder,
                    enable=[s for s in args.polish_stages.split(",") if s.strip()],
                    keywords=args.zoom_keywords,
                    music_path=args.music,
                    music_volume=args.music_volume,
                    logo_path=args.logo,
                    intro=args.intro,
                    outro=args.outro,
                    zoom_keywords=args.zoom_keywords,
                    punch_zoom_amount=1.18,
                )
                ok_n = sum(1 for r in polish_reports if r.get("ok"))
                print(i18n("Polish: {}/{} clips enhanced").format(ok_n, len(polish_reports)))
            except Exception as e:
                print(i18n("Polish pass failed (continuing with unpolished clips): {}").format(e))

        # 6. Subtitles
        burn_subtitles_option = True 
        if burn_subtitles_option:
            print(i18n("Processing subtitles..."))
            emit_progress("subtitles", 90, "Rendering subtitles")
            # transcribe_cuts removido: JSON de legenda já é gerado no corte
            # transcribe_cuts.transcribe(project_folder=project_folder)
            
            # --- Translation Integration ---
            if args.translate_target and args.translate_target.lower() != "none":
                 print(i18n("Translating subtitles to: {}").format(args.translate_target))
                 import asyncio
                 try:
                    asyncio.run(translate_json.translate_project_subs(project_folder, args.translate_target))
                 except Exception as e:
                    print(i18n("Translation failed: {}").format(e))
            # -------------------------------

            sub_config = get_subtitle_config(args.subtitle_config)
            
            def _run_subtitles():
                adjust_subtitles.adjust(project_folder=project_folder, **sub_config)
                burn_subtitles.burn(project_folder=project_folder, prefer_hardware_acceleration=args.prefer_hardware_acceleration)

            # Passa o dicionário desempacotado como argumentos, mais o project_folder
            try:
                emit_progress("subtitles", 95, "Rendering subtitles")
                tracker.run("subtitles", _run_subtitles)
            except FileNotFoundError as fnf_error:
                print(i18n("\n[ERROR] Subtitle processing failed: {}").format(str(fnf_error)))
                print(i18n("Tip: If you are using Workflow 3 (Subtitles Only), ensure the 'subs' folder exists and contains valid JSON files."))
                sys.exit(1)
            except Exception as e:
                print(i18n("\n[ERROR] Unexpected error during subtitle processing: {}").format(str(e)))
                raise e
        else:
            print(i18n("Subtitle burning skipped."))

        # 6.5. Risk Scorecard — per-clip compliance report (reused content /
        #      monetization / visual) + optional publish gate
        if args.risk_scorecard == "on" and viral_segments and "segments" in viral_segments:
            try:
                print(i18n("Running risk scorecard (per-clip compliance report)..."))
                report = tracker.run(
                    "scorecard",
                    risk_scorecard.analyze_project,
                    project_folder,
                    viral_segments=viral_segments,
                    i18n=i18n,
                    auto_download_visual=args.auto_download_visual,
                )
                if report is None:
                    report = risk_scorecard.analyze_project(
                        project_folder, viral_segments=viral_segments, i18n=i18n)
                blocked = report.get("blocked", [])
                if blocked:
                    print(i18n("[risk] ⛔ BLOCKED FOR PUBLISH: {} clip(s) — remove or re-edit before uploading. Details in risk_scorecard.json / publish_blocklist.json").format(len(blocked)))
                    if args.risk_gate == "block":
                        print(i18n("[risk] gate mode 'block' — stopping the run because {} clip(s) failed the compliance gate.").format(len(blocked)))
                        sys.exit(1)
            except Exception as e:
                print(i18n("Risk scorecard failed (skipped): {}").format(e))
        # 6.55. Music fingerprint check (Roadmap 2.3) — Chromaprint/AcoustID.
        #       Runs after rendering, before the upload gate, so that
        #       music_fingerprint.json is available to gate_upload().
        if args.music_check != "off" and viral_segments and "segments" in viral_segments:
            try:
                from scripts import music_fingerprint
                want_run = args.music_check == "on" or music_fingerprint.fpcalc_available()
                if want_run:
                    print(i18n("Running music fingerprint check (Chromaprint/AcoustID)..."))
                    local_db = None
                    if args.music_local_db:
                        if os.path.isdir(args.music_local_db):
                            cache = os.path.join(os.path.expanduser("~"),
                                                 ".viralcutter", "music_db.json")
                            local_db = music_fingerprint.build_local_db(
                                args.music_local_db, cache_path=cache)
                        else:
                            local_db = music_fingerprint.load_local_db(args.music_local_db)
                    report = tracker.run(
                        "music_check",
                        music_fingerprint.analyze_project,
                        project_folder,
                        acoustid_key=args.acoustid_key,
                        local_db=local_db,
                        gate=args.music_gate,
                    )
                    if report is None:
                        report = music_fingerprint.analyze_project(
                            project_folder, acoustid_key=args.acoustid_key,
                            local_db=local_db, gate=args.music_gate)
                    s = report.get("summary", {})
                    print(i18n("[music] {} clip(s) checked, {} matched, {} no_fpcalc, {} errors").format(
                        s.get("checked", 0), s.get("matched", 0),
                        s.get("no_fpcalc", 0), s.get("errors", 0)))
                    for clip in report.get("clips", []):
                        if clip.get("verdict") in ("acoustid_match", "local_match"):
                            print(i18n("[music] 🎵⚠️ #{} {} — {}").format(
                                clip.get("index", "?"),
                                os.path.basename(clip.get("video", "")),
                                clip.get("suggestion", "")))
                    if s.get("matched", 0) and args.music_gate == "block":
                        print(i18n("[music] gate mode 'block' — stopping because {} clip(s) matched known audio.").format(s["matched"]))
                        sys.exit(1)
                elif args.music_check == "auto":
                    print(i18n("Music check skipped (auto): Chromaprint not installed — see docs to enable."))
            except Exception as e:
                print(i18n("Music fingerprint check failed (skipped): {}").format(e))


        # 6.6. Metadata compliance gate (Roadmap 2.4) + upload-gate audit (2.2).
        #      Merges a `metadata` axis into the scorecard, then audits every
        #      clip through upload_gate (publish_blocklist + safety + metadata).
        if args.metadata_gate != "off" and viral_segments and "segments" in viral_segments:
            try:
                print(i18n("Running metadata compliance + upload gate audit..."))
                segs = viral_segments.get("segments", [])
                scorecard_path = os.path.join(project_folder, risk_scorecard.SCORECARD_FILENAME)
                sc = load_json_file(scorecard_path, default={})
                meta_blocked = []
                for entry in sc.get("segments", []):
                    idx = entry.get("index")
                    if idx is None or idx >= len(segs):
                        continue
                    seg = segs[idx]
                    axis = metadata_compliance.metadata_axis(
                        seg.get("title", ""), seg.get("caption", ""),
                        seg.get("hashtags", []))
                    entry["axes"]["metadata"] = axis
                    if not axis["ok"]:
                        meta_blocked.append(entry)
                try:
                    with open(scorecard_path, "w", encoding="utf-8") as f:
                        json.dump(sc, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    debug("Could not save metadata axis into scorecard: {}".format(e))

                allowed, blocked = upload_gate.audit_project(project_folder)
                total_blocked = len(blocked) + len(meta_blocked)
                if total_blocked:
                    print(i18n("[gate] ⛔ {} clip(s) refused for publish by the safety gate").format(total_blocked))
                    for entry in meta_blocked:
                        axis = entry["axes"]["metadata"]
                        print(i18n("[gate]   ✗ #{} '{}' — {}").format(
                            entry.get("index"), entry.get("title"),
                            metadata_compliance.summarize_metadata(axis)))
                    if args.metadata_gate == "block":
                        print(i18n("[gate] gate mode 'block' — stopping the run."))
                        sys.exit(1)
                else:
                    print(i18n("[gate] ✔ all clips pass the publish gate"))
            except Exception as e:
                print(i18n("Metadata gate failed (skipped): {}").format(e))

        # Organização Final (Opcional, pois agora já está tudo em project_folder)
        # organize_output.organize(project_folder=project_folder)
        
        # --- Save Processing Configuration ---
        try:
            # Determine AI Model used
            used_ai_model = args.ai_model_name
            if not used_ai_model and ai_backend != "manual":
                if ai_backend == "gemini":
                    used_ai_model = api_config.get("gemini", {}).get("model", "default")
                elif ai_backend == "g4f":
                    used_ai_model = api_config.get("g4f", {}).get("model", "default")
            
            # Ensure sub_config exists
            current_sub_config = sub_config if 'sub_config' in locals() else get_subtitle_config(args.subtitle_config)
            
            final_config = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "workflow": workflow_choice,
                "ai_config": {
                    "backend": ai_backend,
                    "model_name": used_ai_model,
                    "viral_mode": viral_mode,
                    "themes": themes,
                    "num_segments": num_segments,
                    "chunk_size": args.chunk_size
                },
                "face_config": {
                    "model": face_model,
                    "mode": face_mode,
                    "detect_interval": args.face_detect_interval,
                    "filter_threshold": args.face_filter_threshold,
                    "two_face_threshold": args.face_two_threshold,
                    "confidence_threshold": args.face_confidence_threshold,
                    "dead_zone": args.face_dead_zone,
                    "focus_active_speaker": args.focus_active_speaker,
                    "active_speaker_mar": args.active_speaker_mar,
                    "active_speaker_score_diff": args.active_speaker_score_diff,
                    "include_motion": args.include_motion
                },
                "video_config": {
                    "min_duration": args.min_duration,
                    "max_duration": args.max_duration,
                    "whisper_model": args.model,
                    "platform_template": args.platform
                },
                "subtitle_config": current_sub_config
            }

            config_save_path = os.path.join(project_folder, "process_config.json")
            with open(config_save_path, "w", encoding="utf-8") as f:
                json.dump(final_config, f, indent=4, ensure_ascii=False)
            print(i18n("Configuration saved to: {}").format(config_save_path))
            
        except Exception as e:
            print(i18n("Error saving configuration JSON: {}").format(e))
        # -------------------------------------

        emit_progress("done", 100, "Completed")
        try:
            checkpoint.mark_done(project_folder, "done")
        except Exception:
            pass
        cleanup_temp_files()
        main._retried = False
        print(i18n("Process completed! Check your results in: {}").format(project_folder))

    except Exception as e:
        print(i18n("\nAn error occurred: {}").format(str(e)))
        # Privacy-respecting crash report (Roadmap 4.5) — local always, sent
        # only when the user opts in via VIRALCUTTER_CRASH_REPORT=1.
        try:
            crash_report.report("pipeline", e,
                                log_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "crash_report.log"))
        except Exception:
            pass
        import traceback
        traceback.print_exc()
        cleanup_temp_files()
        if not main._retried:
            main._retried = True
            print(i18n("Retrying after failure..."))
            time.sleep(2)
            return main()
        main._retried = False
        sys.exit(1)

if __name__ == "__main__":
    main()
