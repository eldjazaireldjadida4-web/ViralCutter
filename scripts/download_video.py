import os
import re
import yt_dlp
import sys
from i18n.i18n import I18nAuto
i18n = I18nAuto()

_COOKIES_HINT = (
    "\n"
    "  Private / age-restricted video? Authenticate yt-dlp and retry:\n"
    "    python main_improved.py --url \"...\" --cookies-from-browser chrome\n"
    "  (or export cookies with a browser extension: yt-dlp.github.io/yt-dlp FAQ)\n"
    "  Docs: https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp")


class AuthNeededError(RuntimeError):
    """A private / age-restricted video needs authenticated cookies.

    Raised (instead of SystemExit) so the CLI can offer an interactive retry
    with the user's browser cookies; anything else exits cleanly.
    """


def _friendly_download_error(e, url=""):
    """Map common yt-dlp failures to clear, actionable messages."""
    msg = str(e)
    low = msg.lower()
    if "private video" in low or "sign in" in low or "private" in low and "video" in low:
        return (i18n("\n[ERROR] This YouTube video is PRIVATE — it can only be downloaded "
                     "by accounts granted access.\nSolutions:") + _COOKIES_HINT)
    if "age" in low and ("restrict" in low or "confirm" in low):
        return (i18n("\n[ERROR] This video is age-restricted. Authenticate with "
                     "--cookies-from-browser to download it.") + _COOKIES_HINT)
    if "video unavailable" in low or "not available" in low:
        return i18n("\n[ERROR] This video is unavailable (removed, geo-blocked or "
                    "deleted). Check the link on your browser.")
    if "copyright" in low or "removed" in low:
        return i18n("\n[ERROR] This video was removed (copyright or creator takedown).")
    if "is not a valid url" in low:
        return i18n("\n[ERROR] The link is not a valid YouTube URL.")
    if "unable to download video subtitles" in low or "429" in low:
        return None  # handled by the retry-without-subs branch
    if "403" in msg or "forbidden" in low:
        return (i18n("\n[ERROR] YouTube blocked the download (HTTP 403).\n"
                     "Fixes (try in order):\n"
                     "  1) Update yt-dlp:  uv pip install -U yt-dlp\n"
                     "  2) Use browser cookies: --cookies-from-browser chrome (or the 🔒 list in the WebUI)\n"
                     "  3) Retry in a few minutes (YouTube rate-limits aggressively)"))
    return i18n("\n[ERROR] YouTube download failed: {}").format(e)


def _print_friendly_and_exit(e, url=""):
    msg = _friendly_download_error(e, url)
    if msg:
        try:
            print(msg)
        except UnicodeEncodeError:
            print(msg.encode('ascii', 'replace').decode('ascii'))
    low = str(e).lower()
    auth_cases = ("private video" in low or "sign in" in low
                  or ("age" in low and "restrict" in low))
    if auth_cases:
        raise AuthNeededError(msg)   # let the CLI offer a cookies retry
    raise SystemExit(1)


