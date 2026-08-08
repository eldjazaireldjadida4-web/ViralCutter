# 🪟 Windows — Release Checklist (v6.10.0)

> ما الذي يلزم **من جهازك** لإكمال الحلقة: بناء الـ exe + اختبار حقيقي للرفع
> والتيك توك. كل ما سبق تم تطويره واختباره آلياً (429 اختباراً أخضر) —
> هذه الخطوات تحتاج **بياناتك** (مفاتيح المنصات) وجهاز **ويندوز** فقط.

---

## 1) شغّل البرنامج من المصدر أولاً (التحقق من الأساسيات)

```bat
cd ViralCutter
install_dependencies.bat          :: Python + الحزم الأساسية
pip install -r requirements-upload.txt   :: google-api / pyacoustid (اختياري)
python -m scripts.doctor          :: فحص البيئة
run_webui.bat                     :: يشغّل الواجهة على http://127.0.0.1:7860
```

افتح الواجهة وتأكد من:
- [ ] التبويب الجديد **"🚀 رفع ونشر"** ظاهر في الأسفل.
- [ ] اختر مشروعاً قديماً → تظهر قائمة المقاطع → شغّل أي مقطع في المشغّل.
- [ ] زر "فحص بصمة الموسيقى" يعمل (بدون fpcalc سيعرض تنبيهاً واضحاً — طبيعي).

## 2) بناء الـ exe (على ويندوز — لا يمكن بناؤه من لينكس)

```bat
cd ViralCutter
packaging\build_windows.bat
:: الناتج: dist\ViralCutter.exe
```

- [ ] `ViralCutter.exe` يتشغّل ويطبع رقم الإصدار `6.10.0`.
- [ ] (اختياري) حمّل `fpcalc.exe` من
      https://github.com/acoustid/chromaprint/releases وضعه بجانب الـ exe
      لتفعيل فحص الموسيقى.

## 3) إنشاء أول GitHub Release (يكمل التحديث التلقائي)

1. GitHub ← repo ← **Releases ← Create a new release**.
2. Tag: `v6.10.0` | العنوان: `v6.10.0 — TikTok/Instagram + Chromaprint + رفع من الواجهة`.
3. ارفق `dist/ViralCutter.exe` + لقطة شاشة للتبويب الجديد.

## 4) اختبار الرفع الحقيقي (يتطلب بياناتك — الكود مكتمل ومُختبَر)

### يوتيوب (كان مكتملاً)
```bat
python -m scripts.upload_gate --project VIRALS\اسم_المشروع --auth youtube
python -m scripts.upload_gate --project VIRALS\اسم_المشروع --upload youtube ^
  --index 0 --title "..." --caption "..." --hashtags "#shorts" --no-dry-run
```
- [ ] المتصفح يفتح شاشة الموافقة → يرجع الكود → يتم الرفع (خاص `private` افتراضياً؛ `YT_PRIVACY=public` للنشر).

### تيك توك (جديد)
```bat
:: مرة واحدة: أنشئ تطبيقاً على https://developers.tiktok.com
:: وأضف صلاحية Content Posting API + Redirect URI http://localhost:8431/
set TIKTOK_CLIENT_KEY=xxxx
set TIKTOK_CLIENT_SECRET=xxxx
python -m scripts.upload_gate --project VIRALS\اسم_المشروع --auth tiktok
python -m scripts.upload_gate --project VIRALS\اسم_المشروع --upload tiktok ^
  --index 0 --title "..." --caption "..." --no-dry-run
```
- [ ] أول تشغيل يفتح المتصفح → يوافق → يُحفظ التوكن → الرفع يبدأ.
- [ ] المقطع يظهر **خاص** (SELF_ONLY) في تيك توك — غيّر `TIKTOK_PRIVACY=PUBLIC_TO_EVERYONE` فقط عندما تقصد النشر.

### انستغرام (جديد)
```bat
:: حساب Business/Creator مرتبط بفيسبوك + تطبيق فيسبوك بصلاحية
:: instagram_content_publish + توكن طويل الأمد IG_ACCESS_TOKEN و IG_USER_ID
:: هام: Graph API يتطلب رابطاً عاماً HTTPS للمقطع — ارفعه على أي استضافة ثم:
python -m scripts.upload_gate --project VIRALS\اسم_المشروع --upload instagram ^
  --index 0 --title "..." --caption "..." --video-url https://example.com/clip.mp4 --no-dry-run
```

## 5) فحص الموسيقى (اختياري لكنه مفيد)

```bat
:: قاعدة مرجعية محلية (أغانيك المرخصة أو المحظورة):
python -m scripts.music_fingerprint --build-local-db C:\music --db-cache C:\Users\YOU\.viralcutter\music_db.json
python -m scripts.music_fingerprint --project VIRALS\اسم_المشروع --local-db C:\Users\YOU\.viralcutter\music_db.json
```

## 6) ماذا ترسل لي إذا علقت؟

شغّل `python -m scripts.doctor` وأرسل مخرجه + رسالة الخطأ الكاملة + رقم
الإصدار (`ViralCutter v6.10.0`). إن فشل الـ exe تحديداً، أرسل:
- نص الخطأ من النافذة، و
- نتيجة `pyinstaller packaging\viralcutter.spec --noconfirm` (آخر 30 سطراً).

---

## ملخص التغييرات في v6.10.0

| الملف | التغيير |
|---|---|
| `scripts/upload_gate.py` | TikTok OAuth2 + رفع حقيقي + refresh؛ Instagram two-step؛ `--auth`/`--video-url`/`--music-gate` |
| `scripts/music_fingerprint.py` | جديد: بصمة Chromaprint/AcoustID + مطابقة محلية + تقرير |
| `webui/publish_panel.py` | جديد: تشغيل/ترجمة/رفع لكل مقطع (لا gradio بالداخل) |
| `webui/app.py` | تبويب "🚀 رفع ونشر" |
| `main_improved.py` | `--music-check` / `--music-gate` / `--music-local-db` / `--acoustid-key` |
| `tests/` | +53 اختباراً (TikTok/IG/Chromaprint/publish_panel) |
