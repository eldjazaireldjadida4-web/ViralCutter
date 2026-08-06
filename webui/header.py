import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKING_DIR = os.path.dirname(CURRENT_DIR)
sys.path.append(WORKING_DIR)

from i18n.i18n import I18nAuto, DEFAULT_LANGUAGE

i18n = I18nAuto(DEFAULT_LANGUAGE)

try:
    from app_version import VERSION
except Exception:
    VERSION = "?"

badges = ""

description = """
<div id="vc-header" style="text-align:center; direction: rtl; line-height: 1.8;">
  <h1 style="margin-bottom: 4px; font-size: 2.2em; color:#f8fafc;">✂️ ViralCutter</h1>
  <div style="margin-bottom: 14px;">
    <span style="background:linear-gradient(90deg,#f97316,#ea580c); color:#fff; border-radius:999px; padding:3px 14px; font-size:0.85em; font-weight:600;">v{version}</span>
  </div>
  <p style="font-size: 1.05em; margin-bottom: 18px; color: #cbd5e1;">
    أداة عربية لتحويل الفيديوهات الطويلة إلى مقاطع قصيرة بشكل أوضح وأبسط، مع سجل تشغيل، وتقدم دقيق، وتقارير أخطاء مفهومة، وواجهة أنظف.
  </p>
  <div style="display:inline-block; text-align:right; background:rgba(255,255,255,0.05); color:#e2e8f0; padding:18px 22px; border-radius:14px; margin-bottom:18px; max-width:900px; border:1px solid rgba(255,255,255,0.08);">
    <p style="margin-bottom:10px;"><strong>ماذا تستطيع أن تفعل هنا؟</strong></p>
    <ul style="margin:0; padding-right:20px; line-height:1.9;">
      <li>✂️ <strong>قص احترافي</strong>: استخراج المقاطع المهمة مع ضبط أفضل للوجه والتوقيت.</li>
      <li>📝 <strong>ترجمة وضبط شكلها</strong>: التحكم بخطوط الترجمة وموقعها ومعاينتها قبل الحفظ.</li>
      <li>🤖 <strong>دعم الذكاء الاصطناعي</strong>: Gemini وG4F والنماذج المحلية من نفس الواجهة.</li>
      <li>📱 <strong>مناسب للفيديو العمودي</strong>: تحسينات خاصة بـ Shorts وReels وTikTok.</li>
    </ul>
  </div>
  <p style="color:#94a3b8; margin:0;">واجهة عربية كاملة، مرتبة، ومصممة لتبقى واضحة أثناء المهام الطويلة.</p>
</div>
""".format(version=VERSION)