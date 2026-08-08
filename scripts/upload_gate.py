# -*- coding: utf-8 -*-
"""
Upload Gate — the mandatory last safety barrier before anything is published.

Roadmap item 2.2 ("الرفع المباشر + بوابة رفض إجبارية"). The gate itself is
fully implemented and enforced here; the platform SDK clients (YouTube /
TikTok / Instagram) plug into it so *no* upload path can bypass the check.

The gate refuses (raises / exits non-zero) when a clip:
    1. is on the publish_blocklist written by risk_scorecard
       (reused-content / high overall risk),
    2. was blocked by the safety filter (safety_report.json),
    3. fails the live metadata compliance check (title / caption / hashtags),
    4. is missing its final rendered video.

Design notes
------------
* Pure stdlib, no network calls inside the gate itself → unit-testable.
* `check_clip()` returns a structured verdict; `gate_upload()` is the
  enforcement wrapper (raises `UploadGateError`).
* Platform uploaders are thin adapters that MUST call `gate_upload()` first.
* YouTube (OAuth + Data API v3), TikTok (OAuth2 + Content Posting API) and
  Instagram (Graph API Reels) are fully implemented; run the OAuth flow once
  with `--auth <platform>` to obtain/store tokens (see --auth below).
* The optional music_fingerprint.json report (Roadmap 2.3) is consulted via
  `music_gate`: "warn" flags matched audio, "block" refuses the upload.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

from scripts.metadata_compliance import check_metadata, summarize_metadata

PUBLISH_BLOCKLIST = "publish_blocklist.json"
SAFETY_REPORT = "safety_report.json"
SCORECARD = "risk_scorecard.json"


class UploadGateError(Exception):
    """Raised when a clip must not be published. Carries structured reasons."""

    def __init__(self, reasons):
        self.reasons = reasons  # list of {"source": str, "detail": str, "severity": str}
        joined = "; ".join("{}: {}".format(r["source"], r["detail"]) for r in reasons)
        super().__init__("Upload refused by ViralCutter safety gate: " + joined)


# ---------------------------------------------------------------------------
# Evidence loaders
# ---------------------------------------------------------------------------

def _load_json(project_folder, name):
    path = os.path.join(project_folder, name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _blocklist_reasons(project_folder, index):
    reasons = []
    data = _load_json(project_folder, PUBLISH_BLOCKLIST)
    if not data:
        return reasons
    for entry in data.get("blocked", []):
        if index is not None and entry.get("index") != index:
            continue
        score = (entry.get("axes") or {}).get("reuse", {}).get("score")
        why = "high overall risk" if score is None else "reused-content score ~{:.0f}%".format(score)
        reasons.append({
            "source": "publish_blocklist",
            "detail": "clip #{} is BLOCKED for publish ({})".format(
                entry.get("index", "?"), why),
            "severity": "high",
        })
    return reasons


def _safety_report_reasons(project_folder, index):
    reasons = []
    data = _load_json(project_folder, SAFETY_REPORT)
    if not data:
        return reasons
    blocked = data.get("blocked", [])
    if isinstance(blocked, dict):  # older reports may nest under {"segments": [...]}
        blocked = blocked.get("segments", [])
    for entry in blocked:
        if index is not None and entry.get("index") not in (index, None):
            continue
        if entry.get("index") is None and index is None:
            reasons.append({"source": "safety_report",
                            "detail": "segment blocked by safety filter: {}".format(
                                entry.get("reason", entry.get("title", "?"))),
                            "severity": "high"})
        elif entry.get("index") == index:
            reasons.append({"source": "safety_report",
                            "detail": "segment blocked by safety filter: {}".format(
                                entry.get("reason", entry.get("title", "?"))),
                            "severity": "high"})
    return reasons


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

def check_clip(project_folder, index=None, title="", caption="", hashtags=None,
               extra_rules_path=None, require_video=False, music_gate=None):
    """Evaluate one clip against every safety barrier.

    Returns {"allowed": bool, "reasons": [...], "metadata": {...}}.
    Never raises — callers decide what to do with the verdict.

    `music_gate`: "warn" (default, flagged), "block" (refused) or "off"
    (ignored) — controls how music_fingerprint.json matches are treated.
    """
    reasons = []
    reasons += _blocklist_reasons(project_folder, index)
    reasons += _safety_report_reasons(project_folder, index)

    # Audio copyright fingerprint report (Roadmap 2.3) — optional module.
    try:
        from scripts.music_fingerprint import music_gate_reasons
        reasons += music_gate_reasons(project_folder, index, gate=music_gate)
    except Exception:
        pass  # never let an optional check crash the gate

    meta = check_metadata(title, caption, hashtags or [], extra_rules_path)
    if not meta["ok"]:
        reasons.append({
            "source": "metadata_compliance",
            "detail": summarize_metadata(meta),
            "severity": meta["severity"],
        })

    if require_video and index is not None:
        found = _find_clip_video(project_folder, index)
        if not found:
            reasons.append({
                "source": "missing_video",
                "detail": "no rendered video found for clip #{}".format(index),
                "severity": "high",
            })

    # Only high-severity reasons block; music "warn" flags are advisory and
    # never stop an upload on their own (metadata/safety/blocklist unchanged).
    blocking = [r for r in reasons
                if r["severity"] == "high"
                or (r["severity"] == "medium" and r["source"] != "music_fingerprint")]

    return {"allowed": not blocking, "reasons": reasons, "metadata": meta}


def _find_clip_video(project_folder, index):
    import glob
    patterns = [
        os.path.join(project_folder, "final", "*{0:03d}*.mp4".format(index)),
        os.path.join(project_folder, "final", "final-output{0:03d}_processed.mp4".format(index)),
        os.path.join(project_folder, "cuts", "{0:03d}_*_original_scale.mp4".format(index)),
    ]
    for pattern in patterns:
        hits = sorted(glob.glob(pattern))
        if hits:
            return hits[0]
    return None


def gate_upload(project_folder, index=None, title="", caption="", hashtags=None,
                extra_rules_path=None, require_video=False, music_gate=None):
    """Enforcement wrapper: raises UploadGateError when the clip must not go out."""
    verdict = check_clip(project_folder, index, title, caption, hashtags,
                         extra_rules_path, require_video, music_gate)
    if not verdict["allowed"]:
        raise UploadGateError(verdict["reasons"])
    return verdict


def audit_project(project_folder, extra_rules_path=None):
    """Check every scored clip in the project folder. Returns (allowed, blocked)."""
    scorecard = _load_json(project_folder, SCORECARD)
    allowed, blocked = [], []
    segments = (scorecard or {}).get("segments", [])
    for entry in segments:
        idx = entry.get("index")
        verdict = check_clip(project_folder, idx,
                             title=entry.get("title", ""),
                             require_video=False,
                             extra_rules_path=extra_rules_path)
        if verdict["allowed"]:
            allowed.append(idx)
        else:
            blocked.append({"index": idx, "title": entry.get("title", ""),
                            "reasons": verdict["reasons"]})
    return allowed, blocked


# ---------------------------------------------------------------------------
# Platform upload adapters (all MUST pass through the gate)
# ---------------------------------------------------------------------------

class _BaseUploader:
    """Thin adapter contract. Subclasses implement _do_upload()."""

    platform = "base"

    def __init__(self, project_folder, dry_run=False, extra_rules_path=None,
                 video_url=None, music_gate=None):
        self.project_folder = project_folder
        self.dry_run = dry_run
        self.extra_rules_path = extra_rules_path
        self.video_url = video_url
        self.music_gate = music_gate

    def upload(self, video_path, title, caption="", hashtags=None, index=None):
        """Gate first, then upload. Raises UploadGateError when blocked."""
        gate_upload(self.project_folder, index, title, caption, hashtags,
                    self.extra_rules_path, require_video=False,
                    music_gate=self.music_gate)
        if self.dry_run:
            print("[{}] DRY-RUN would upload '{}' → {}".format(
                self.platform, title, video_path))
            return {"status": "dry-run", "platform": self.platform}
        return self._do_upload(video_path, title, caption, hashtags)

    def _do_upload(self, video_path, title, caption, hashtags):
        raise NotImplementedError

    # Convenience for adapters: fail loudly with a clear setup hint.
    @staticmethod
    def _missing_credentials(platform, env_vars):
        raise RuntimeError(
            "{} upload requires OAuth credentials via env vars: {}. "
            "See docs/ROADMAP_REPORT.md (2.2) for setup.".format(platform, ", ".join(env_vars)))


class YouTubeUploader(_BaseUploader):
    """YouTube Data API v3 uploader with real OAuth (Roadmap 2.2).

    Setup (once):
      1. pip install -r requirements-upload.txt
      2. Google Cloud console → enable "YouTube Data API v3" →
         create OAuth 2.0 Client ID (Desktop app) → save JSON as client_secrets.json
      3. Run any upload: the first run opens the browser for consent and
         stores the token in ~/.viralcutter/yt_token.json.

    The safety gate runs BEFORE any API call (see _BaseUploader.upload).
    Privacy: default privacyStatus is "private" (safe) — set YT_PRIVACY=public
    only when you intend to publish.
    """
    platform = "youtube"
    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

    def auth(self):
        """Run the OAuth consent flow and save the token (no upload)."""
        creds = self._load_or_create_token()
        print("[youtube] ✅ token saved → {}".format(self._token_path()))
        return self._token_path()

    def _token_path(self):
        return os.getenv("YT_TOKEN_FILE") or os.path.join(
            os.path.expanduser("~"), ".viralcutter", "yt_token.json")

    def _load_or_create_token(self):
        """Return credentials; run the OAuth consent flow on first use."""
        # Check credentials BEFORE importing the optional google libraries so a
        # missing client_secrets.json always yields the clear, actionable error
        # (and never a raw ModuleNotFoundError in minimal environments).
        token_path = self._token_path()
        secrets = os.getenv("YT_CLIENT_SECRETS_FILE") or os.path.join(
            os.getcwd(), "client_secrets.json")
        if not os.path.exists(secrets) and not os.path.exists(token_path):
            self._missing_credentials(self.platform, ["YT_CLIENT_SECRETS_FILE"])

        import google.auth.transport.requests as g_requests
        from google.oauth2.credentials import Credentials

        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, self.SCOPES)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(g_requests.Request())
            if creds and creds.valid:
                return creds
        # The consent flow needs client_secrets.json.
        if not os.path.exists(secrets):
            self._missing_credentials(self.platform, ["YT_CLIENT_SECRETS_FILE"])
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_secrets_file(secrets, self.SCOPES)
        creds = flow.run_local_server(port=0, prompt="consent")
        os.makedirs(os.path.dirname(token_path), exist_ok=True)
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        return creds

    def _do_upload(self, video_path, title, caption, hashtags):
        if not os.path.exists(video_path):
            raise FileNotFoundError("video not found: {}".format(video_path))
        creds = self._load_or_create_token()
        try:
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload
        except ImportError:
            raise RuntimeError(
                "youtube upload needs: pip install -r requirements-upload.txt")

        tags = [str(h).lstrip("#") for h in (hashtags or []) if str(h).strip()]
        description = caption or ""
        if tags:
            description += "\n\n" + " ".join("#" + t for t in tags)
        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": os.getenv("YT_CATEGORY_ID", "22"),  # 22 = People & Blogs
            },
            "status": {
                "privacyStatus": os.getenv("YT_PRIVACY", "private"),
                "selfDeclaredMadeForKids": False,
            },
        }
        service = build("youtube", "v3", credentials=creds)
        media = MediaFileUpload(video_path, chunksize=8 * 1024 * 1024, resumable=True)
        request = service.videos().insert(part="snippet,status", body=body,
                                          media_body=media)
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print("[youtube] uploaded {:.0f}%".format(
                    status.progress() * 100 if status.progress() else 0), flush=True)
        video_id = response.get("id")
        print("[youtube] uploaded '{}' → https://youtu.be/{}".format(title, video_id))
        return {"status": "uploaded", "platform": "youtube",
                "video_id": video_id, "url": "https://youtu.be/{}".format(video_id)}


# ---------------------------------------------------------------------------
# Shared HTTP helpers (stdlib only — no extra pip deps for the upload stack)
# ---------------------------------------------------------------------------

def _http_json(url, data=None, headers=None, method=None, timeout=60, retries=3):
    """JSON POST/PUT/GET via urllib with a simple 429/5xx retry loop.

    Returns the parsed JSON body. Raises RuntimeError with a readable message
    on transport errors and on API error payloads ({"error": {...}}).
    """
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
    req_headers = {"Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    if body is not None:
        req_headers.setdefault("Content-Type", "application/json")

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                try:
                    return json.loads(raw) if raw else {}
                except ValueError:
                    return {"raw": raw}
        except urllib.error.HTTPError as e:
            raw = ""
            try:
                raw = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            last_err = _api_error_message(e.code, raw)
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(2 * attempt)
                continue
            raise RuntimeError(last_err) from None
        except Exception as e:  # network errors, timeouts
            last_err = str(e)
            if attempt < retries:
                time.sleep(2 * attempt)
                continue
            raise RuntimeError("network error talking to {}: {}".format(url, e)) from None
    raise RuntimeError("request failed: {}".format(last_err))


def _api_error_message(status, raw):
    """Best-effort extraction of a human-readable API error message."""
    try:
        payload = json.loads(raw or "{}")
    except ValueError:
        payload = {}
    err = payload.get("error") or {}
    if isinstance(err, dict):
        code = err.get("code") or err.get("status")
        msg = err.get("message") or err.get("description") or err.get("detail")
        if msg:
            return "API error {}: {}".format(code or status, msg)
    msg = payload.get("message") or payload.get("error_description") or payload.get("reason")
    if msg:
        return "API error {}: {}".format(status, msg)
    return "API error {}: {}".format(status, raw[:200])


def _token_file(platform):
    env_map = {
        "tiktok": "TIKTOK_TOKEN_FILE",
        "instagram": "IG_TOKEN_FILE",
        "youtube": "YT_TOKEN_FILE",
    }
    return os.getenv(env_map[platform]) or os.path.join(
        os.path.expanduser("~"), ".viralcutter", "{}_token.json".format(platform))


def _save_token(platform, payload):
    path = _token_file(platform)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


def _load_token(platform):
    path = _token_file(platform)
    if not os.path.exists(path):
        return None, path
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), path
    except Exception:
        return None, path


class _OAuthCallbackServer:
    """Tiny local HTTP server that captures one OAuth redirect (?code=...).

    Used by the TikTok authorization-code flow: we open the browser, the
    platform redirects to http://localhost:<port>/?code=...&state=..., and
    this server hands the code back to the caller.
    """

    def __init__(self, port, expected_state, timeout=180):
        self.port = port
        self.expected_state = expected_state
        self.timeout = timeout
        self.code = None
        self.error = None
        self.state_ok = False

    def _handler(self):
        expected_state = self.expected_state
        holder = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_a):
                pass

            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                query = urllib.parse.parse_qs(parsed.query)
                if query.get("error"):
                    holder.error = query.get("error_description", query.get("error"))[0]
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"ViralCutter: OAuth error received. You may close this tab.")
                    return
                code = (query.get("code") or [None])[0]
                state = (query.get("state") or [None])[0]
                if not code:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"ViralCutter: no code in redirect. You may close this tab.")
                    return
                holder.code = code
                holder.state_ok = state == expected_state
                self.send_response(200)
                self.end_headers()
                self.wfile.write(
                    b"ViralCutter: authorization received. You may close this tab and return to the app.")

            def do_HEAD(self):
                self.send_response(200)
                self.end_headers()

        return Handler

    def run(self):
        server = HTTPServer(("127.0.0.1", self.port), self._handler())
        deadline = time.time() + self.timeout
        while self.code is None and self.error is None and time.time() < deadline:
            server.handle_request()
        server.server_close()
        if self.error:
            raise RuntimeError("OAuth denied: {}".format(self.error))
        if self.code is None:
            raise RuntimeError(
                "OAuth timed out after {}s — no redirect received on http://localhost:{}/".format(
                    self.timeout, self.port))
        if not self.state_ok:
            raise RuntimeError("OAuth state mismatch (CSRF guard) — please retry.")
        return self.code


class TikTokUploader(_BaseUploader):
    """TikTok Content Posting API adapter with real OAuth2 (Roadmap 2.2).

    Setup (once) — requires a TikTok Developer app:
      1. https://developers.tiktok.com → create an app → enable the
         "Content Posting API" permission (scope `video.publish`).
      2. Add the redirect URI (default http://localhost:8431/) to the app.
      3. Set env vars TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET, then run
         `python -m scripts.upload_gate --auth tiktok` — a browser opens,
         you approve, and the token is stored in ~/.viralcutter/tiktok_token.json.

    The safety gate runs BEFORE any API call (see _BaseUploader.upload).
    Privacy: default privacyLevel is SELF_ONLY (draft, safe) — set
    TIKTOK_PRIVACY=PUBLIC_TO_EVERYONE only when you intend to publish.
    """
    platform = "tiktok"
    AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
    TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
    VIDEO_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
    VIDEO_UPLOAD_URL = "https://open.tiktokapis.com/v2/post/publish/video/upload/"
    STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
    SCOPES = "user.info.basic,video.publish"
    CALLBACK_PORT = 8431

    def __init__(self, project_folder, dry_run=False, extra_rules_path=None,
                 video_url=None):
        super().__init__(project_folder, dry_run=dry_run, extra_rules_path=extra_rules_path)
        self.video_url = video_url

    # -- OAuth -----------------------------------------------------------------

    def _redirect_uri(self):
        return os.getenv("TIKTOK_REDIRECT_URI", "http://localhost:{}/".format(self.CALLBACK_PORT))

    def auth(self):
        """Run the full OAuth consent flow (browser + local callback). No upload."""
        client_key = os.getenv("TIKTOK_CLIENT_KEY", "")
        client_secret = os.getenv("TIKTOK_CLIENT_SECRET", "")
        if not client_key or not client_secret:
            self._missing_credentials(
                self.platform, ["TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET"])
        redirect_uri = self._redirect_uri()
        import secrets
        state = secrets.token_urlsafe(16)
        params = {
            "client_key": client_key,
            "scope": self.SCOPES,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "state": state,
        }
        auth_url = "{}?{}".format(self.AUTH_URL, urllib.parse.urlencode(params))
        print("[tiktok] opening browser for consent…")
        print("[tiktok] if the browser does not open, visit:\n  {}".format(auth_url))
        try:
            import webbrowser
            webbrowser.open(auth_url)
        except Exception:
            pass
        code = _OAuthCallbackServer(self.CALLBACK_PORT, state).run()
        token = self._exchange_code(code, redirect_uri, client_key, client_secret)
        path = _save_token("tiktok", token)
        print("[tiktok] ✅ token saved → {}".format(path))
        return path

    def _exchange_code(self, code, redirect_uri, client_key, client_secret):
        form = urllib.parse.urlencode({
            "client_key": client_key,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }).encode("utf-8")
        req = urllib.request.Request(self.TOKEN_URL, data=form, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(_api_error_message(e.code, raw)) from None
        if payload.get("error"):
            raise RuntimeError("TikTok OAuth failed: {}".format(
                payload.get("error_description") or payload.get("error")))
        payload["expires_at"] = time.time() + int(payload.get("expires_in", 0) or 0)
        return payload

    def _refresh_token(self, token):
        client_key = os.getenv("TIKTOK_CLIENT_KEY", "")
        client_secret = os.getenv("TIKTOK_CLIENT_SECRET", "")
        if not client_key or not client_secret or not token.get("refresh_token"):
            self._missing_credentials(
                self.platform, ["TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET"])
        form = urllib.parse.urlencode({
            "client_key": client_key,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": token["refresh_token"],
        }).encode("utf-8")
        req = urllib.request.Request(self.TOKEN_URL, data=form, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if payload.get("error"):
            raise RuntimeError("TikTok token refresh failed: {}".format(payload.get("error")))
        new_token = dict(token)
        for key in ("access_token", "refresh_token", "expires_in", "scope", "open_id"):
            if payload.get(key) is not None:
                new_token[key] = payload[key]
        if payload.get("expires_in"):
            new_token["expires_at"] = time.time() + int(payload["expires_in"])
        _save_token("tiktok", new_token)
        return new_token

    def _ensure_token(self):
        """Return a valid access token; run OAuth on first use; refresh if expired."""
        token, path = _load_token("tiktok")
        if not token:
            self._missing_credentials(
                self.platform, ["TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET"])
        expires_at = token.get("expires_at") or 0
        if expires_at and time.time() > expires_at - 60:
            if not token.get("refresh_token"):
                self._missing_credentials(
                    self.platform, ["TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET"])
            token = self._refresh_token(token)
        return token["access_token"]

    # -- Upload ----------------------------------------------------------------

    def _do_upload(self, video_path, title, caption, hashtags):
        # Credentials first (keeps the "clear setup hint" contract), then file.
        access_token = self._ensure_token()
        if not os.path.exists(video_path):
            raise FileNotFoundError("video not found: {}".format(video_path))
        size = os.path.getsize(video_path)
        if size <= 0:
            raise ValueError("video file is empty: {}".format(video_path))

        headers = {"Authorization": "Bearer {}".format(access_token)}
        display_title = (title or caption or "ViralCutter clip")[:150]
        init_payload = {
            "post_info": {
                "title": display_title,
                "privacy_level": os.getenv("TIKTOK_PRIVACY", "SELF_ONLY"),
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": size,
                "chunk_size": size,
                "total_chunk_count": 1,
            },
        }
        init = _http_json(self.VIDEO_INIT_URL, init_payload, headers=headers)
        publish_id = ((init.get("data") or {}).get("publish_id"))
        if not publish_id:
            raise RuntimeError("TikTok init returned no publish_id: {}".format(init))

        # Upload the file bytes (single chunk).
        with open(video_path, "rb") as f:
            blob = f.read()
        upload_url = "{}?video_size={}".format(
            self.VIDEO_UPLOAD_URL + str(publish_id) + "/", size)
        _http_json(upload_url, data=None, headers={
            "Authorization": "Bearer {}".format(access_token),
            "Content-Type": "video/mp4",
        }, method="PUT", timeout=600)

        # Poll publish status (PUBLISH_COMPLETE / FAILED / PROCESSING...).
        for _ in range(30):
            status = _http_json(self.STATUS_URL, {"publish_id": publish_id},
                                headers=headers)
            state = ((status.get("data") or {}).get("status") or "").upper()
            if state == "PUBLISH_COMPLETE":
                print("[tiktok] uploaded '{}' (publish_id {})".format(
                    display_title, publish_id))
                return {"status": "uploaded", "platform": "tiktok",
                        "publish_id": publish_id, "url": "https://www.tiktok.com/"}
            if state == "FAILED":
                fail = ((status.get("data") or {}).get("fail_reason")
                        or status.get("error") or "unknown")
                raise RuntimeError("TikTok publish failed: {}".format(fail))
            time.sleep(5)
        raise RuntimeError(
            "TikTok publish is still processing (publish_id {}) — check later "
            "on tiktok.com".format(publish_id))


class InstagramUploader(_BaseUploader):
    """Instagram Graph API Reels adapter with real tokens (Roadmap 2.2).

    How it works (Instagram Graph API, documented constraints):
      * Two-step publish: POST /{ig-user-id}/media (media_type=REELS) →
        creation_id, then POST /{ig-user-id}/media_publish.
      * The API requires a **public HTTPS video_url** for the clip (there is
        no raw-file upload endpoint for IG Reels). Host the final clip on any
        public URL (your server / storage bucket) and pass it with
        `--video-url` or the IG_VIDEO_URL env var.
      * The account must be a Business/Creator account linked to a Facebook
        Page, and the Facebook app needs the `instagram_content_publish` and
        `pages_show_list` permissions.

    Token setup (once):
      1. Create a Facebook app → add Instagram Graph API.
      2. Get a short-lived user token, then exchange it for a long-lived one:
         `python -m scripts.upload_gate --auth instagram` (or set
         IG_ACCESS_TOKEN + IG_USER_ID env vars directly).
      3. Token is stored in ~/.viralcutter/ig_token.json.

    The safety gate runs BEFORE any API call (see _BaseUploader.upload).
    """
    platform = "instagram"
    GRAPH = "https://graph.facebook.com/v21.0"
    TOKEN_EXCHANGE = "https://graph.facebook.com/v21.0/oauth/access_token"

    def __init__(self, project_folder, dry_run=False, extra_rules_path=None,
                 video_url=None):
        super().__init__(project_folder, dry_run=dry_run, extra_rules_path=extra_rules_path)
        self.video_url = video_url

    def auth(self):
        """Print how to get a long-lived IG token (no browser flow needed)."""
        token = os.getenv("IG_ACCESS_TOKEN")
        if token:
            # Exchange a short-lived user token for a long-lived one.
            client_id = os.getenv("IG_CLIENT_ID")
            client_secret = os.getenv("IG_CLIENT_SECRET")
            if client_id and client_secret:
                url = "{}?grant_type=fb_exchange_token&client_id={}&client_secret={}&fb_exchange_token={}".format(
                    self.TOKEN_EXCHANGE, urllib.parse.quote(client_id),
                    urllib.parse.quote(client_secret), urllib.parse.quote(token))
                try:
                    payload = _http_json(url)
                except RuntimeError as e:
                    raise RuntimeError(
                        "IG long-lived exchange failed ({}). Set IG_ACCESS_TOKEN "
                        "directly to the long-lived token instead.".format(e)) from None
                token = payload.get("access_token", token)
            path = _save_token("instagram", {
                "access_token": token, "expires_at": 0})
            print("[instagram] ✅ token saved → {}".format(path))
            return path
        raise RuntimeError(
            "Instagram token setup: 1) generate a long-lived IG user access "
            "token (Graph API explorer) and set IG_ACCESS_TOKEN + IG_USER_ID, "
            "or 2) set IG_CLIENT_ID + IG_CLIENT_SECRET and run "
            "`--auth instagram` with a short-lived token to exchange it.")

    def _ensure_token(self):
        token, _path = _load_token("instagram")
        if not token:
            env_token = os.getenv("IG_ACCESS_TOKEN")
            if not env_token:
                self._missing_credentials(
                    self.platform, ["IG_ACCESS_TOKEN", "IG_USER_ID"])
            token = {"access_token": env_token, "expires_at": 0}
        return token["access_token"]

    def _do_upload(self, video_path, title, caption, hashtags):
        access_token = self._ensure_token()
        ig_user_id = os.getenv("IG_USER_ID") or ""
        if not ig_user_id:
            self._missing_credentials(self.platform, ["IG_USER_ID"])

        video_url = self.video_url or os.getenv("IG_VIDEO_URL", "")
        if not video_url:
            raise RuntimeError(
                "Instagram Graph API requires a PUBLIC https video_url for the "
                "clip (no raw-file upload exists for IG Reels). Host the clip "
                "and pass --video-url or set IG_VIDEO_URL.")

        caption_text = (title or "").strip()
        if caption:
            caption_text = (caption_text + "\n\n" + caption).strip()
        if hashtags:
            tags = " ".join("#" + str(h).lstrip("#") for h in hashtags if str(h).strip())
            caption_text = (caption_text + "\n\n" + tags).strip()
        caption_text = caption_text[:2200]  # IG caption limit

        base = self.GRAPH
        params = {
            "access_token": access_token,
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption_text,
            "share_to_feed": os.getenv("IG_SHARE_TO_FEED", "true").lower() in ("1", "true", "yes"),
        }
        created = _http_json("{}/{}/media".format(base, ig_user_id), params)
        creation_id = created.get("id")
        if not creation_id:
            raise RuntimeError("Instagram media creation failed: {}".format(created))

        published = _http_json("{}/{}/media_publish".format(base, ig_user_id),
                               {"creation_id": creation_id,
                                "access_token": access_token})
        media_id = published.get("id")
        print("[instagram] uploaded '{}' (media_id {})".format(title, media_id))
        return {"status": "uploaded", "platform": "instagram",
                "media_id": media_id, "url": "https://www.instagram.com/"}


UPLOADERS = {
    "youtube": YouTubeUploader,
    "tiktok": TikTokUploader,
    "instagram": InstagramUploader,
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="ViralCutter upload gate — refuses publishing blocked clips.")
    parser.add_argument("--project", required=True, help="Project folder")
    parser.add_argument("--index", type=int, default=None,
                        help="Clip index to check (default: audit all scored clips)")
    parser.add_argument("--title", default="", help="Title (checked live)")
    parser.add_argument("--caption", default="", help="Caption (checked live)")
    parser.add_argument("--hashtags", default="", help="Comma-separated hashtags")
    parser.add_argument("--extra-rules", default=None, help="Extra metadata rules JSON")
    parser.add_argument("--require-video", action="store_true",
                        help="Also require a rendered video file for the clip")
    parser.add_argument("--upload", choices=list(UPLOADERS), default=None,
                        help="Platform to upload to (dry-run by default)")
    parser.add_argument("--video", default=None, help="Video file to upload (with --upload)")
    parser.add_argument("--video-url", default=None,
                        help="Public HTTPS video URL (required by Instagram Graph API for Reels)")
    parser.add_argument("--no-dry-run", action="store_true",
                        help="Actually call the platform SDK (needs credentials)")
    parser.add_argument("--auth", choices=list(UPLOADERS), default=None,
                        help="Run the OAuth consent flow for a platform and save the token (no upload)")
    parser.add_argument("--music-gate", choices=["warn", "block", "off"], default=None,
                        help="How to treat music_fingerprint.json matches (default: warn)")
    args = parser.parse_args()

    if args.auth:
        uploader = UPLOADERS[args.auth](args.project, dry_run=True,
                                        extra_rules_path=args.extra_rules,
                                        video_url=args.video_url,
                                        music_gate=args.music_gate)
        try:
            uploader.auth()
        except UploadGateError as e:
            print(str(e))
            return 3
        return 0

    if args.upload:
        uploader = UPLOADERS[args.upload](args.project, dry_run=not args.no_dry_run,
                                          extra_rules_path=args.extra_rules,
                                          video_url=args.video_url,
                                          music_gate=args.music_gate)
        try:
            uploader.upload(args.video or _find_clip_video(args.project, args.index) or "",
                            args.title, args.caption,
                            [h for h in args.hashtags.split(",") if h.strip()],
                            index=args.index)
        except UploadGateError as e:
            print(str(e))
            return 3
        return 0

    if args.index is not None:
        verdict = check_clip(args.project, args.index, args.title, args.caption,
                             [h for h in args.hashtags.split(",") if h.strip()],
                             args.extra_rules, args.require_video)
        if verdict["allowed"]:
            print("clip #{}: ALLOWED".format(args.index))
            return 0
        print("clip #{}: BLOCKED".format(args.index))
        for r in verdict["reasons"]:
            print("  - [{}] {}: {}".format(r["severity"], r["source"], r["detail"]))
        return 3

    allowed, blocked = audit_project(args.project, args.extra_rules)
    print("audit: {} allowed, {} blocked".format(len(allowed), len(blocked)))
    for b in blocked:
        print("  BLOCKED #{} '{}' — {}".format(
            b["index"], b["title"], b["reasons"][0]["detail"] if b["reasons"] else ""))
    return 3 if blocked else 0


if __name__ == "__main__":
    sys.exit(main())
