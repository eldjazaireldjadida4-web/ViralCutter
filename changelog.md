# Changelog

## 🚀 v6.11.0 — حواجز الاستخدام الواسع: exe مبني تلقائياً + فحص موسيقى يخدم فعلاً + رفع انستغرام يشتغل بدون استضافة يدوية (2026-08-08)

### New — الـ exe يُبنى تلقائياً على GitHub Actions (يزيل أكبر حاجز)
- PyInstaller لا يعمل cross-compile، فكان الـ Release يتطلب ويندوز يدوياً.
  الآن `.github/workflows/build-exe.yml` يبني `ViralCutter.exe` على runner
  ويندوز رسمي: على أي `tag v*` يُرفع الـ exe تلقائياً إلى Release، وعلى
  `workflow_dispatch` يبني الفرع الحالي ويتركه artifact للاختبار.
- الـ exe يأتي و **fpcalc.exe مدمج** بداخله — فحص الموسيقى يشتغل من أول تشغيل
  (المستخدم العادي لا يحتاج تحميل أي شيء).

### Fix — فحص الموسيقى لم يعد "بلا أسنان" بدون إعداد
- **`--install-fpcalc`**: أمر واحد يحمّل fpcalc.exe تلقائياً (من
  releases الرسمية لـ chromaprint) ويضعه بجانب التطبيق أو في
  `~/.viralcutter/bin` — بدل إرشاد يدوي طويل.
- **استعلام AcoustID بدون pyacoustid**: بصمة `fpcalc -raw` تُرمَّز الآن
  تلقائياً (encode 32-bit) وتُرسل إلى `api.acoustid.org` — سابقاً كان
  مسار fpcalc وحده لا يستطيع الاستعلام إطلاقاً.
- `fpcalc_available()`/`fingerprint_file()` يبحثان الآن بجانب الـ exe
  (sys._MEIPASS) ثم `~/.viralcutter/bin` ثم PATH — يعمل مع النسخة المعبأة
  وبدونها.
- **صدق في التقرير**: `music_fingerprint.json` يعلن `backend`
  (pyacoustid/fpcalc/none) + `coverage_note` صريحة أن AcoustID لا يغطي
  الموسيقى العربية/غير المسجّلة جيداً، ويوصي بقاعدة مرجعية محلية
  (`--build-local-db`) لهذا النوع — فالمستخدم يعرف بالضبط قوة الفحص لا وهمه.
- CLI يطبع تحذيراً واضحاً عندما يكون `no_fpcalc > 0` مع خطوة الإصلاح.

### Fix — الرفع لانستغرام يشتغل بدون استضافة يدوية
- Graph API لا يقبل ملفاً محلياً (يلزم رابط HTTPS عام) — كان هذا يقتل
  الميزة للمستخدم العادي. الآن `host_media_file()` يرفع المقطع تلقائياً إلى
  مضيف مجاني مجهول (catbox.moe، و0x0.st احتياطاً) ويمرر الرابط إلى
  Graph API. عطّل ذلك بـ `IG_HOST_DISABLE=1` أو اربط `IG_VIDEO_URL` بنفسك.
- مكالمات Graph API (media/media_publish) أصبحت form-encoded
  (application/x-www-form-urlencoded) كما يتوقعها API فعلياً — كانت JSON.

### Fix — باك حقيقي في رفع تيك توك
- بايتات الفيديو كانت تُقرأ في الذاكرة و**لا تُرسل أبداً** في PUT
  (`data=None`) — ينجح مع mock ولا ينجح ضد API الحقيقي. أُصلح: الـ body
  الآن هو البايتات نفسها مع `Content-Type: video/mp4`.
- أخطاء الأذونات/الموافقة في تيك توك تُرفق تلميحاً صريحاً
  (الموافقة على Content Posting API تستغرق أياماً/أسابيع) بدل رسالة غامضة.

### New — تشخيص قبل الرفع
- `python -m scripts.upload_gate --check <youtube|tiktok|instagram>`: يفحص
  بدون شبكة — المفاتيح، التوكنات، وما لا يمكن التحقق منه محلياً (موافقة
  تيك توك) يُعلَن بوضوح. `--project` لم يعد مطلوباً لهذا الأمر.

### Tests
- +~74 اختباراً: باك الـ PUT، ترميز البصمة، تلقائي المضيف، `--check`،
  اكتشاف fpcalc، إلخ. **451 passed** محلياً.

## 🚀 v6.10.0 — ربط TikTok/Instagram + بصمة الموسيقى Chromaprint + أزرار رفع من الواجهة (2026-08-08)

### New — TikTok Content Posting API (Roadmap 2.2)
- **رفع حقيقي لتيك توك** في `scripts/upload_gate.py`: OAuth2 كامل
  (authorization-code + local callback + refresh token) عبر
  `python -m scripts.upload_gate --auth tiktok`، ثم init → PUT upload →
  status polling على `open.tiktokapis.com/v2/post/publish/...`.
