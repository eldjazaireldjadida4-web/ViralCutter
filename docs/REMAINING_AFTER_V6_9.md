# 📋 تقرير "ما تبقى" — بعد جولتي v6.9 و v6.9.1

> **الغرض**: هذا الملف موجّه لأي مطوّر (إنسان أو ذكاء اصطناعي) يَلي العمل على
> المشروع — **ماذا أُنجز، وماذا تبقّى، وكيف يُنفَّذ كل بند**. لا تُعِد تنفيذ ما
> هو مُنجز، ولا تكتشف من جديد ما هو موثّق هنا.
>
> **التاريخ**: 2026-08-07 | **آخر إصدار**: v6.9.2 | **الاختبارات**: 377

---

## ✅ ما أُنجز في v6.9 (PR #1 — مدمج)

- **حفظ إعدادات Gemini تلقائياً** (`webui/settings_store.py`): المفتاح/المحرك/النموذج/حجم
  الجزء يُحمَّلون عند فتح الواجهة ويُحفظون تلقائياً عند كل تعديل — لا إعادة كتابة
  المفتاح بعد اليوم.
- **🔌 زر اختبار الاتصال** في إعدادات الذكاء الاصطناعي (SDK أو REST احتياطياً).
- **أخطاء Gemini تصبح صريحة**: `call_gemini` يرفع خطأً واضحاً عند مفتاح غير صالح
  (كان يُرجع `{}` بصمت → "no viral segments" مضلل).
- **تلميحات عربية جديدة** في `webui/utils.py` (مفتاح غير صالح، حصة منتهية، PERMISSION_DENIED...).
- **فحص مسبق** قبل التشغيل: مفتاح مفقود → رسالة فورية؛ مفتاح لا يبدأ بـ `AIza` → تحذير.
- **أمني**: `--api-key` يُقنَّع في سجل الواجهة (كان يتسرب في لقطات الشاشة).
- **`app_version.py`**: 0.9.0 → 6.9.0 (كان منحرفاً عن changelog فيكسر التحديث التلقائي).
- 17 مفتاح ترجمة × 4 لغات + 24 اختباراً جديداً.

## ✅ ما أُنجز في v6.9.1 (PR #2 — مدمج)

- **`mediapipe` أصبح اختيارياً**: كان `import mediapipe` مكشوفاً في
  `scripts/edit_video.py` و`one_face.py` و`two_face.py` → أي جهاز بلا mediapipe
  كان ينهار في منتصف المعالجة. الآن import محمي + انحدار تلقائي إلى OpenCV Haar.
- **خطوط Montserrat مضمّنة**: `fonts/` (Regular + Bold + ExtraBold + رخصة OFL)
  و`burn_subtitles.py` يمرّر `:fontsdir=` لـ ffmpeg — ترجمات "Hormozi" تظهر بخطها
  الصحيح حتى دون تثبيت الخط على النظام. أُضيفت أيضاً إلى `packaging/viralcutter.spec`.
- **CI**: أُضيفت خطوة تثبيت `ffmpeg` في `.github/workflows/ci.yml` (اختبارات
  الفيديو الحقيقية كانت تُتخطى بصمت على CI). **⚠️ لم تُرفع**: GitHub يرفض دفع
  أي تعديل على `.github/workflows/*` لأن تطبيق `moclaw-ai` بلا صلاحية
  **Workflows**. المحتوى الجاهز للتطبيق في البند 1 أدناه.
- اختبارات: `tests/test_mediapipe_optional.py` (2) + `tests/test_fonts.py` (4).

## ✅ ما أُنجز في v6.9.2 (PR #3 — مدمج)

- **كل حقول الواجهة تُحفظ تلقائياً**: امتداد لميزة v6.9 — جودة الفيديو، الترجمة
  الهدف، ترجمات يوتيوب، فلتر الأمان + المراجعة AI، قالب المنصة، بوابة الميتاداتا،
  لغة العناوين، التلميع، الموسيقى، اللوجو، الكوكيز، نموذج Whisper، طريقة العمل.
  الملف `webui_settings.json` محلي وغير متتبَّع في git + كتابة ذرّية.
- **READMEs (ar/en/pt)**: الإصدار صُحّح 0.9.0 → 6.9.2 (كان منحرفاً).
- اختبارات: +4 → **377**.

---

## 🔴 أولويات حرجة — تمنع اكتمال "الحلقة"

### 1. تفعيل GitHub Actions + صلاحية Workflows (إجراء من المالك)
- المشكلة: بعد كل push لا تظهر أي check runs — Actions غير مفعّلة أو تطبيق
  `moclaw-ai` بلا صلاحية **Workflows** (الجولة السابقة وثّقت رفض GitHub للرفع،
  وv6.9.1 رُفض دفعها بنفس الرسالة حرفياً).
