# -*- coding: utf-8 -*-
"""ViralCutter WebUI stylesheet (extracted from app.py for organization)."""

CSS = """
#logs_output textarea {
    min-height: 300px !important;
    max-height: 520px !important;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace !important;
    line-height: 1.6 !important;
}

.vc-topbar {
    position: sticky;
    top: 0;
    z-index: 20;
    background: rgba(2, 6, 23, 0.92);
    backdrop-filter: blur(10px);
    padding: 10px 0;
    margin-bottom: 12px;
    gap: 12px;
    align-items: center;
}

.vc-topbar > div,
.vc-topbar > button {
    flex: 0 0 auto !important;
}

.vc-panels > div {
    min-width: 0;
}

body, .gradio-container {
    background-color: #0b0b0b !important;
    color: #ffffff !important;
}

input[type="password"], textarea, select {
    background-color: #1f1f1f !important;
    color: #ffffff !important;
    border: 1px solid #333 !important;
}

footer {visibility: hidden}

.gradio-container {
    max-width: 98% !important;
    width: 98% !important;
    margin: 0 auto !important;
}

/* --- RTL layout for the Arabic UI ---
   Text fields keep per-content direction (URLs stay LTR) via plaintext bidi. */
body, .gradio-container {
    direction: rtl !important;
    font-family: "Cairo", "Tajawal", "Segoe UI", Tahoma, Arial, sans-serif !important;
}

/* Section headings inside the app: subtle separator for clean formatting */
.gradio-container h3 {
    margin-top: 16px !important;
    padding-bottom: 4px;
    border-bottom: 1px solid rgba(148, 163, 184, 0.18);
}

/* Header card: force light text regardless of Gradio theme defaults */
#vc-header, #vc-header p, #vc-header li, #vc-header strong, #vc-header ul {
    color: #e2e8f0 !important;
}
#vc-header h1 {
    color: #f8fafc !important;
}

.gradio-container input,
.gradio-container textarea {
    unicode-bidi: plaintext !important;
}

/* --- Tab bar: rounded pills, subtle dark surface (v6.15 UI polish) --- */
.gradio-container .tab-nav {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 14px !important;
    padding: 4px !important;
    margin-bottom: 14px !important;
    gap: 4px !important;
}
.gradio-container .tab-nav button {
    border-radius: 10px !important;
    border: none !important;
    background: transparent !important;
    color: #cbd5e1 !important;
    font-weight: 600 !important;
    padding: 8px 14px !important;
    transition: all 0.15s ease;
}
.gradio-container .tab-nav button:hover {
    background: rgba(255,255,255,0.07) !important;
    color: #f1f5f9 !important;
}
.gradio-container .tab-nav button.selected {
    background: linear-gradient(90deg, #f97316, #ea580c) !important;
    color: #fff !important;
}

/* --- Top action bar: glass card --- */
.vc-topbar {
    background: rgba(255,255,255,0.05) !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 14px !important;
    padding: 10px 14px !important;
}

/* --- Progress/tasks/errors panels: subtle cards --- */
.vc-panels > div {
    background: rgba(255,255,255,0.03) !important;
    border: 1px solid rgba(255,255,255,0.06) !important;
    border-radius: 12px !important;
    padding: 10px 12px !important;
}
.vc-panels h3 {
    border-bottom: none !important;
    margin-top: 0 !important;
}

/* --- Primary CTA gets a gradient --- */
.vc-topbar button.primary {
    background: linear-gradient(90deg, #f97316, #ea580c) !important;
    border: none !important;
    color: #fff !important;
    font-weight: 700 !important;
}

/* --- Subtle scrollbar for the log --- */
#logs_output textarea::-webkit-scrollbar { width: 8px; }
#logs_output textarea::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }
"""
