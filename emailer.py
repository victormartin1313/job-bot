"""Email digest of high-scoring new jobs to Victor."""

from __future__ import annotations

import smtplib
import sqlite3
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

TO_ADDRESS = "vamartin@me.com"


def _score_color(score: float) -> str:
    if score >= 80:
        return "#2e7d32"   # dark green
    elif score >= 65:
        return "#e65100"   # orange
    return "#555555"


def _source_label(source: str) -> str:
    labels = {
        "linkedin": "LinkedIn",
        "indeed": "Indeed",
        "handshake": "Handshake",
        "deloitte": "Deloitte",
        "ey": "EY",
        "pwc": "PwC",
        "kpmg": "KPMG",
        "rsm": "RSM",
        "bdo": "BDO",
        "grant_thornton": "Grant Thornton",
        "moss_adams": "Moss Adams",
        "cla": "CLA",
    }
    return labels.get(source.lower(), source.title())


def build_html(jobs: list[sqlite3.Row]) -> str:
    date_str = datetime.now().strftime("%B %d, %Y")
    rows = ""
    for _job in jobs:
        job = dict(_job)
        score = job["score"]
        color = _score_color(score)
        source = _source_label(job["source"])
        location = job["location"] or "Location not listed"
        rows += f"""
        <tr>
          <td style="padding:12px 8px; border-bottom:1px solid #eee;">
            <a href="{job['url']}" style="font-size:15px; font-weight:600;
               color:#1a237e; text-decoration:none;">{job['title']}</a><br>
            <span style="color:#333; font-size:13px;">{job['company']}</span>
            <span style="color:#888; font-size:12px;"> &mdash; {location}</span>
          </td>
          <td style="padding:12px 8px; border-bottom:1px solid #eee;
              text-align:center; white-space:nowrap;">
            <span style="background:{color}; color:#fff; border-radius:12px;
              padding:3px 10px; font-size:13px; font-weight:700;">
              {score:.0f}
            </span>
          </td>
          <td style="padding:12px 8px; border-bottom:1px solid #eee;
              color:#555; font-size:12px; white-space:nowrap;">
            {source}
          </td>
          <td style="padding:12px 8px; border-bottom:1px solid #eee;">
            <a href="{job['url']}" style="background:#1a237e; color:#fff;
               border-radius:6px; padding:5px 12px; font-size:12px;
               text-decoration:none; white-space:nowrap;">Apply →</a>
          </td>
        </tr>"""

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
             background:#f5f5f5; margin:0; padding:24px;">
  <div style="max-width:700px; margin:0 auto; background:#fff;
              border-radius:10px; box-shadow:0 2px 8px rgba(0,0,0,.08); overflow:hidden;">

    <div style="background:#1a237e; padding:24px 28px;">
      <h1 style="color:#fff; margin:0; font-size:20px; font-weight:700;">
        Job Matches — {date_str}
      </h1>
      <p style="color:#c5cae9; margin:6px 0 0; font-size:13px;">
        {len(jobs)} new role{"s" if len(jobs) != 1 else ""} above your score threshold
      </p>
    </div>

    <div style="padding:0 16px 16px;">
      <table style="width:100%; border-collapse:collapse;">
        <thead>
          <tr style="background:#f8f8f8;">
            <th style="padding:10px 8px; text-align:left; font-size:12px;
                color:#888; font-weight:600; text-transform:uppercase;">Role</th>
            <th style="padding:10px 8px; text-align:center; font-size:12px;
                color:#888; font-weight:600; text-transform:uppercase;">Score</th>
            <th style="padding:10px 8px; text-align:left; font-size:12px;
                color:#888; font-weight:600; text-transform:uppercase;">Source</th>
            <th style="padding:10px 8px;"></th>
          </tr>
        </thead>
        <tbody>
          {rows}
        </tbody>
      </table>
    </div>

    <div style="background:#f8f8f8; padding:16px 28px; border-top:1px solid #eee;">
      <p style="margin:0; font-size:12px; color:#888;">
        Run <code>python3 main.py review</code> to browse and save jobs locally.
      </p>
    </div>
  </div>
</body>
</html>"""


def send_digest(jobs: list[sqlite3.Row], smtp_cfg: dict) -> bool:
    """Send job digest email. Returns True on success."""
    if not jobs:
        return False

    smtp_host = smtp_cfg.get("smtp_host", "smtp.mail.me.com")
    smtp_port = int(smtp_cfg.get("smtp_port", 587))
    smtp_user = smtp_cfg.get("smtp_user", "")
    smtp_password = smtp_cfg.get("smtp_password", "")

    if not smtp_user or not smtp_password:
        print("Email credentials not configured — skipping email.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Job Matches ({len(jobs)} new) — {datetime.now().strftime('%b %d')}"
    msg["From"] = smtp_user
    msg["To"] = TO_ADDRESS

    # Plain-text fallback
    plain = f"New job matches — {datetime.now().strftime('%B %d, %Y')}\n\n"
    for job in jobs:
        j = dict(job)
        plain += f"[{j['score']:.0f}] {j['title']} @ {j['company']}\n"
        plain += f"  {j.get('location', '')}\n"
        plain += f"  {j['url']}\n\n"

    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(build_html(jobs), "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        return True
    except Exception as exc:
        print(f"Email send failed: {exc}")
        return False
