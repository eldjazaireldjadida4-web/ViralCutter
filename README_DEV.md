# Development Notes

## Done
- ✅ Test suite: 73 unit tests (`tests/`) covering i18n, subtitle helpers, JSON cutting, saving, and WebUI utils. Run with `pytest` (install `requirements-dev.txt`).
- ✅ i18n overhaul: `ar_SA.json` fully covers every UI/CLI string; `en_US.json` cleaned (had 71 Arabic values); `pt_BR`/`tr_TR` completed with English fallback. Coverage guarded by `tests/test_i18n_completeness.py`.
- ✅ Locale loading no longer depends on the current working directory.
- ✅ Language is configurable: `VIRALCUTTER_LANG` env var (default `ar_SA`).
- ✅ `webui/app.py`: duplicate `AR_LABELS` dict removed; pure helpers extracted to `webui/utils.py`; RTL layout + Arabic font stack added.

## Current gaps
- No automated tests for the heavy pipeline stages (download/transcribe/edit) — they need model/video fixtures or mocks.
- `webui/app.py` is still large (~940 lines); `run_viral_cutter` and the UI blocks could be split further.
- Dependencies are unpinned in `requirements.txt` (reproducibility risk).
- CI workflow is ready but not yet committed (needs GitHub App `workflows` permission).

## Suggested next steps
1. Add a lightweight smoke test for the CLI startup path (mock heavy imports).
2. Split the Gradio UI blocks into dedicated builder modules.
3. Pin dependency versions after verifying a clean install.
4. Tighten error reporting for missing dependencies and invalid project state.