def sanitize_filename(name):
    """Safe folder name for any script (incl. Arabic) — v6.5.

    The old cp1252/ascii fallback erased non-Latin scripts entirely (Arabic
    titles became "" → every Arabic-titled project collapsed into VIRALS/ and
    overwrote input.mp4). NTFS/FAT32 handle Unicode fine; only strip the
    reserved characters, control chars and emojis (keep letters incl. Arabic,
    digits, spaces, and safe punctuation).
    """
    cleaned = re.sub(r'[\\/*?:"<>|]', "", str(name))
    # keep unicode word chars (Arabic/Latin/CJK), spaces, and safe punctuation
    cleaned = re.sub(r"[^\w\s\-\.\(\)\[\]]", "", cleaned, flags=re.UNICODE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned[:120] or "Unknown_Video"


def progress_hook(d):
    if d['status'] == 'downloading':
        try:
            p = d.get('_percent_str', '').replace('%', '')
            print(f"[download] {p}% - {d.get('_eta_str', 'N/A')} remaining", flush=True)
        except:
            pass
    elif d['status'] == 'finished':
        print(f"[download] Download concluído: {d['filename']}", flush=True)


def download(url, base_root="VIRALS", download_subs=True, quality="best",
             cookies_from_browser=None, cookies_file=None):
    # 1. Extrair informações do vídeo para pegar o título
    print(i18n("Extracting video information..."))
    title = None

    # Título: usa cookies apenas quando o usuário pediu explicitamente
    # (--cookies-from-browser / --cookies). Forçar chrome antes causava
    # "Could not copy Chrome cookie database" em Windows (yt-dlp#7271).
    info_opts = {'quiet': True, 'no_warnings': True}
    if cookies_from_browser:
        info_opts['cookiesfrombrowser'] = (cookies_from_browser,)
    if cookies_file:
        info_opts['cookiefile'] = cookies_file
    try:
        with yt_dlp.YoutubeDL(info_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get('title')
    except Exception as e:
        try:
            print(i18n("Error getting video info: {}").format(e))
        except UnicodeEncodeError:
            print(i18n("Error getting video info: [Encoding Error in Message]"))

    # Fallback final
    if title:
        safe_title = sanitize_filename(title)
        try:
            print(i18n("Detected title: {}").format(title))
        except UnicodeEncodeError:
            # Fallback for Windows consoles that choke on Emojis
            clean_title = title.encode('ascii', 'replace').decode('ascii')
            print(i18n("Detected title: {}").format(clean_title))
    else:
        print(i18n("WARNING: Title could not be obtained. Using 'Unknown_Video'."))
        safe_title = i18n("Unknown_Video")

    # 2. Criar estrutura de pastas
    project_folder = os.path.join(base_root, safe_title)
    os.makedirs(project_folder, exist_ok=True)

    # Caminho final do vídeo
    output_filename = 'input'
    output_path_base = os.path.join(project_folder, output_filename)
    final_video_path = f"{output_path_base}.mp4"

    # Verificação inteligente
    if os.path.exists(final_video_path):
        if os.path.getsize(final_video_path) > 1024:
            try:
                print(i18n("Video already exists at: {}").format(final_video_path))
            except UnicodeEncodeError:
                print(i18n("Video already exists at: {}").format(final_video_path.encode('ascii', 'replace').decode('ascii')))
            print(i18n("Skipping download and reusing local file."))
            return final_video_path, project_folder
        else:
            print(i18n("Existing file found but seems corrupted/empty. Downloading again..."))
            try:
                os.remove(final_video_path)
            except:
                pass

    # Limpeza de temp
    temp_path = f"{output_path_base}.temp.mp4"
    if os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except:
            pass

    # Mapeamento de Qualidade
    quality_map = {
        "best": 'bestvideo+bestaudio/best',
        "1080p": 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
        "720p": 'bestvideo[height<=720]+bestaudio/best[height<=720]',
        "480p": 'bestvideo[height<=480]+bestaudio/best[height<=480]'
    }
    selected_format = quality_map.get(quality, 'bestvideo+bestaudio/best')
    print(i18n("Configuring download quality: {} -> {}").format(quality, selected_format))

    ydl_opts = {
        'format': selected_format,
        'overwrites': True,
        'outtmpl': output_path_base,
        'postprocessor_args': [
            '-movflags', 'faststart'
        ],
        'merge_output_format': 'mp4',
        'progress_hooks': [progress_hook],
        # Opções de Legenda
        'writesubtitles': download_subs,
        'writeautomaticsub': download_subs,
        'subtitleslangs': ['pt.*', 'en.*', 'sp.*'],  # Prioritize generic PT, EN, SP
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        },
        'skip_download': False,
        'quiet': False,
        'no_warnings': False,
        'force_ipv4': True,
        # Authentication for private / age-restricted videos (v6.2)
        'cookiesfrombrowser': (cookies_from_browser,) if cookies_from_browser else None,
        'cookiefile': cookies_file or None,
    }

    if download_subs:
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegSubtitlesConvertor',
            'format': 'srt',
        }]

    try:
        print(i18n("Downloading video to: {}...").format(project_folder))
    except UnicodeEncodeError:
        print(i18n("Downloading video to: {}...").format(project_folder.encode('ascii', 'replace').decode('ascii')))

    def _run_download(opts):
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

    # Tentativa 1: Com configuração original
    try:
        _run_download(ydl_opts)
    except yt_dlp.utils.DownloadError as e:
        error_str = str(e)
        # HTTP 403 (Forbidden) → retry once with alternative YouTube player
        # clients (the classic fix for bot-detection blocks).
        if ("403" in error_str or "Forbidden" in error_str) and "extractor_args" not in ydl_opts:
            print(i18n("\nWarning: YouTube returned 403 — retrying with an alternative player client..."))
            retry_opts = dict(ydl_opts)
            retry_opts['extractor_args'] = {'youtube': {'player_client': ['android', 'tv', 'web_safari']}}
            try:
                _run_download(retry_opts)
                ydl_opts = retry_opts  # so the subtitle post-processor below sees success
            except yt_dlp.utils.DownloadError as e2:
                e = e2
            except Exception as e2:
                e = e2
        error_str = str(e)
        if "No address associated with hostname" in error_str or "Failed to resolve" in error_str:
            print(i18n("\n[CRITICAL ERROR] Connection Failure: Could not access YouTube."))
            print(i18n("Check your internet connection or if there is any DNS block."))
            print(i18n("Details: {}").format(e))
            sys.exit(1)

        elif download_subs and ("Unable to download video subtitles" in error_str or "429" in error_str):
            print(i18n("\nWarning: Error downloading subtitles ({}).").format(e))
            print(i18n("Retrying ONLY the video (without subtitles)..."))

            ydl_opts['writesubtitles'] = False
            ydl_opts['writeautomaticsub'] = False
            ydl_opts['postprocessors'] = [p for p in ydl_opts.get('postprocessors', []) if 'Subtitle' not in p.get('key', '')]

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
            except Exception as e2:
                print(i18n("Fatal error on second attempt: {}").format(e2))
                raise
        elif "is not a valid URL" in error_str:
            print(i18n("Error: the entered link is not valid."))
            _print_friendly_and_exit(e, url)
        else:
            # Friendly, actionable message for private/age-restricted/unavailable
            # videos (v6.2) — clean exit instead of a raw traceback.
            _print_friendly_and_exit(e, url)
    except Exception as e:
        print(i18n("Unexpected error: {}").format(e))
        raise

    # Safety net: if the video file still does not exist after all attempts,
    # fail loudly instead of returning a bogus path (v6.3b).
    if not os.path.exists(final_video_path) or os.path.getsize(final_video_path) < 1024:
        print(i18n("\n[ERROR] Download finished but the video file is missing/empty: {}")
              .format(final_video_path))
        raise SystemExit(1)

    # RENOMEAR LEGENDA PARA PADRÃO (input.vtt ou input.srt)
    # Se for VTT, converte para SRT para garantir compatibilidade.
    try:
        import glob
        # Pega a primeira que encontrar
        potential_subs = glob.glob(os.path.join(project_folder, "input.*.vtt")) + glob.glob(os.path.join(project_folder, "input.*.srt"))

        if potential_subs:
            best_sub = potential_subs[0]
            ext = os.path.splitext(best_sub)[1]
            new_name = os.path.join(project_folder, "input.srt")  # Vamos padronizar tudo para .srt

            if ext.lower() == '.vtt':
                try:
                    print(i18n("Formatting complex VTT subtitle ({}) to clean SRT...").format(os.path.basename(best_sub)))
                except UnicodeEncodeError:
                    print(i18n("Formatting complex VTT subtitle ({}) to clean SRT...").format(os.path.basename(best_sub).encode('ascii', 'replace').decode('ascii')))
                try:
                    with open(best_sub, 'r', encoding='utf-8') as f:
                        lines = f.readlines()

                    srt_content = []
                    counter = 1

                    seen_texts = set()
                    last_text = ""

                    for line in lines:
                        clean_line = line.strip()
                        # Ignora Headers e Metadados do VTT/Youtube
                        if clean_line.startswith("WEBVTT") or \
                           clean_line.startswith("X-TIMESTAMP") or \
                           clean_line.startswith("NOTE") or \
                           clean_line.startswith("Kind:") or \
                           clean_line.startswith("Language:"):
                            continue

                        if "-->" in clean_line:
                            # Parse Timestamp
                            parts = clean_line.split("-->")
                            start = parts[0].strip()
                            # Remove tags de posicionamento "align:start position:0%"
                            end = parts[1].strip().split(' ')[0]

                            def fix_time(t):
                                t = t.replace('.', ',')
                                if t.count(':') == 1:
                                    t = "00:" + t
                                return t

                            current_start = fix_time(start)
                            current_end = fix_time(end)

                        elif clean_line:
                            # Texto: remover tags complexas <00:00:00.560><c> etc
                            text = re.sub(r'<[^>]+>', '', clean_line).strip()

                            if not text:
                                continue

                            # Pega apenas a ULTIMA linha se tiver quebras
                            lines_in_text = text.split('\n')
                            final_line = lines_in_text[-1].strip()

                            if not final_line:
                                continue

                            # Filtro de duplicidade consecutivo
                            if final_line == last_text:
                                continue

                            srt_content.append(f"{counter}\n")
                            srt_content.append(f"{current_start} --> {current_end}\n")
                            srt_content.append(f"{final_line}\n\n")

                            last_text = final_line
                            counter += 1

                    with open(new_name, 'w', encoding='utf-8') as f_out:
                        f_out.writelines(srt_content)

                    try:
                        print(i18n("Subtitle converted and cleaned: {}").format(new_name))
                    except UnicodeEncodeError:
                        print(i18n("Subtitle converted and cleaned: {}").format(new_name.encode('ascii', 'replace').decode('ascii')))
                    try:
                        os.remove(best_sub)
                    except:
                        pass

                except Exception as e_conv:
                    print(i18n("Failed to convert VTT: {}. Keeping original.").format(e_conv))
                    # Fallback: rename apenas
                    new_name_fallback = os.path.join(project_folder, "input.vtt")
                    if os.path.exists(new_name_fallback) and new_name_fallback != best_sub:
                        try:
                            os.remove(new_name_fallback)
                        except:
                            pass
                    os.rename(best_sub, new_name_fallback)

            else:
                # Já é SRT, só renomeia
                if os.path.exists(new_name) and new_name != best_sub:
                    try:
                        os.remove(new_name)
                    except:
                        pass
                os.rename(best_sub, new_name)
                try:
                    print(i18n("SRT subtitle renamed to: {}").format(new_name))
                except UnicodeEncodeError:
                    print(i18n("SRT subtitle renamed to: {}").format(new_name.encode('ascii', 'replace').decode('ascii')))

            # Limpa sobras
            for extra in potential_subs[1:]:
                try:
                    os.remove(extra)
                except:
                    pass

    except Exception as e_ren:
        print(i18n("Error processing subtitles: {}").format(e_ren))

    # Absolute last resort: never return a missing/empty file (v6.3c).
    if not os.path.exists(final_video_path) or os.path.getsize(final_video_path) < 1024:
        print(i18n("\n[ERROR] Download finished but the video file is missing/empty: {}")
              .format(final_video_path))
        raise SystemExit(1)

    return final_video_path, project_folder
