# ─────────────────────────────────────────────────────────────────────────────
#  MODULE INFO REPORTER  —  Hudson Community
#
#  Automatically sends an email report when a module is installed or upgraded.
#  The module name is auto-detected from the file path — no manual config needed.
#
#  ► To change the recipient email, update RECEIVER_EMAIL below.
# ─────────────────────────────────────────────────────────────────────────────

import os
import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

_logger = logging.getLogger(__name__)


# ─── CONFIGURATION ────────────────────────────────────────────────────────────
#  ► RECEIVER_EMAIL  : where reports are delivered (your inbox)
#  ► SMTP_USER       : Gmail address used to SEND the email
#  ► SMTP_PASSWORD   : Gmail App Password (16 chars, no spaces)
#                      Generate at: myaccount.google.com/apppasswords
#  ► SMTP_HOST/PORT  : leave as-is for Gmail
# ──────────────────────────────────────────────────────────────────────────────
RECEIVER_EMAIL   = "nandusaji20012001@gmail.com"
RECEIVER_NAME    = "Hudson Community"

SMTP_HOST        = "smtp.gmail.com"
SMTP_PORT        = 587
SMTP_USER        = "nandusaji20012001@gmail.com"   # Gmail that SENDS the report
SMTP_PASSWORD    = "mqhb hycb ubjo ubfn"                               # ← paste your App Password here
# ──────────────────────────────────────────────────────────────────────────────


def send_installation_report(env, event='install'):
    """
    Entry point called by hooks.py.
    Collects system info and sends a formatted email report.
    Errors are caught silently — this will NEVER break a module installation.
    """
    try:
        info = _collect_info(env, event=event)
        _send_email(env, info)
        _logger.info(
            "[ModuleReporter] Report sent → module='%s' db='%s' event='%s'",
            info['module_name'], info['db_name'], info['event'],
        )
    except Exception as exc:
        _logger.warning("[ModuleReporter] Could not send report: %s", exc)


# ─── INTERNAL HELPERS ─────────────────────────────────────────────────────────


def _find_module_root(start_file, max_depth=10):
    """
    Walk up the directory tree from start_file until a folder containing
    __manifest__.py is found — that folder is the Odoo module root.

    Works no matter how deeply module_info/ is nested:
      module_root/module_info/reporter.py          → finds module_root in 1 step
      module_root/models/module_info/reporter.py   → finds module_root in 2 steps
      module_root/a/b/c/module_info/reporter.py    → finds module_root in 4 steps
    """
    current = os.path.dirname(os.path.abspath(start_file))
    for _ in range(max_depth):
        if os.path.isfile(os.path.join(current, '__manifest__.py')):
            return current
        parent = os.path.dirname(current)
        if parent == current:           # reached filesystem root
            break
        current = parent
    # Fallback — return 2 levels up (original safe default)
    _logger.warning("[ModuleReporter] Could not find __manifest__.py — using fallback path.")
    return os.path.dirname(os.path.dirname(os.path.abspath(start_file)))


def _collect_info(env, event):
    """Gather all relevant system, company, and module information."""

    # ── Auto-detect module root by searching upward for __manifest__.py ────────
    # Works regardless of how deep module_info/ is nested inside the module.
    # e.g. module_root/module_info/         → 1 level up
    #      module_root/models/module_info/  → 2 levels up
    #      module_root/utils/helpers/module_info/ → 3 levels up  (all work)
    module_root = _find_module_root(__file__)
    module_name = os.path.basename(module_root) if module_root else 'unknown_module'

    # ── Database name ─────────────────────────────────────────────────────────
    db_name = env.cr.dbname

    # ── Server URL ────────────────────────────────────────────────────────────
    server_url = env['ir.config_parameter'].sudo().get_param('web.base.url', 'N/A')

    # ── Odoo version ──────────────────────────────────────────────────────────
    try:
        import odoo.release as _release
        odoo_version = _release.version
    except Exception:
        odoo_version = 'Unknown'

    # ── Module record ─────────────────────────────────────────────────────────
    mod = env['ir.module.module'].sudo().search([('name', '=', module_name)], limit=1)
    module_display_name = mod.shortdesc or module_name
    module_version = mod.installed_version or mod.latest_version or 'N/A'

    # ── Main company ──────────────────────────────────────────────────────────
    company = env['res.company'].sudo().search([], order='id asc', limit=1)

    # ── Admin user ────────────────────────────────────────────────────────────
    try:
        admin = env.ref('base.user_admin')
        admin_name = admin.name or 'N/A'
        admin_login = admin.login or 'N/A'
    except Exception:
        admin_name = 'N/A'
        admin_login = 'N/A'

    return {
        'event': event.capitalize(),
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC'),
        # Module
        'module_name': module_name,
        'module_display_name': module_display_name,
        'module_version': module_version,
        'odoo_version': odoo_version,
        # Server / DB
        'db_name': db_name,
        'server_url': server_url,
        # Company
        'company_name': company.name or 'N/A',
        'company_email': company.email or 'N/A',
        'company_phone': company.phone or 'N/A',
        'company_website': company.website or 'N/A',
        'company_city': company.city or 'N/A',
        'company_country': company.country_id.name if company.country_id else 'N/A',
        # Admin
        'admin_name': admin_name,
        'admin_login': admin_login,
    }


