"""Generate a self-contained HTML pipeline dashboard from LoreConvo DB.

Usage:
    python scripts/generate_pipeline_dashboard.py

Output:
    ~/Documents/Claude/OPPORTUNITY_PIPELINE.html

Called automatically at the end of Scout, Gina, and Ron sessions.
Can also be run manually at any time.
"""

import sqlite3
import json
import os
import glob
from datetime import datetime


def find_db():
    native = os.path.expanduser('~/.loreconvo/sessions.db')
    if os.path.exists(native):
        return native
    for p in glob.glob('/sessions/*/mnt/.loreconvo/sessions.db'):
        return p
    return native


def find_output_path():
    # ~/Documents/Claude/OPPORTUNITY_PIPELINE.html
    native = os.path.expanduser('~/Documents/Claude/OPPORTUNITY_PIPELINE.html')
    # Also check Cowork VM mount
    for p in glob.glob('/sessions/*/mnt'):
        # Try to find the Documents/Claude path via the Cowork workspace
        candidate = os.path.join(p, '.loreconvo')
        if os.path.exists(candidate):
            # Use the native path -- this runs on Mac
            return native
    return native


def extract_tag(tags, prefix):
    for t in tags:
        if t.startswith(f'{prefix}:'):
            return t.split(':', 1)[1]
    return None


STATUS_ORDER = [
    'scouted', 'approved-for-review', 'architecture-proposed',
    'approved', 'in-progress', 'on-hold', 'completed', 'rejected', 'archived'
]

STATUS_COLORS = {
    'scouted':                '#6c757d',
    'approved-for-review':    '#0d6efd',
    'architecture-proposed':  '#6f42c1',
    'approved':               '#198754',
    'in-progress':            '#fd7e14',
    'on-hold':                '#ffc107',
    'completed':              '#20c997',
    'rejected':               '#dc3545',
    'archived':               '#adb5bd',
}

EFFORT_LABELS = {
    '1': 'Afternoon',
    '2': 'Half-day',
    '3': 'Weekend',
    '5': 'Several days',
    '8': 'Full week',
    '13': 'Multi-week',
}


