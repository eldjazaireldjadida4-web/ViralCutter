# Changelog

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