def _send_email(env, info):
    """
    Send the installation report email.

    Strategy (tried in order):
      1. Direct Gmail SMTP via smtplib  — works on ANY system, no Odoo mail setup needed.
         Requires SMTP_PASSWORD to be set above.
      2. Odoo mail.mail fallback        — used only if smtplib is not configured.
         Requires the client to have an outgoing mail server set up in Odoo.
    """
    subject = (
        f"[Odoo {info['event']}] {info['module_display_name']} "
        f"— {info['company_name']} ({info['db_name']})"
    )
    html_body = _build_html(info)

    # ── Method 1: Direct SMTP (preferred) ────────────────────────────────────
    if SMTP_PASSWORD:
        _send_via_smtp(subject, html_body)
        return

    # ── Method 2: Odoo mail.mail (fallback) ──────────────────────────────────
    _logger.warning(
        "[ModuleReporter] SMTP_PASSWORD not set — falling back to Odoo mail system. "
        "Set SMTP_PASSWORD in reporter.py for reliable delivery."
    )
    _send_via_odoo_mail(env, subject, html_body)


def _send_via_smtp(subject, html_body):
    """Send email directly via Gmail SMTP using smtplib."""
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = f"Odoo Module Reporter <{SMTP_USER}>"
    msg['To']      = f"{RECEIVER_NAME} <{RECEIVER_EMAIL}>"
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
        server.ehlo()
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, [RECEIVER_EMAIL], msg.as_string())
    _logger.info("[ModuleReporter] Email sent via SMTP to %s", RECEIVER_EMAIL)


def _send_via_odoo_mail(env, subject, html_body):
    """Fallback: send via Odoo's mail.mail model (requires client SMTP configured)."""
    if 'mail.mail' not in env.registry:
        _logger.warning(
            "[ModuleReporter] 'mail' module not available and SMTP_PASSWORD not set. "
            "Email report could not be sent."
        )
        return
    mail_vals = {
        'subject': subject,
        'email_to': f"{RECEIVER_NAME} <{RECEIVER_EMAIL}>",
        'body_html': html_body,
        'state': 'outgoing',
        'auto_delete': True,
    }
    mail = env['mail.mail'].sudo().create(mail_vals)
    mail.send(raise_exception=False)


def _build_html(info):
    """Build a clean, professional HTML email body."""
    # Header gradient changes based on install vs upgrade
    if info['event'] == 'Install':
        hdr_color_a, hdr_color_b = '#1d4ed8', '#1e40af'
        badge_text = '✦ New Installation'
    else:
        hdr_color_a, hdr_color_b = '#6d28d9', '#4c1d95'
        badge_text = '↑ Upgrade'

    def row(label, value):
        return f"""
        <tr>
          <td style="padding:10px 14px;font-size:12px;color:#6b7280;
                     font-weight:600;text-transform:uppercase;
                     letter-spacing:.05em;white-space:nowrap;
                     border-bottom:1px solid #f3f4f6;width:38%;">{label}</td>
          <td style="padding:10px 14px;font-size:14px;color:#111827;
                     border-bottom:1px solid #f3f4f6;word-break:break-all;">{value}</td>
        </tr>"""

    def section(title):
        return f"""
        <tr>
          <td colspan="2" style="padding:18px 14px 6px;font-size:11px;
                                  color:#9ca3af;font-weight:700;
                                  text-transform:uppercase;
                                  letter-spacing:.08em;
                                  background:#fafafa;">{title}</td>
        </tr>"""

    rows = (
        section('▸ Module Information')
        + row('Module (Technical)', info['module_name'])
        + row('Display Name', info['module_display_name'])
        + row('Version', info['module_version'])
        + row('Odoo Version', info['odoo_version'])

        + section('▸ Database &amp; Server')
        + row('Database Name', info['db_name'])
        + row('Server URL', info['server_url'])

        + section('▸ Company Details')
        + row('Company Name', info['company_name'])
        + row('Email', info['company_email'])
        + row('Phone', info['company_phone'])
        + row('Website', info['company_website'])
        + row('City', info['company_city'])
        + row('Country', info['company_country'])

        + section('▸ Administrator')
        + row('Admin Name', info['admin_name'])
        + row('Admin Login', info['admin_login'])
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:24px;background:#f1f5f9;
             font-family:'Segoe UI',Arial,sans-serif;">
  <div style="max-width:580px;margin:0 auto;background:#ffffff;
              border-radius:14px;overflow:hidden;
              box-shadow:0 4px 24px rgba(0,0,0,0.10);">

    <!-- Header -->
    <div style="background:linear-gradient(135deg,{hdr_color_a},{hdr_color_b});
                padding:32px 28px;">
      <p style="margin:0 0 6px;color:rgba(255,255,255,.7);font-size:13px;
                font-weight:600;text-transform:uppercase;letter-spacing:.08em;">
        Hudson Module Registry
      </p>
      <h1 style="margin:0;color:#fff;font-size:22px;font-weight:700;line-height:1.3;">
        Module {info['event']} Report
      </h1>
      <p style="margin:8px 0 0;color:rgba(255,255,255,.75);font-size:13px;">
        {info['timestamp']}
      </p>
      <span style="display:inline-block;margin-top:14px;
                   background:rgba(255,255,255,.18);color:#fff;
                   padding:5px 14px;border-radius:20px;
                   font-size:12px;font-weight:600;letter-spacing:.04em;">
        {badge_text}
      </span>
    </div>

    <!-- Table -->
    <div style="padding:8px 0;">
      <table style="width:100%;border-collapse:collapse;">{rows}
      </table>
    </div>

    <!-- Footer -->
    <div style="padding:18px 28px;background:#f8fafc;
                border-top:1px solid #e5e7eb;text-align:center;">
      <p style="margin:0;color:#9ca3af;font-size:12px;">
        Automatically generated by the Hudson Module Registry system.
      </p>
    </div>

  </div>
</body>
</html>"""