- الحل (دقيقة واحدة):
  1. GitHub ← repo ← **Settings ← Actions ← General ← Enable**.
  2. GitHub ← avatar ← **Settings ← Applications** ← moclaw-ai ←
     أعطِ **Read and write** لصلاحية **Workflows** (المطلوبة لرفع/تشغيل
     `.github/workflows/*`).
  3. بعدها ارفع ملف `ci.yml` التالي (جاهز) — أو أي تعديل مستقبلي عليه:
- **محتوى `ci.yml` الجاهز (مع خطوة ffmpeg):**
  ```yaml
  name: CI

  on:
    push:
      branches: [main]
    pull_request:

  jobs:
    test:
      runs-on: ubuntu-latest
      strategy:
        matrix:
          python-version: ["3.10", "3.11", "3.12"]
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-python@v5
          with:
            python-version: ${{ matrix.python-version }}
            cache: pip
        - name: Install ffmpeg (real-video smoke tests)
          run: sudo apt-get update && sudo apt-get install -y ffmpeg
        - name: Install test dependencies
          run: pip install pytest
        - name: Run unit tests
          run: pytest -v
  ```
- إن رُفض رفع ملفات `ci.yml` مستقبلاً من التطبيق، فهذا السبب.

### 2. إنشاء أول GitHub Release — يكمل التحديث التلقائي
- الـ tag `v6.9.1` مرفوع. `scripts/auto_updater.py` يفحص Releases ثم يتراجع
  لأحدث tag — أول Release رسمي يفعل الحلقة كاملة.
- الخطوات:
  1. ابنِ ملف ويندوز: `packaging/build_windows.bat` (يتطلب PyInstaller +
     `pip install -r requirements.txt` على جهاز Windows).
  2. GitHub ← repo ← **Releases ← Create a new release**.
  3. Tag: `v6.9.1` | العنوان: `v6.9.1 — حفظ الإعدادات + خطوط مضمّنة + أخطاء أذكى`.
  4. ارفق `dist/ViralCutter.exe` + لقطتي شاشة للواجهة.
- ملاحظة: حتى Release بدون exe يفيد — سيرى المستخدمون وجود تحديث.

---

## 🟡 ميزات موثّقة في `docs/ROADMAP_REPORT.md` لم تُنفَّذ بعد

| # | البند | الحالة | أين |
|---|-------|--------|-----|
| 1 | **ربط OAuth TikTok/Instagram** | يوتيوب مكتمل؛ TikTok/Insta TODOs في الكود | `scripts/upload_gate.py` |
| 2 | **بصمة الموسيقى Chromaprint (2.3)** | غير منفّذ — فحص حقوق النشر الصوتية | جديد |
| 3 | **حلقة الضربات Strike Feedback (5.1)** | غير منفّذ | جديد |
| 4 | **تحليلات الأداء (5.4)** | غير منفّذ — YouTube Analytics API | جديد |
| 5 | **استبدال حلقة OpenCV بـ ffmpeg pipe** | A/V desync جذري على فيديوهات معينة | `scripts/edit_video.py` |
| 6 | **WebUI: أزرار polish/gate لكل مشروع** | السباكة جاهزة؛ حقول v6 موجودة في الواجهة | `webui/app.py` |

## 🟢 ملاحظات تشغيلية

- **التثبيت الكامل** يحتاج: `requirements.txt` + `requirements-transcribe.txt`
  (whisperx/torch) + `requirements-upload.txt` — المثبّتون يسألون عنها.
- **فحص البيئة**: `python -m scripts.doctor` قبل رفع المشاكل.
- **قاعدة i18n**: أي مفتاح إنجليزي جديد يجب إضافته للغات الأربع
  (`en_US`/`ar_SA`/`pt_BR`/`tr_TR`) وإلا تفشل `tests/test_i18n_completeness.py`.
  ملفات locale بمسافة بادئة 4 (indent=4).
- **قاعدة الإصدار**: `app_version.py` يجب أن يطابق changelog دائماً؛ وارفع tag
  بنفس الرقم عند كل إصدار (التحديث التلقائي يعتمد على المقارنة).
- **الخطوط**: أي خط جديد يوضع في `fonts/` مع رخصة OFL ويُضاف للـ spec.

## 🧪 الاختبارات

| قبل v6.9 | بعد v6.9 | بعد v6.9.2 |
|---|---|---|
| 343 | 367 | 377 |