- الخصوصية الآمنة افتراضياً `SELF_ONLY` (مسودة خاصة)؛ غيّرها بـ `TIKTOK_PRIVACY`
  عندما تقصد النشر فعلاً. المتطلبات: تطبيق مطوّر TikTok مع صلاحية
  Content Posting API + `TIKTOK_CLIENT_KEY` / `TIKTOK_CLIENT_SECRET`.
- التوكن يُحفظ في `~/.viralcutter/tiktok_token.json` ويُجدَّد تلقائياً.

### New — Instagram Graph API Reels (Roadmap 2.2)
- رفع Reels بخطوتين (`/media` → `/media_publish`) مع توكن طويل الأمد
  (`IG_ACCESS_TOKEN` + `IG_USER_ID`) ودعم تبادل التوكن القصير
  (`--auth instagram` مع `IG_CLIENT_ID/SECRET`).
- ملاحظة صريحة في الكود: Graph API يتطلب **رابطاً عاماً HTTPS** للفيديو
  (لا يوجد رفع ملفات خام لـ Reels) — مرّر `--video-url` أو `IG_VIDEO_URL`.

### New — بصمة الموسيقى Chromaprint (Roadmap 2.3)
- `scripts/music_fingerprint.py`: بصمة محلية عبر `pyacoustid` أو `fpcalc`,
  كشف عبر AcoustID (مفتاح عام مدمج + `ACOUSTID_API_KEY`)، وقاعدة مرجعية
  محلية دون إنترنت (`--build-local-db` + مطابقة n-gram).
- النتيجة في `music_fingerprint.json` لكل مقطع + ملخص في النهاية.
- بوابة الرفع تستهلك التقرير: `--music-gate warn` (افتراضي، تحذير لا يمنع) /
  `block` (يرفض الرفع) / `off`. في الواجهة: زر "فحص بصمة الموسيقى".
- انحدار كامل: بدون fpcalc/pyacoustid لا ينكسر شيء — يُكتب `no_fpcalc`.

### New — WebUI: أزرار تشغيل/ترجمة/رفع لكل مقطع (بدل CLI فقط)
- تبويب جديد **"🚀 رفع ونشر"**: اختر مشروعاً ثم مقطعاً من القائمة →
  **تشغيل مباشر** في مشغّل فيديو، اقتراح عنوان/وصف من `viral_segments.txt`.
- **ترجمة** ترجمات المقطع الواحد (deep-translator) مع معاينة النص.
- **رفع** عبر بوابة الأمان (يوتيوب/تيك توك/انستغرام) مع تجربة (dry-run)
  افتراضية، وسجل رفع حي في الواجهة، وخيار بوابة الموسيقى.
- وحدة قابلة للاختبار `webui/publish_panel.py` (لا تعتمد على gradio).

### Fixes
- `check_clip`/`gate_upload` يدعمان `music_gate`؛ تحذيرات الموسيقى لا تمنع
  الرفع وحدها (المانع يبقى للخطورة العالية).
- `_BaseUploader` يقبل `video_url` و`music_gate` — واجهة موحدة لكل المنصات.

### Tests
- +53 اختباراً (TikTok flow/refresh/status، Instagram two-step، OAuth
  URLs، Chromaprint decode/مطابقة محلية/AcoustID، بوابة الموسيقى،
  publish_panel كاملاً). — يشمل الاختبارات السابقة.

### ملاحظة Windows (المستخدم)
- لا يمكن بناء `ViralCutter.exe` من لينكس (PyInstaller ليس cross-compiler) —
  شغّل `packaging/build_windows.bat` على جهازك (الخطوات في
  `docs/RELEASE_CHECKLIST_WINDOWS.md`).
- للتحقق الكامل من الرفع والتيك توك: أنت وحدك تملك بيانات الحسابات —
  كل الكود مكتوب ومُختبَر (mocks)؛ التشغيل الحي يتطلب مفاتيحك.

## 💾 v6.9.2 — كل إعدادات الواجهة تُحفظ تلقائياً (2026-08-07)

### New
- **الحفظ الكامل للواجهة**: امتداد لميزة v6.9 — ليس المفتاح فقط، بل **كل حقول
  النموذج** تُتذكَّر الآن تلقائياً بين الجلسات: جودة الفيديو، الترجمة الهدف،
  ترجمات يوتيوب، فلتر الأمان ومراجعته، قالب المنصة، بوابة الميتاداتا، لغة
  العناوين، التلميع، الموسيقى، اللوجو، الكوكيز، نموذج Whisper، وطريقة العمل.
  يُحفظ الملف محلياً `webui_settings.json` (غير متتبَّع في git).
- الآلية: `.change` على كل حقل → حفظ ذري؛ `demo.load` → استعادة كل الحقول.
- 4 اختبارات جديدة (round-trip، تجاهل None، ملف تالف، ملف مفقود).

