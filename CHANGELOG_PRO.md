# ViralCutter 7.0.1-pro

## Security hardening (review pass — Aug 2026)

- **WebUI no longer serves the repo root.** Gradio `allowed_paths`/static
  mounts are restricted to `VIRALS/` (extras via `VIRALCUTTER_EXTRA_STATIC_DIRS`)
  so `api_config.json`, crash logs and OAuth tokens can no longer be fetched
  over `/file/...`.
- **Loopback by default.** The WebUI now binds `127.0.0.1` unless
  `VIRALCUTTER_HOST` is set, and prints a warning when binding to the
  network. Optional HTTP basic auth via `VIRALCUTTER_WEBUI_USER` /
  `VIRALCUTTER_WEBUI_PASSWORD` (both Gradio-launch and Uvicorn paths).
- **`/export_xml_api` path containment.** The `project` parameter is
  basenamed and validated to stay inside `VIRALS/` (no more `../` escape).
- **Gallery XSS fixed.** All user-derived strings (titles, scores, file
  names, errors) are HTML-escaped; absolute-path `/file/` URLs are no
  longer emitted for files outside the allowed static dirs.
- **Gemini key pass-through restored (env, not argv).** The pro build
  removed `--api-key` from child-process argv but never delivered the key
  to the CLI; the WebUI now injects it via `VIRALCUTTER_GEMINI_KEY` in the
  child environment (never clobbering an explicit user export).
- **Encrypted credential storage preferred by the WebUI.** When
  `VIRALCUTTER_CONFIG_PASSPHRASE` is set, saved keys go to the encrypted
  store and the plaintext `api_config.json` stays clean.
- **`api_config.json` is now gitignored** (real keys must not be committed);
  `api_config.example.json` is provided instead. Existing installs keep
  their file; new clones start from defaults.
- **Auto-updater verifies downloads.** Release assets must match a
  published `checksums.txt`/`SHA256SUMS` manifest before being installed;
  updates without a manifest are refused unless
  `VIRALCUTTER_ALLOW_UNSIGNED_UPDATE=1`. The blind "grab the first asset"
  fallback was removed.
- **`torch.load` no longer disables PyTorch's guard globally.** It first
  loads with `weights_only=True` + registered safe globals; the legacy
  `weights_only=False` path requires an explicit
  `VIRALCUTTER_ALLOW_UNSAFE_LOAD=1` opt-in.
- **ffmpeg pipe failures are no longer silent.** `generate_short_fallback`
  detects a dead encoder, surfaces the ffmpeg stderr tail and raises
  instead of finalizing a truncated clip.

## Reliability

- `main_improved.py` loads the API config unconditionally (fixes the
  resume-path `NameError` where `--ai-backend` was silently ignored when
  `viral_segments.txt` already existed).
- The pipeline no longer re-runs the whole job on user-input errors
  (`ValueError`/`TypeError` e.g. malformed `--chunk-size`).
- `--chunk-size` parsing is defensive (`_safe_chunk_size`) instead of
  crashing the run.
- Subtitle filter paths escape `'` and `:` for the ffmpeg filtergraph.
- `tests/test_preflight.py` numpy pin test is deterministic (no longer
  depends on the ambient numpy version).

# ViralCutter 7.0.0-pro

## Production hardening
- Added dependency-aware Pipeline Engine with atomic state and cancellation.
- Added non-destructive Professional Editor state with validation and undo/redo.
- Added persistent Render Queue with crash recovery of interrupted jobs.
- Removed insecure XOR credential fallback; secure credential storage now fails closed.
- Secure credential writes are atomic and use restrictive file permissions where supported.
- WebUI no longer places API keys in process arguments.
- Added regression-testable building blocks for Editor, Queue, Pipeline and credential security.

## Compatibility
- Existing `checkpoint.json` remains supported.
- Existing WebUI/CLI entry points are preserved.
