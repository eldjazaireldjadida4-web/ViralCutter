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
* Platform uploaders are thin adapters that MUST call `gate_upload()` first;
  their actual API calls live behind `--dry-run` stubs so the scaffold is
  honest and safe until OAuth credentials are configured.
"""

import json
import os
import sys

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
               extra_rules_path=None, require_video=False):
    """Evaluate one clip against every safety barrier.

    Returns {"allowed": bool, "reasons": [...], "metadata": {...}}.
    Never raises — callers decide what to do with the verdict.
    """
    reasons = []
    reasons += _blocklist_reasons(project_folder, index)
    reasons += _safety_report_reasons(project_folder, index)

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

    return {"allowed": not reasons, "reasons": reasons, "metadata": meta}


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
                extra_rules_path=None, require_video=False):
    """Enforcement wrapper: raises UploadGateError when the clip must not go out."""
    verdict = check_clip(project_folder, index, title, caption, hashtags,
                         extra_rules_path, require_video)
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

    def __init__(self, project_folder, dry_run=False, extra_rules_path=None):
        self.project_folder = project_folder
        self.dry_run = dry_run
        self.extra_rules_path = extra_rules_path

    def upload(self, video_path, title, caption="", hashtags=None, index=None):
        """Gate first, then upload. Raises UploadGateError when blocked."""
        gate_upload(self.project_folder, index, title, caption, hashtags,
                    self.extra_rules_path, require_video=False)
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

    def _token_path(self):
        return os.getenv("YT_TOKEN_FILE") or os.path.join(
            os.path.expanduser("~"), ".viralcutter", "yt_token.json")

    def _load_or_create_token(self):
        """Return credentials; run the OAuth consent flow on first use."""
        import google.auth.transport.requests as g_requests
        from google.oauth2.credentials import Credentials

        token_path = self._token_path()
        secrets = os.getenv("YT_CLIENT_SECRETS_FILE") or os.path.join(
            os.getcwd(), "client_secrets.json")
        if not os.path.exists(secrets):
            self._missing_credentials(self.platform, ["YT_CLIENT_SECRETS_FILE"])
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, self.SCOPES)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(g_requests.Request())
            if creds and creds.valid:
                return creds
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


class TikTokUploader(_BaseUploader):
    """TikTok Content Posting API adapter (scaffold — needs OAuth2 token).

    TODO(2.2): POST https://open.tiktokapis.com/v2/post/publish/video/upload/
    with the access token from the Content Posting API scope.
    """
    platform = "tiktok"

    def _do_upload(self, video_path, title, caption, hashtags):
        self._missing_credentials(self.platform, ["TIKTOK_ACCESS_TOKEN"])


class InstagramUploader(_BaseUploader):
    """Instagram Graph API Reels adapter (scaffold — needs IG user token).

    TODO(2.2): POST /{ig-user-id}/media with media_type=REELS + video_url,
    then POST /{ig-user-id}/media_publish.
    """
    platform = "instagram"

    def _do_upload(self, video_path, title, caption, hashtags):
        self._missing_credentials(self.platform, ["IG_ACCESS_TOKEN", "IG_USER_ID"])


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
    parser.add_argument("--no-dry-run", action="store_true",
                        help="Actually call the platform SDK (needs credentials)")
    args = parser.parse_args()

    if args.upload:
        uploader = UPLOADERS[args.upload](args.project, dry_run=not args.no_dry_run,
                                          extra_rules_path=args.extra_rules)
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
