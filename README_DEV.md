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

---

## v6 — جولة التطوير الكبرى (2026-08-04)

كل ما نُفّذ موثّق بالتفصيل في `docs/ROADMAP_REPORT.md` (القسم السادس). الملخص:

- **التوزيع**: `packaging/viralcutter.spec` (PyInstaller onefile) + سكربتات بناء
  (`build_windows.bat`/`build_linux.sh`/`build_macos.sh`) + `install_linux.sh`/
  `install_macos.sh`/`run.sh` + تحديث تلقائي (`scripts/auto_updater.py`، نسخة من `app_version.py`).
- **الحماية**: فحص بصري ONNX حقيقي (`scripts/visual_check.py` — مدمج في `risk_scorecard`)،
  بوابة رفض إجبارية (`scripts/upload_gate.py` — SDKs المنصات جاهزة للربط)،
  فحص كابشن/عنوان (`scripts/metadata_compliance.py`).
- **المونتاج**: `scripts/polish.py` يشغّل السلسلة (jump cuts → punch zoom → موسيقى مع Auto-Duck
  → ووترمارك + intro/outro) على `final/` → `final_polished/` مع إعادة توقيت الترجمة.
  فعّل عبر `--polish on`.
- **الموثوقية**: `scripts/checkpoint.py` (استئناف ذكي)، `scripts/oom_guard.py` (تراجع نموذج عند OOM)،
  `scripts/secure_config.py` (مفتاح API مشفر/env)، `scripts/crash_report.py` (تقارير خصوصية).
- **CI**: `.github/workflows/ci.yml` يثبّت ffmpeg و `tests/test_ci_smoke.py` يختبر pipeline حقيقياً.
- **الاختبارات**: 196 → **286**.

### أعلام CLI جديدة في `main_improved.py`
`--polish on` (+ `--polish-stages/--music/--music-volume/--logo/--intro/--outro/--zoom-keywords`)،
`--checkpoint on|off` (افتراضي on)، `--check-updates`، `--metadata-gate warn|block|off` (افتراضي warn)،
`--auto-download-visual`.

### بقي للجولة القادمة (موثّق كـ TODO في الكود)
ربط OAuth الفعلي لـ YouTube/TikTok/Instagram في `upload_gate`، بصمة الموسيقى (2.3)،
حلقة تغذية الضربات (5.1)، قوالب المنصات (5.2)، تحليلات الأداء (5.4)، وواجهة WebUI للأزرار الجديدة.