## 🛠️ v6.9.1 — mediapipe اختياري + خطوط Montserrat مضمّنة + CI ffmpeg (2026-08-07)

### Fixes
- **mediapipe أصبح اختيارياً** في `scripts/edit_video.py` / `one_face.py` /
  `two_face.py`: كان `import mediapipe` مكشوفاً فتنهار المعالجة في منتصفها على
  أي جهاز بلا الحزمة. الآن انحدار تلقائي إلى OpenCV Haar Cascade (كان جاهزاً
  في موقع الاستخدام — فقط الاستيراد كان يقتل الوحدة).
- **خطوط Montserrat مضمّنة** في `fonts/` (Regular/Bold/ExtraBold + OFL):
  `burn_subtitles.py` يمرّر `:fontsdir=` لـ ffmpeg فتُحفظ ترجمات "Hormozi" بخطها
  الصحيح حتى بدون تثبيت الخط على النظام (كان ffmpeg يستبدله بصمت). أُضيفت
  الخطوط إلى `packaging/viralcutter.spec` أيضاً.
- **CI**: خطوة `apt-get install ffmpeg` في `.github/workflows/ci.yml` جاهزة
  لكنها **محجوبة بالصلاحيات**: GitHub يرفض دفع تعديلات workflows من تطبيق
  moclaw-ai بلا صلاحية Workflows. المحتوى كاملاً موثّق في
  `docs/REMAINING_AFTER_V6_9.md` البند 1 ليُرفع بعد منح الصلاحية.
- **تقرير تسليم جديد**: `docs/REMAINING_AFTER_V6_9.md` — ما أنجزناه وما تبقى
  وكيف يُنفَّذ كل بند (تفعيل Actions، أول Release، OAuth، Chromaprint...).

### Tests
- `tests/test_mediapipe_optional.py` (2) + `tests/test_fonts.py` (4).
- الإجمالي: **373** (367 + 6).

## 💾 v6.9 — Persistent AI settings: save the Gemini key once, never retype it (2026-08)

### New
- **Auto-saved AI settings (the headline request)**: the WebUI now loads the
  saved Gemini key / backend / model / chunk size at startup and auto-saves
  them on every change (plus an explicit 💾 Save button). One paste, remembered
  forever — no more re-entering the key each session.
- **🔌 Test Connection button**: validates the Gemini key instantly from the UI
  (SDK or REST fallback) instead of discovering a bad key mid-processing.
- **Settings status card**: shows the masked key (`AIza********wxyz`) and where
  it came from (env var / encrypted store / api_config.json).
- Resolution order mirrors the CLI: `GEMINI_API_KEY` env → encrypted store →
  `api_config.json`. Env keys are never copied into the file.

### Error handling
- **Gemini key errors fail loudly**: `call_gemini` used to return `"{}"` on an
  invalid key, so runs died later on the confusing "no viral segments" error.
  It now raises a clear bilingual error naming the real cause.
- New Arabic hints for: invalid key, quota exhausted, PERMISSION_DENIED,
  generativelanguage errors, empty AI responses.
- **WebUI preflight**: missing-key runs fail fast with an actionable message;
  keys that don't look like Gemini keys (`AIza…`) log a warning.

### Security
- **API key no longer leaks into the visible log**: the echoed command line now
  masks `--api-key <value>` before printing.
- `app_version.py` bumped 0.9.0 → 6.9.0 (it had drifted from the changelog, so
  the auto-updater compared the wrong version).

### Tests
- 24 new tests (settings round-trip, atomic writes, env precedence, masking,
  connection-test guards, loud key errors, new hints). Total: 367.

## 🛠️ v6.8.1 — WebUI bug fixes, tests green on clean CI, dark theme (2026-08)

### Fixes
- **WebUI parameter order bug (critical)**: `run_viral_cutter` tail signature
  `(platform, polish, music, logo, metadata_gate, cookies, title_language)` did
  not match the `inputs=[...]` order sent by all three callers (Start, Review
  Segments render, Batch Queue). Effect: polish ran with `--music auto`,
  cookies/title-language selections were silently ignored. Signature now matches
  the UI order.
- **Stop button**: `kill_process` returned 6 values for 5 outputs (missing
  progress panel) — Gradio raised on every Stop click. Fixed.
- **Duplicate template handlers**: Save/Apply template buttons were wired twice
  (flat + nested payload formats) so both fired on one click. Consolidated to a
  single nested-format handler pair.