def load_pipeline(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT id, title, tags, summary, decisions, open_questions, start_date
        FROM sessions WHERE surface='pipeline' AND id NOT LIKE 'REF%'
        ORDER BY id
    """).fetchall()

    items = []
    for r in rows:
        tags = json.loads(r['tags']) if r['tags'] else []
        status = extract_tag(tags, 'status') or 'unknown'
        priority = extract_tag(tags, 'priority') or '-'
        effort_raw = extract_tag(tags, 'effort') or '-'
        effort = EFFORT_LABELS.get(effort_raw, effort_raw)
        hold_reason = extract_tag(tags, 'hold-reason')
        disposition = extract_tag(tags, 'disposition')

        decisions = r['decisions'] or ''
        open_q = r['open_questions'] or ''

        items.append({
            'id': r['id'],
            'title': r['title'],
            'status': status,
            'priority': priority,
            'effort': effort,
            'hold_reason': hold_reason,
            'disposition': disposition,
            'summary': r['summary'] or '',
            'decisions': decisions,
            'open_questions': open_q,
            'scouted': r['start_date'] or '',
        })

    conn.close()
    return items


def status_badge(status):
    color = STATUS_COLORS.get(status, '#6c757d')
    return (
        f'<span style="background:{color};color:#fff;padding:3px 10px;'
        f'border-radius:12px;font-size:0.78em;font-weight:600;'
        f'white-space:nowrap">{status}</span>'
    )


def priority_badge(priority):
    colors = {'P1': '#dc3545', 'P2': '#fd7e14', 'P3': '#ffc107',
              'P4': '#0d6efd', 'P5': '#6c757d'}
    color = colors.get(priority, '#6c757d')
    return (
        f'<span style="background:{color};color:#fff;padding:3px 8px;'
        f'border-radius:4px;font-size:0.78em;font-weight:700">{priority}</span>'
    )


def generate_html(items, generated_at):
    active = [i for i in items if i['status'] not in ('rejected', 'archived')]
    inactive = [i for i in items if i['status'] in ('rejected', 'archived')]

    # Status counts for summary bar
    status_counts = {}
    for i in items:
        status_counts[i['status']] = status_counts.get(i['status'], 0) + 1

    summary_pills = ''
    for s in STATUS_ORDER:
        if s in status_counts:
            color = STATUS_COLORS.get(s, '#6c757d')
            summary_pills += (
                f'<span style="background:{color};color:#fff;padding:4px 12px;'
                f'border-radius:14px;font-size:0.82em;font-weight:600;margin:3px">'
                f'{s} ({status_counts[s]})</span>'
            )

    # Build rows for active table
    table_rows = ''
    for item in active:
        hold_note = ''
        if item['hold_reason']:
            readable = item['hold_reason'].replace('-', ' ')
            hold_note = (
                f'<br><span style="color:#856404;font-size:0.8em">'
                f'Hold: {readable}</span>'
            )

        oq_snippet = ''
        if item['open_questions']:
            oq_lines = [l.strip() for l in item['open_questions'].split('\n') if l.strip()]
            if oq_lines:
                last = oq_lines[-1][:120]
                oq_snippet = (
                    f'<br><span style="color:#666;font-size:0.78em;font-style:italic">'
                    f'{last}{"..." if len(oq_lines[-1]) > 120 else ""}</span>'
                )

        summary_short = item['summary'][:140] + ('...' if len(item['summary']) > 140 else '')

        table_rows += f"""
        <tr>
          <td style="font-weight:700;white-space:nowrap;color:#333">{item['id']}</td>
          <td><strong>{item['title']}</strong>{hold_note}{oq_snippet}</td>
          <td>{status_badge(item['status'])}</td>
          <td style="text-align:center">{priority_badge(item['priority'])}</td>
          <td style="font-size:0.85em;color:#555;white-space:nowrap">{item['effort']}</td>
          <td style="font-size:0.82em;color:#666">{summary_short}</td>
          <td style="font-size:0.82em;color:#888;white-space:nowrap">{item['scouted']}</td>
        </tr>"""

    inactive_rows = ''
    for item in inactive:
        inactive_rows += f"""
        <tr>
          <td style="font-weight:700">{item['id']}</td>
          <td>{item['title']}</td>
          <td>{status_badge(item['status'])}</td>
          <td style="font-size:0.85em;color:#666">{item['disposition'] or '-'}</td>
          <td style="font-size:0.82em;color:#888">{item['scouted']}</td>
        </tr>"""

    inactive_section = ''
    if inactive_rows:
        inactive_section = f"""
        <h2 style="color:#666;margin-top:40px">Rejected / Archived</h2>
        <table style="width:100%;border-collapse:collapse;font-family:sans-serif">
          <thead>
            <tr style="background:#f8f9fa;text-align:left">
              <th style="{th()}">ID</th>
              <th style="{th()}">Name</th>
              <th style="{th()}">Status</th>
              <th style="{th()}">Disposition</th>
              <th style="{th()}">Scouted</th>
            </tr>
          </thead>
          <tbody>{inactive_rows}</tbody>
        </table>"""

    pipeline_stages = ''
    for s in ['scouted', 'approved-for-review', 'architecture-proposed',
              'approved', 'in-progress', 'on-hold', 'completed']:
        color = STATUS_COLORS.get(s, '#6c757d')
        owners = {
            'scouted': 'Scout',
            'approved-for-review': 'Debbie',
            'architecture-proposed': 'Gina',
            'approved': 'Debbie',
            'in-progress': 'Ron',
            'on-hold': 'Debbie',
            'completed': 'Ron/Debbie',
        }
        owner = owners.get(s, '')
        pipeline_stages += (
            f'<div style="display:flex;align-items:center;margin:6px 0">'
            f'<span style="background:{color};color:#fff;padding:3px 10px;'
            f'border-radius:12px;font-size:0.82em;font-weight:600;width:200px;'
            f'display:inline-block;text-align:center">{s}</span>'
            f'<span style="margin-left:12px;font-size:0.85em;color:#555">{owner}</span>'
            f'</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Opportunity Pipeline - Labyrinth Analytics</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          max-width: 1200px; margin: 0 auto; padding: 24px; background: #f5f5f5; color: #333; }}
  h1 {{ color: #1a1a2e; margin-bottom: 4px; }}
  h2 {{ color: #333; margin-top: 32px; }}
  .meta {{ color: #888; font-size: 0.85em; margin-bottom: 24px; }}
  .card {{ background: #fff; border-radius: 10px; padding: 24px;
           box-shadow: 0 2px 8px rgba(0,0,0,0.07); margin-bottom: 24px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ background: #1a1a2e; color: #fff; padding: 10px 12px;
        text-align: left; font-size: 0.83em; font-weight: 600; }}
  td {{ padding: 10px 12px; border-bottom: 1px solid #f0f0f0; vertical-align: top; }}
  tr:hover td {{ background: #fafafa; }}
  .summary-bar {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 12px 0 24px; }}
  .legend {{ display: flex; flex-direction: column; }}
</style>
</head>
<body>
<h1>Opportunity Pipeline</h1>
<div class="meta">
  Labyrinth Analytics Consulting &nbsp;|&nbsp;
  Generated: {generated_at} &nbsp;|&nbsp;
  Source: ~/.loreconvo/sessions.db &nbsp;|&nbsp;
  {len(items)} total opportunities
</div>

<div class="card">
  <strong>Status Summary</strong>
  <div class="summary-bar">{summary_pills}</div>
</div>

<div style="display:grid;grid-template-columns:1fr 280px;gap:24px">
<div>
<div class="card">
<h2 style="margin-top:0">Active Pipeline</h2>
<table>
  <thead>
    <tr>
      <th style="width:80px">ID</th>
      <th>Name</th>
      <th style="width:180px">Status</th>
      <th style="width:60px;text-align:center">Pri</th>
      <th style="width:110px">Effort</th>
      <th>Scout Summary</th>
      <th style="width:90px">Scouted</th>
    </tr>
  </thead>
  <tbody>{table_rows}</tbody>
</table>
{inactive_section}
</div>
</div>

<div>
<div class="card">
  <strong>Pipeline Stages</strong>
  <div style="margin-top:12px" class="legend">{pipeline_stages}</div>
</div>
<div class="card" style="margin-top:0">
  <strong>Effort Scale (Fibonacci)</strong>
  <table style="margin-top:8px">
    {''.join(f"<tr><td style='font-weight:700;padding:4px 8px'>{k}</td><td style='padding:4px 8px;color:#555'>{v}</td></tr>"
             for k, v in EFFORT_LABELS.items())}
  </table>
</div>
<div class="card" style="margin-top:0;font-size:0.82em;color:#666">
  <strong>How to update</strong><br><br>
  Ask Claude in any Cowork session to move an opportunity to a new status.
  This dashboard regenerates automatically at the end of Scout, Gina, and Ron sessions.
  <br><br>
  <strong>Valid statuses:</strong><br>
  scouted &rarr; approved-for-review &rarr; architecture-proposed &rarr; approved &rarr; in-progress &rarr; completed<br><br>
  Or at any Debbie review point: on-hold, rejected, archived
</div>
</div>
</div>

</body>
</html>"""


def th():
    return "padding:10px 12px;text-align:left;font-size:0.83em;font-weight:600"


def main():
    db_path = find_db()
    if not os.path.exists(db_path):
        print(f"ERROR: Database not found at {db_path}")
        return

    items = load_pipeline(db_path)
    generated_at = datetime.now().strftime('%Y-%m-%d %H:%M')
    html = generate_html(items, generated_at)

    out_path = find_output_path()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    with open(out_path, 'w') as f:
        f.write(html)

    print(f"Dashboard generated: {out_path}")
    print(f"  {len(items)} opportunities loaded from {db_path}")
    return out_path


if __name__ == '__main__':
    main()
