"""Learn & Performance panels for the WebUI.

Thin handlers that wrap the CLI modules (scripts.strike_feedback / scripts
.analytics) so the WebUI can call them IN-PROCESS — no subprocess, works in
both source runs and the packaged exe (modules are bundled).

Every handler returns a plain string to show in a Textbox and never raises
raw exceptions: failures come back as a readable message.
"""

import os


def _strike():
    from scripts import strike_feedback
    return strike_feedback


def list_terms():
    try:
        sf = _strike()
        terms = sf.load_terms()
        lines = ["Custom BLOCK terms (extra_terms): %d" % len(terms["extra_terms"])]
        for t in terms["extra_terms"]:
            lines.append("  • %s  (lang=%s, sev=%s, cat=%s)" % (
                t["term"], t.get("lang", "?"), t.get("severity", "?"),
                t.get("category", "?")))
        lines.append("")
        lines.append("ALLOW terms (false-positive fixes): %d" % len(terms["allow_terms"]))
        for t in terms["allow_terms"]:
            lines.append("  • %s" % t)
        return "\n".join(lines)
    except Exception as e:
        return "❌ Could not read the term list: %s" % e


def add_term(term, severity="high", reason=""):
    if not term or not term.strip():
        return "❌ Enter a term first."
    try:
        sf = _strike()
        sf.cmd_add(term.strip(), severity=severity or "high",
                   reason=(reason or "").strip() or None)
        return "✅ Learned '%s' (severity=%s) — the safety filter now blocks it on every run." % (
            term.strip(), severity or "high")
    except Exception as e:
        return "❌ %s" % e


def allow_term(term, reason=""):
    if not term or not term.strip():
        return "❌ Enter a term first."
    try:
        sf = _strike()
        sf.cmd_allow(term.strip(), reason=(reason or "").strip() or None)
        return "✅ Allowed '%s' — excluded from the built-in blocklist." % term.strip()
    except Exception as e:
        return "❌ %s" % e


def remove_term(term):
    if not term or not term.strip():
        return "❌ Enter a term first."
    try:
        sf = _strike()
        ok = sf.cmd_remove(term.strip())
        if not ok:
            ok = sf.cmd_remove(term.strip(), allow=True)
        return "✅ Removed '%s'" % term.strip() if ok else "Not found — nothing to remove."
    except Exception as e:
        return "❌ %s" % e


def show_stats():
    try:
        sf = _strike()
        s = sf.cmd_stats()
        lines = [
            "📓 Learning journal:",
            "  events:          %d" % s["events"],
            "  by action:       %s" % s["by_action"],
            "  by severity:     %s" % s["by_severity"],
            "  by month:        %s" % s["by_month"],
            "  last event:      %s" % (s["last_event"] or "—"),
            "  active block:    %d terms" % s["active_extra_terms"],
            "  active allow:    %d terms" % s["active_allow_terms"],
        ]
        return "\n".join(lines)
    except Exception as e:
        return "❌ %s" % e


def extract_from_project(project_name, apply=False, virals_dir=None):
    if not project_name:
        return "❌ Select a project first."
    base = virals_dir or os.path.join(os.getcwd(), "VIRALS")
    project_folder = os.path.join(base, project_name)
    if not os.path.isdir(project_folder):
        return "❌ Project folder not found: %s" % project_folder
    try:
        sf = _strike()
        found = sf.extract_terms_from_project(project_folder)
        if not found:
            return "No patterns found — this project has no safety/risk reports or no blocked clips."
        lines = ["Patterns behind the blocked clips (%s):" % project_name]
        for f in found:
            lines.append("  • %-24s sev=%-6s x%d" % (f["term"], f["severity"], f["count"]))
        if apply:
            added = 0
            for f in found:
                try:
                    sf.cmd_add(f["term"], lang="auto", severity=f["severity"],
                               category="learned",
                               reason="learned from WebUI (project %s)" % project_name,
                               source="scorecard", project=project_folder)
                    added += 1
                except Exception:
                    pass
            lines.append("")
            lines.append("✅ Learned %d term(s) — next runs will block them earlier." % added)
        else:
            lines.append("")
            lines.append("(tick 'Apply' and run again to teach them to the tool)")
        return "\n".join(lines)
    except Exception as e:
        return "❌ %s" % e


def run_analytics(kind, days=28):
    """Run a YouTube Analytics query in-process. kind: summary|top|trends."""
    try:
        from scripts import analytics
        ya, yt = analytics._build_services()
    except Exception as e:
        return ("❌ Analytics is not configured yet: %s\n\n"
                "Setup: 1) client_secrets.json (Google OAuth desktop app)  "
                "2) enable 'YouTube Data API v3' + 'YouTube Analytics API'  "
                "3) the first run opens a browser to authorize (read-only)." % e)
    try:
        if kind == "top":
            return analytics.format_top(analytics.fetch_top_videos(ya, yt, days=days))
        if kind == "trends":
            return analytics.format_trends(analytics.fetch_trends(ya, days=days))
        return analytics.format_summary(analytics.fetch_summary(ya, days=days))
    except Exception as e:
        return "❌ Analytics query failed: %s" % e