- **Subtitle Editor tab**: file list update was written into a status Textbox
  (Dropdown update into Textbox) and `current_json_path` was never set — "Render
  Selected" could never work. Added a real file Dropdown wired to
  project/subs/*_processed.json.
- **Gemini dual-SDK detection**: `import google.generativeai` required the parent
  `google` namespace package; now uses `importlib.import_module` so sys.modules
  fakes / hermetic environments resolve correctly.
- **yt-dlp optional import** in `scripts/download_video.py`: module imports
  without yt-dlp (friendly-error helpers still work); a clear RuntimeError is
  raised only when a download is attempted.
- **YouTube uploader**: missing-credentials error now raised *before* importing
  the optional google libs, so the actionable message appears in minimal envs.
- **on_source_change** no longer calls `refresh_projects()` twice.

### WebUI polish
- Rich header (version badge, feature list) actually rendered (was dead code).
- Full dark theme: Gradio 6 compatible (theme/css routed per version;
  `is_custom_theme` set for the mount path), dark blocks/inputs/tabs/radios.
- Progress/tasks panels restyled for the dark surface; dead duplicate
  `render_error_html` removed; orphaned headings removed from the log row.

### Tests
- All 343 tests pass with only `pytest` installed (CI parity), including the
  6 that previously failed on a clean environment.

## 📊 Risk Scorecard + Reused-Content Protection (v4)

### Novidades
- **Per-clip YouTube Risk Scorecard** (`scripts/risk_scorecard.py`): after every render, each clip gets a compliance report — `risk_scorecard.json` with axes: **reuse** (how identical the final clip still is to the raw source window, via dHash frame comparison — >70% = "reused content" risk), **first7s** (profanity inside the first 7 seconds = limited ads), **visual** (letterbox detection + local ONNX model hook), **overall** (low/medium/high/danger).
- **Publish gate**: `--risk-gate warn` (default) writes `publish_blocklist.json` listing clips that must NOT be uploaded; `--risk-gate block` stops the run. Standalone: `python scripts/risk_scorecard.py --project X --exit-on-blocked`.
- **Reused-content guide** in README_ar.md: practical rules to keep clips "transformative" (commentary, cropping, shortening, source choice).
- **13 testes novos** (test_risk_scorecard.py, incl. real ffmpeg dHash similarity and pillarbox detection). Total: 196 testes.

## 🔄 Auto-Updating Hate-Speech Word List

### Novidades
- **Lista de bloqueio com auto-atualização** (`scripts/safety_updater.py`): a lista oficial versionada (`safety_blocklist.json` no repositório) é baixada **automaticamente 1x por dia** durante o processamento (e por botão na WebUI). Novas palavras chegam ao usuário sem atualizar o programa.
- **Offline-safe**: falha de rede → usa o cache anterior (ou a lista embutida) e o pipeline continua.
- Merge automático das palavras remotas no filtro e no modo Bleep; `allow_terms` continua funcionando sobre elas.
- Flag `--safety-autoupdate on|off` (padrão: on). Cache local é git-ignored.
- Script de manutenção `scripts/export_blocklist_pack.py --version N` para publicar novas palavras a todos os usuários.
- **16 testes novos** (test_safety_updater.py, incluindo throttle diário e fallback offline). Total: 183 testes.

## 🔇 Bleep Mode + AI Policy Review (Safety Filter v2)

### Novidades
- **Modo `censor` (Bleep)**: em vez de remover o segmento inteiro, o ViralCutter agora **silencia apenas as palavras que violam políticas** (`volume=0` via ffmpeg na janela exata da palavra) e as mascara como `████` nas legendas — o clipe viral sobrevive. Mapa completo em `censor_map.json`.
- **Revisão contextual por IA (`--safety-ai`, padrão: on)**: os segmentos sobreviventes são enviados ao Gemini/G4F para uma segunda verificação de política do YouTube — captura discurso de ódio contextual sem palavras proibidas (ex.: "essa gente não merece existir"). Nunca quebra o pipeline: falha na API → filtro de palavras permanece.
- **Allowlist**: `safety_terms.json` agora aceita `allow_terms` para excluir falsos positivos da lista embutida (ex.: canal de história dizendo "منغولي").
- **Aba Review mostra segurança**: nova coluna "الأمان" (✅ / ⚠️ / 🔇 / 🤖⚠️) com o status de cada segmento.
- **WebUI**: seletor do modo Bleep + checkbox da revisão por IA.
- **29 testes novos** (`test_censor_engine.py`, `test_safety_ai.py`) incluindo teste real de muting com ffmpeg. Total: 167 testes.

## 🛡️ Safety Filter — YouTube Hate-Speech Shield

### Novidades
- **Filtro de segurança anti-strike (`scripts/safety_filter.py`)**: novo módulo que analisa o texto transcrito de cada segmento viral e **bloqueia antes do corte** os clipes com discurso de ódio, incitação à violência, xingamentos e assédio — a principal causa de strikes do YouTube ("الكلام الذي يحضّ على الكراهية").
- **100% local e multilíngue**: lista de termos em árabe (fusha + dialetos, incl. magrebino/argelino), inglês, português, francês, espanhol e turco. Normalização robusta contra evasões: diacríticos/tatweel árabe, dobra de alef/yá/taa-marbuta, remoção do artigo "ال" colado, leetspeak (@→a, 3→ع) e letras repetidas.
- **3 modos** (`--safety-mode`): `block` (padrão — remove o segmento), `flag` (mantém e anota para revisão), `off`. Severidade mínima configurável (`--safety-min-severity`).
- **Relatório detalhado** `safety_report.json` por projeto: veredito por segmento, termos encontrados, categoria, severidade e timestamp aproximado.
- **Termos personalizados**: arquivo `safety_terms.json` (raiz ou pasta do projeto) para estender a lista — ver `safety_terms.example.json`.
- **Prompt anti-violação**: `prompt.txt` agora instrui o LLM a nunca selecionar segmentos com discurso de ódio/violência (prevenção na fonte).
- **WebUI**: novo seletor "🛡️ Safety filter (hate speech)" com os 3 modos; CLI standalone: `python scripts/safety_filter.py --project <pasta> --mode block --in-place`.
- **i18n**: 14 novas chaves traduzidas (ar/en/pt/tr) + 25 testes novos (`tests/test_safety_filter.py`).

## Fixes for Manual/Raw JSON Input

### Core Functionality
- **Raw Segment Repair**: Implemented automatic detection and repair of segments that lack timestamp information (e.g. manually crafted JSON with just reference tags). The system now recalculates start/end times using the transcript alignment logic.
- **Duration Constraint Hardening**: The timestamp alignment logic now strictly enforces the user-defined `min_duration`, effectively extending segments that the AI might have outputted as too short.

## Suporte a GGUF e Ajustes de Link

### Novidades
- **Suporte a GGUF**: colocado suporte a gguf para llm local.
- **Link Público**: ajustado diretórios de link público.

## Melhorias de Qualidade de Vídeo, Legendas e Processamento

### Novidades

- **Aprimoramento de prompt para LLM**: melhorias no prompt para permitir que o modelo de linguagem compreenda melhor o contexto do conteúdo.
- **Aprimoramento na detecção facial**: melhorias na identificação de rostos quando várias pessoas estão falando simultaneamente.
- **Seleção de Qualidade de Vídeo**: agora é possível escolher a qualidade desejada para download de vídeos (Melhor, 1080p, 720p, 480p) diretamente pela WebUI ou CLI, permitindo otimizar entre velocidade e uso de armazenamento.
- **Controle de Legendas do YouTube**: adicionada a opção de ignorar o download de legendas oficiais do YouTube, permitindo forçar uma nova transcrição via Whisper, se desejado.
- **Suporte a VTT**: o script de transcrição foi aprimorado para oferecer suporte a arquivos de legenda `.vtt` para alinhamento, garantindo maior compatibilidade.
- **Tradução de legendas em JSON com destaque palavra por palavra**: adicionada a tradução de legendas no formato JSON, permitindo highlight e sincronização word-by-word em outro idioma durante a exibição.

### Melhorias e Otimizações

- **yt-dlp mais robusto**: corrigidos problemas em que downloads de vídeo estavam sendo salvos como “Unknown_Video” e exibiam progresso incorreto. Também foram adicionados logs de progresso mais precisos e suporte aprimorado ao download de legendas.
- **Otimização de Legendas do YouTube**: quando legendas do YouTube estão disponíveis, o sistema agora faz o download automático e as utiliza apenas para alinhamento, pulando o processo pesado e demorado de transcrição. Isso acelera significativamente o processamento de vídeos que já possuem legendas.


## Active Speaker & Face Controls

### Controles Avançados de Face e Falante Ativo
- **Filtros de Face**: Controle granular para ignorar rostos pequenos, definir limite de confiança minimiza falsos positivos e "Zona Morta" para estabilizar a câmera.
- **Experimental: Active Speaker**: Novo modo experimental que tenta focar na pessoa que está falando (detecção de boca aberta e movimento), em vez de sempre dividir a tela.
- **Legendas**: Opção para remover pontuação automaticamente.

## Editor de Legenda JSON

### Funcionalidades
- **Editor de Legendas**: Adicionado um editor de legendas simples, dentro das limitações do Gradio, para corrigir erros de ortografia ocorridos durante o uso do WhisperX.

### Correções
- **Geral**: Alguns Fix Colab e melhorias na geração de viral segments.

## Gradio WebUI & UV Installation

### Nova Interface Web (Gradio)
- **OpusClip Inspired**: Nova interface gráfica construída com Gradio, inspirada no design do OpusClip, oferecendo uma experiência de usuário moderna e intuitiva.
- **Funcionalidades da UI**: Ajustes completos para garantir que todas as funcionalidades da ferramenta estejam acessíveis e operantes através da nova interface.

### Instalação e Infraestrutura
- **Instalação via UV**: Criação de script `.bat` para instalação otimizada de dependências utilizando o `uv`, acelerando o processo de setup.
- **Fixes Gerais**: Correções em diversos componentes que estavam quebrados ou instáveis, garantindo maior estabilidade na execução via UI.

## WebUI 2.0 & Enhanced Configuration

### WebUI Overhaul
- **Dark & Modern UI**: Interface completamente redesenhada com tema escuro e layout em grid responsivo (estilo Opus.pro) para a galeria de vídeos.
- **Dynamic Configuration**: Componentes da interface agora reagem dinamicamente à escolha do Backend de IA, atualizando automaticamente a lista de modelos disponíveis e o tamanho sugerido de chunk.
- **Improved Controls**: Controle granular sobre `Face Detect Interval`, `Skip Prompts`, e `Chunk Size` diretamente na interface web.
- **Refactoring**: Código da WebUI refatorado e modularizado (`library.py` separado do `app.py`) para melhor manutenção.

### Core & CLI
- **Arguments Expansion**: `main_improved.py` agora aceita argumentos de linha de comando para `--chunk-size` e `--ai-model-name`, permitindo override total da configuração.
- **Script Update**: `create_viral_segments.py` atualizado para respeitar os parâmetros passados via CLI, priorizando-os sobre o arquivo de configuração.

## Fix 2 faces

### Melhorias na Detecção Facial e Layout
- **Consistência Visual (2 Faces)**: Implementada lógica para "travar" a identidade dos rostos nas posições superior e inferior, impedindo que os participantes troquem de lugar durante o vídeo.
- **Lógica de Fallback Inteligente**: Caso o rosto não seja detectado no frame atual, o sistema agora tenta recuperar a posição baseada no frame anterior, posterior ou na última coordenada válida conhecida.
- **Intervalo de Detecção Personalizável**: Adicionada configuração para o usuário escolher a frequência da varredura facial, permitindo otimizar o tempo de renderização.

### Correções de Legendas
- **Correção de Sobreposição**: Resolvido bug onde legendas apareciam sobrepostas em momentos de fala rápida.
- **Refinamento de Centralização (2 Faces)**: Ajustes adicionais no cálculo de posição para garantir que a legenda fique perfeitamente centralizada no modo dividido.

## Atualizações Anteriores

### Refatoração e Melhorias de Código
- **Refatoração do Script Principal**: Criação e aprimoramento do `main_improved.py` para melhorar a estrutura e manutenibilidade do pipeline de processamento.
- **Padronização de Código (Inglês)**: Tradução completa de nomes de variáveis, funções e comentários internos para inglês, visando compatibilidade com padrões internacionais e colaboração open-source, mantendo logs de saída com suporte a i18n (`en_US`/`pt_BR`).
- **Ajuste de Diretórios**: Reorganização da estrutura de pastas e caminhos de saída para maior organização dos arquivos gerados.

### Configuração e IA
- **Integração Multi-LLM**: Implementação de suporte ao **g4f** (GPT-4 Free) e **Google Gemini**.
- **API Config**: Centralização das chaves e seleção de modelos no novo arquivo `api_config.json`, permitindo troca rápida de provedor de IA sem alterar o código.
- **Gerenciamento de Prompts**: Criação do arquivo `prompt.txt` para edição fácil do prompt do sistema.

### Legendas e Transcrição (Whisper)
- **Correções no Whisper**: Solução robusta para erros de `unpickling`, conflitos de DLLs (`libprotobuf`, `torchaudio`) e detecção de GPU.
- **Otimização do Fluxo (Slicing)**: O vídeo original é transcrito apenas uma vez. Os cortes reutilizam o JSON original, eliminando a re-transcrição e acelerando o processo.
- **Posicionamento de Legendas**: Correção da lógica de alinhamento para centralização no modo "2-face".

### Processamento de Vídeo e Detecção Facial
- **Novo Motor: InsightFace**: Adição da biblioteca `InsightFace` como motor de detecção facial de alta precisão.
- **MediaPipe**: Manutenção e correção de erros no fallback para o MediaPipe.
- **Limpeza de Logs**: Redução da verbosidade dos logs do FFmpeg no console.
## ⚙️ v6 — Distribution + Visual Safety + Pro Editing + Reliability (`f37e007`)

### Novidades
- **Pacote único (Roadmap 1.1)**: `packaging/viralcutter.spec` (PyInstaller onefile) + scripts de build Windows/Linux/macOS.
- **Auto-update (1.2)**: `scripts/auto_updater.py` verifica GitHub Releases; versão central em `app_version.py` (0.9.0); `--check-updates`.
- **Instaladores Linux/macOS (1.3)**: `install_linux.sh`, `install_macos.sh`, `run.sh`.
- **Verificação visual ONNX (2.1)**: `scripts/visual_check.py` (NudeNet-lite) integrado ao hook `visual_model_path` do risk scorecard — frames reais por clipe, score 0-100, `--auto-download-visual`.
- **Porta de publicação obrigatória (2.2)**: `scripts/upload_gate.py` recusa upload de clipes em publish_blocklist / safety_report / metadata inválida; adapters YouTube/TikTok/Instagram já passam pela porta (SDKs a ligar).
- **Metadata compliance (2.4)**: `scripts/metadata_compliance.py` (hashtags banidas, claims médicas/financeiras, clickbait, keyword stuffing).
- **Edição profissional (3.1–3.4)**: `scripts/polish.py` — jump cuts (silêncio+fillers), punch-in zoom, música de fundo com auto-duck, watermark + intro/outro; legendas re-sincronizadas (retime) e `burn_subtitles` prefere `final_polished/`.
- **Resumo crash-safe (4.2)**: `scripts/checkpoint.py` (`--checkpoint on`).
- **OOM Guard (4.1)**: `scripts/oom_guard.py` cai de modelo automaticamente.
- **Chave API segura (4.4)**: `scripts/secure_config.py` (env → Fernet → plaintext).
- **Crash reports privados (4.5)**: `scripts/crash_report.py` (opt-in).
- **CI real (4.3)**: ffmpeg no workflow + `tests/test_ci_smoke.py` com vídeo real.
- **Títulos A/B (5.3)**: `alt_titles`/`alt_captions` no prompt e nos segmentos.
- **Testes**: 196 → 286 (reais com ffmpeg).

## 🟣 v6.1 — Platform templates + verified build + hardening (2026-08-04)

### Novidades
- **Platform templates (Roadmap 5.2)**: `scripts/platform_templates.py` + `--platform {yt_shorts,tiktok,reels,yt_standard}` — define duration defaults/aspect per platform; saved to process_config.json.
- **Build verificado (1.1)**: `dist/ViralCutter` onefile (~300 MB) built & tested with PyInstaller 6.21 on Linux. Fixed a spec path bug (`ROOT`).
- **Hardening**: `transcribe_video.py` now imports torch optionally (binary runs without whisperx/torch); `doctor.py` checks onnxruntime/cryptography; requirements.txt += onnxruntime, cryptography.
- **i18n**: new v6 keys translated (ar_SA) + pt_BR/tr_TR synced.
- **WebUI plumbing**: `webui/pipeline.py` supports the v6 flags (Gradio fields still pending).
- **Testes**: 286 → **304**.

## 🟢 v6.2 — Ready-to-run fixes (2026-08-04)

- **Full install**: `requirements-transcribe.txt` (whisperx+torch) + `requirements-upload.txt` (YouTube OAuth); installers ask to install them.
- **Clear failure instead of silent placeholder**: transcription raises actionable ImportError when whisperx/torch missing; `--allow-placeholder-transcription` for testing only.
- **Real YouTube uploader**: full OAuth flow (client_secrets → token in ~/.viralcutter/yt_token.json), resumable upload, default privacyStatus=private.
- **WebUI fixed (was crashing on startup)**: implemented render_progress_html/render_tasks_html/render_error_html, GEMINI_MODELS/G4F_MODELS/get_local_models, apply_face_preset/apply_experimental_preset, template_choices/save_template/load_templates, subtitle-editor buttons + current_json_path; added visible v6 fields (platform/polish/music/logo/metadata gate).
- **Auto-update armed**: falls back to latest git tag when no Release exists; tag v0.9.0 pushed.
- doctor.py checks whisperx/torch; README_ar quickstart "3 steps to full pipeline".
- Testes: 304 → 309.

## 🔐 v6.3 — YouTube download UX (private / age-restricted videos)

- `--cookies-from-browser chrome|firefox|edge|...` + `--cookies file.txt` (yt-dlp auth) for private/age-restricted downloads.
- Friendly error messages instead of raw tracebacks: private video / age-restricted / unavailable / removed / invalid URL → actionable guidance + clean exit(1).
- Tests: 309 → 313.

## 🔐 v6.3b — Interactive cookies retry for private videos

- CLI: when a download fails as "private / age-restricted" and the user runs interactively, ViralCutter now ASKS "Retry using your Chrome browser cookies? (yes/no)" and retries automatically with --cookies-from-browser chrome. (TTY-only — the WebUI never hangs on a prompt.)
- WebUI: new "🔒 YouTube login (cookies)" dropdown (Chrome/Edge/Firefox) wired through build_command.
- Tests: 313 → 314.

## 🔧 v6.3c — Windows crash fixes (Chrome cookie noise + input_video=None)

- download_video: title extraction no longer forces Chrome cookies (removed the
  "Could not copy Chrome cookie database" noise on Windows, yt-dlp#7271) —
  cookies are used only when the user asks (--cookies-from-browser/--cookies).
- download_video: safety net — after all attempts, if the video file is missing/empty,
  fail loudly instead of returning a bogus path.
- main_improved: guard against input_video=None after a failed download → clean
  error message + exit(1) instead of `os.path.dirname(None)` TypeError.
- Tests: 314.

## 🐛 v6.3d — CRITICAL: fix download() returning None (Windows crash root cause)

- The v6.3 helper insertion accidentally nested the main download block inside
  `_print_friendly_and_exit` — download() silently returned None and the pipeline
  crashed at `os.path.dirname(None)`. download_video.py fully rewritten with the
  correct structure.
- Regression tests added: private video → AuthNeededError (never None); invalid URL → SystemExit.
- main_improved: guard placed BEFORE os.path.dirname + version banner at startup.
- Tests: 314 → 316.

## 🎨 v6.4 — Arabic WebUI: organization + performance + error reports

- **Error report display**: raw 30-line traceback tails are now summarized into
  scannable cards — title (ERROR line) + Arabic friendly hint (private video /
  whisperx / ffmpeg / 429 / OOM / cookies…) + collapsible technical details +
  exit code badge. (webui/utils.py summarize_error + render_error_html).
- **Performance**: logs list capped at 1000 lines (was unbounded O(n²) joins).
- **Organization**: v6 settings grouped into a labeled Accordion
  "✨ المونتاج الاحترافي والمنصات (v6)" with sub-sections (platform/publishing,
  editing quality, YouTube login).
- **Arabic**: all new WebUI labels translated to ar_SA (27 keys) + pt_BR/tr_TR synced.
- Tests: 316 → 322.

## 🤖 v6.5 — Gemini SDK fix (both libraries supported)

- create_viral_segments: works with EITHER `google-generativeai` (classic) or
  `google-genai` (new SDK) — auto-detects; requirements.txt now installs both.
- Actionable ImportError message (Arabic hint added to the WebUI error cards).
- WebUI error hints now match the real error line first (no more wrong hints
  from older log lines).
- Tests: 322 → 325.

## 🇩🇿 v6.5b — CRITICAL: Arabic video titles erased (folder collapse)

- sanitize_filename stripped non-Latin scripts (cp1252/ascii fallback) → Arabic
  titles became "" → every Arabic-titled project collapsed into VIRALS/ and
  overwrote input.mp4. Now keeps Unicode letters (Arabic/CJK/Latin), strips only
  reserved chars/emojis; empty → "Unknown_Video". + regression tests.
- Tests: 325 → 329.

## 🇩🇿🎬 v6.6 — Arabic titles + A/V sync fix + developer report

- **Arabic titles**: `--title-language ar` forces ALL AI output (titles, alt_titles,
  reasoning, captions) into Arabic regardless of video language; WebUI dropdown
  "🌐 لغة العناوين والكابشن" (auto/ar/en/fr/es/pt/de/tr).
- **A/V sync fix**: edit_video mux now uses -shortest + aresample=async=1 (audio
  follows the OpenCV-processed video timeline) + fps guard for VFR/broken metadata.
- **docs/ROADMAP_REPORT.md section 9**: developer handover report — what was fixed,
  prioritized remaining work (mediapipe guard, fonts, first Release, CI permission,
  TikTok/IG OAuth, deeper sync rework).
- Tests: 329 → 335.

## 🎙️ v6.7 — Whisper model fallback (large-v3-turbo unsupported on older faster-whisper)

- transcribe_video: resolve_model_candidates() — if the requested model (e.g.
  large-v3-turbo) is rejected as an invalid size, fall back to large-v3 → medium
  with a clear console note, instead of crashing.
- WebUI error hint for "invalid model size" (Arabic): update faster-whisper or
  pick large-v3/medium — and hints now correctly prefer the real error line.
- Tests: 335 → 339.

## 🛡️ v6.7b — Broken optional stack no longer kills the WebUI

- whisperx/torch import guards widened (any Exception, not just ModuleNotFoundError):
  a transformers/tokenizers version conflict no longer crashes the whole app/WebUI.
- subtitle_editor imports main_improved lazily (faster WebUI startup, less fragile).
- Tests: 339 → 341.

## 🔧 v6.7c — numpy<2 pin (whisperx/pyannote break on NumPy 2.x)

- requirements.txt + requirements-transcribe.txt now pin numpy<2 (np.NaN was
  removed in NumPy 2.0 → old pyannote.audio crashes).
- Arabic WebUI hint for the numpy conflict.
- Tests: 341 → 342.

## 🛠️ v6.8 — 403 handling + specific whisperx/torch diagnostics

- download_video: on HTTP 403 (Forbidden) → clear Arabic-adjacent guidance AND an
  automatic retry with alternative YouTube player clients (android/tv/web_safari).
- transcribe_video: the "stack missing" error now names WHICH import failed
  (whisperx vs torch) with a check command for each.
- WebUI hints: 403/Forbidden → update yt-dlp / use cookies / retry later.
- Tests: 342 → 343.
