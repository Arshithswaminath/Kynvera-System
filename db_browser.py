"""
Injaaz App — Database Browser (User-Friendly Edition)
Run: python db_browser.py
Then open: http://localhost:8765
"""

import csv
import io
import json
import http.server
import webbrowser
import threading
import urllib.parse
from datetime import datetime, date
from decimal import Decimal

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("Installing psycopg2-binary...")
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "psycopg2-binary"])
    import psycopg2
    import psycopg2.extras

# ── CONFIG ──────────────────────────────────────────────────────────────────
DATABASE_URL = "postgresql://injaaz_db_t2rb_user:BxwqYHt2GiA6uenC9PkjgebiIE2ydut8@dpg-d6sheakr85hc73esmetg-a.oregon-postgres.render.com/injaaz_db_t2rb"
PORT = 8765
# ────────────────────────────────────────────────────────────────────────────

# Friendly metadata for each table
TABLE_META = {
    "users":                      {"icon": "👤", "label": "Team Members",         "desc": "All user accounts and their roles"},
    "submissions":                {"icon": "📋", "label": "Submissions",           "desc": "Form submissions from all modules"},
    "jobs":                       {"icon": "🔧", "label": "Jobs",                  "desc": "Work orders and job tracking"},
    "files":                      {"icon": "📁", "label": "Files",                 "desc": "Uploaded documents and attachments"},
    "audit_logs":                 {"icon": "🔍", "label": "Activity Log",          "desc": "Record of all system actions"},
    "sessions":                   {"icon": "🔐", "label": "Login Sessions",        "desc": "Active and past user sessions"},
    "devices":                    {"icon": "📱", "label": "Devices",               "desc": "Registered devices"},
    "bd_projects":                {"icon": "🏗️",  "label": "BD Projects",          "desc": "Business development projects"},
    "bd_followups":               {"icon": "📞", "label": "BD Follow-ups",         "desc": "Follow-up actions on BD projects"},
    "bd_contacts":                {"icon": "👥", "label": "BD Contacts",           "desc": "Business development contacts"},
    "bd_activities":              {"icon": "📊", "label": "BD Activities",         "desc": "Business development activity log"},
    "admin_personal_projects":    {"icon": "⭐", "label": "Admin Projects",        "desc": "Admin personal project tracking"},
    "admin_personal_progress_steps": {"icon": "✅", "label": "Progress Steps",    "desc": "Steps within admin projects"},
    "dochub_documents":           {"icon": "📄", "label": "Documents",             "desc": "DocHub document library"},
    "dochub_access":              {"icon": "🔑", "label": "Document Access",       "desc": "Who can access which documents"},
    "mmr_chargeable_config":      {"icon": "💰", "label": "MMR Charges",           "desc": "MMR chargeable configuration"},
    "notifications":              {"icon": "🔔", "label": "Notifications",         "desc": "System notifications sent to users"},
}

# Quick filter presets per table (label, SQL WHERE clause)
TABLE_FILTERS = {
    "users": [
        ("All",          ""),
        ("Admins only",  "role = 'admin'"),
        ("Active users", "is_active = true"),
        ("Inactive",     "is_active = false"),
    ],
    "submissions": [
        ("All",          ""),
        ("Pending",      "status = 'pending'"),
        ("Approved",     "status = 'approved'"),
        ("Rejected",     "status = 'rejected'"),
    ],
    "jobs": [
        ("All",          ""),
        ("Active",       "status != 'completed'"),
        ("Completed",    "status = 'completed'"),
    ],
    "notifications": [
        ("All",          ""),
        ("Unread",       "is_read = false"),
        ("Read",         "is_read = true"),
    ],
    "bd_projects": [
        ("All",          ""),
        ("Active",       "status = 'active'"),
        ("Won",          "status = 'won'"),
        ("Lost",         "status = 'lost'"),
    ],
}

# Dashboard KPI queries
DASHBOARD_QUERIES = [
    {"label": "Team Members",    "icon": "👤", "table": "users",       "filter": ""},
    {"label": "Submissions",     "icon": "📋", "table": "submissions",  "filter": ""},
    {"label": "Active Jobs",     "icon": "🔧", "table": "jobs",         "filter": "status != 'completed'"},
    {"label": "BD Projects",     "icon": "🏗️",  "table": "bd_projects", "filter": ""},
    {"label": "Documents",       "icon": "📄", "table": "dochub_documents", "filter": ""},
    {"label": "Notifications",   "icon": "🔔", "table": "notifications","filter": "is_read = false"},
]


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def safe_json(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, memoryview):
        return obj.tobytes().decode("utf-8", errors="replace")
    return str(obj)


def api_tables():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name;
    """)
    tables = [r[0] for r in cur.fetchall()]
    counts = {}
    for t in tables:
        cur.execute(f'SELECT COUNT(*) FROM "{t}"')
        counts[t] = cur.fetchone()[0]
    cur.close()
    conn.close()
    return {"tables": tables, "counts": counts, "meta": TABLE_META,
            "filters": TABLE_FILTERS, "dashboard": DASHBOARD_QUERIES}


def api_table_data(table, page=1, per_page=50, search="", sort_col="", sort_dir="asc", preset_filter=""):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT column_name, data_type FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position;
    """, (table,))
    columns = cur.fetchall()
    col_names = [c["column_name"] for c in columns]

    conditions = []
    params = []

    if preset_filter:
        conditions.append(f"({preset_filter})")

    if search and col_names:
        search_conds = [f'CAST("{c}" AS TEXT) ILIKE %s' for c in col_names]
        conditions.append("(" + " OR ".join(search_conds) + ")")
        params += [f"%{search}%"] * len(col_names)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    cur.execute(f'SELECT COUNT(*) FROM "{table}" {where}', params)
    total = cur.fetchone()["count"]

    order = ""
    if sort_col and sort_col in col_names:
        direction = "DESC" if sort_dir.lower() == "desc" else "ASC"
        order = f'ORDER BY "{sort_col}" {direction}'

    offset = (page - 1) * per_page
    cur.execute(f'SELECT * FROM "{table}" {where} {order} LIMIT %s OFFSET %s', params + [per_page, offset])
    rows = [dict(r) for r in cur.fetchall()]

    cur.close()
    conn.close()
    return {
        "columns": col_names,
        "column_types": {c["column_name"]: c["data_type"] for c in columns},
        "rows": rows,
        "total": int(total),
        "page": page,
        "per_page": per_page,
    }


def api_export_csv(table, search="", sort_col="", sort_dir="asc", preset_filter=""):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position;
    """, (table,))
    col_names = [c["column_name"] for c in cur.fetchall()]

    conditions = []
    params = []
    if preset_filter:
        conditions.append(f"({preset_filter})")
    if search and col_names:
        search_conds = [f'CAST("{c}" AS TEXT) ILIKE %s' for c in col_names]
        conditions.append("(" + " OR ".join(search_conds) + ")")
        params += [f"%{search}%"] * len(col_names)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    order = ""
    if sort_col and sort_col in col_names:
        direction = "DESC" if sort_dir.lower() == "desc" else "ASC"
        order = f'ORDER BY "{sort_col}" {direction}'

    cur.execute(f'SELECT * FROM "{table}" {where} {order}', params)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=col_names)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: (v.isoformat() if isinstance(v, (datetime, date)) else
                             float(v) if isinstance(v, Decimal) else v)
                         for k, v in row.items()})
    return output.getvalue().encode("utf-8")


def api_dashboard():
    conn = get_conn()
    cur = conn.cursor()
    results = []
    for q in DASHBOARD_QUERIES:
        try:
            where = f"WHERE {q['filter']}" if q.get("filter") else ""
            cur.execute(f"SELECT COUNT(*) FROM \"{q['table']}\" {where}")
            count = cur.fetchone()[0]
        except Exception:
            count = 0
        results.append({**q, "count": count})
    cur.close()
    conn.close()
    return {"cards": results}


def api_get_primary_key(table):
    """Return the primary key column name for a table (usually 'id')."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        WHERE tc.constraint_type = 'PRIMARY KEY'
          AND tc.table_schema = 'public'
          AND tc.table_name = %s
        LIMIT 1;
    """, (table,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else "id"


def api_update_row(table, pk_col, pk_val, updates):
    """Update a row. updates = {col: new_value, ...}"""
    if not updates:
        return {"error": "No fields to update."}
    # Only allow known columns
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s;
    """, (table,))
    valid_cols = {r[0] for r in cur.fetchall()}
    bad = [k for k in updates if k not in valid_cols]
    if bad:
        cur.close(); conn.close()
        return {"error": f"Unknown column(s): {', '.join(bad)}"}
    set_clause = ", ".join(f'"{k}" = %s' for k in updates)
    values = list(updates.values()) + [pk_val]
    try:
        cur.execute(f'UPDATE "{table}" SET {set_clause} WHERE "{pk_col}" = %s', values)
        conn.commit()
        return {"ok": True, "rowcount": cur.rowcount}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        cur.close(); conn.close()


def api_delete_row(table, pk_col, pk_val):
    """Delete a single row by primary key."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(f'DELETE FROM "{table}" WHERE "{pk_col}" = %s', (pk_val,))
        conn.commit()
        return {"ok": True, "rowcount": cur.rowcount}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        cur.close(); conn.close()


def api_run_query(sql):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(sql)
        if cur.description:
            col_names = [d.name for d in cur.description]
            rows = [dict(r) for r in cur.fetchall()]
            conn.commit()
            return {"columns": col_names, "rows": rows, "rowcount": len(rows), "error": None}
        else:
            conn.commit()
            return {"columns": [], "rows": [], "rowcount": cur.rowcount, "error": None}
    except Exception as e:
        conn.rollback()
        return {"columns": [], "rows": [], "rowcount": 0, "error": str(e)}
    finally:
        cur.close()
        conn.close()


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Injaaz — Data Browser</title>
<style>
:root {
  --bg:#0f1117; --surface:#1a1d27; --surface2:#22263a; --border:#2e3249;
  --accent:#6c63ff; --accent2:#a78bfa; --text:#e2e8f0; --muted:#94a3b8;
  --green:#34d399; --red:#f87171; --yellow:#fbbf24;
}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;display:flex;height:100vh;overflow:hidden;}

/* ── Sidebar ── */
#sidebar{width:250px;min-width:220px;background:var(--surface);border-right:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden;}
#sidebar-top{padding:16px;border-bottom:1px solid var(--border);}
#sidebar-top h1{font-size:16px;font-weight:700;color:var(--accent2);}
#sidebar-top p{font-size:11px;color:var(--muted);margin-top:2px;}
#sidebar-search{padding:10px 12px;border-bottom:1px solid var(--border);}
#sidebar-search input{width:100%;background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:6px 10px;border-radius:6px;font-size:12px;outline:none;}
#sidebar-search input:focus{border-color:var(--accent);}
#table-list{flex:1;overflow-y:auto;padding:6px 0;}
.section-label{padding:8px 14px 4px;font-size:10px;font-weight:700;color:var(--muted);letter-spacing:.8px;text-transform:uppercase;}
.table-item{display:flex;align-items:center;gap:8px;padding:8px 14px;cursor:pointer;transition:background .15s;font-size:13px;color:var(--muted);border-left:3px solid transparent;}
.table-item:hover{background:var(--surface2);color:var(--text);}
.table-item.active{background:var(--surface2);color:var(--accent2);border-left-color:var(--accent);}
.table-item .ticon{font-size:15px;flex-shrink:0;}
.table-item .tinfo{flex:1;min-width:0;}
.table-item .tname{font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.table-item .tdesc{font-size:10px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:1px;}
.table-item .badge{font-size:10px;background:var(--surface);color:var(--muted);padding:2px 6px;border-radius:10px;border:1px solid var(--border);flex-shrink:0;}
.table-item.active .badge{background:var(--accent);color:#fff;border-color:var(--accent);}
#db-footer{padding:10px 14px;font-size:10px;color:var(--muted);border-top:1px solid var(--border);display:flex;align-items:center;gap:6px;}
#db-footer .dot{width:6px;height:6px;border-radius:50%;background:var(--green);}

/* ── Main ── */
#main{flex:1;display:flex;flex-direction:column;overflow:hidden;}

/* ── Dashboard ── */
#dashboard{flex:1;overflow-y:auto;padding:28px 32px;}
#dashboard h2{font-size:20px;font-weight:700;margin-bottom:6px;}
#dashboard p{color:var(--muted);font-size:13px;margin-bottom:24px;}
.cards-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:16px;margin-bottom:32px;}
.kpi-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:20px;cursor:pointer;transition:all .2s;}
.kpi-card:hover{border-color:var(--accent);transform:translateY(-2px);}
.kpi-icon{font-size:28px;margin-bottom:10px;}
.kpi-count{font-size:28px;font-weight:700;color:var(--accent2);line-height:1;}
.kpi-label{font-size:12px;color:var(--muted);margin-top:4px;}
.recent-section h3{font-size:14px;font-weight:600;margin-bottom:14px;color:var(--text);}
.recent-table{width:100%;border-collapse:collapse;font-size:13px;}
.recent-table th{color:var(--muted);font-weight:600;padding:8px 12px;text-align:left;border-bottom:1px solid var(--border);}
.recent-table td{padding:8px 12px;border-bottom:1px solid var(--border);}
.recent-table tr:hover td{background:var(--surface2);}

/* ── Browse panel ── */
#browse-panel{flex:1;display:none;flex-direction:column;overflow:hidden;}
#toolbar{padding:12px 20px;background:var(--surface);border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px;flex-wrap:wrap;}
#toolbar-left{display:flex;align-items:center;gap:10px;flex:1;min-width:0;}
#toolbar-title{font-size:15px;font-weight:600;white-space:nowrap;}
#toolbar-desc{font-size:12px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
#toolbar-right{display:flex;align-items:center;gap:8px;flex-shrink:0;}
#search-box{background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:6px 12px;border-radius:6px;font-size:13px;width:200px;outline:none;}
#search-box:focus{border-color:var(--accent);}
.action-btn{background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:6px 12px;border-radius:6px;cursor:pointer;font-size:12px;transition:all .15s;display:flex;align-items:center;gap:5px;flex-shrink:0;white-space:nowrap;}
.action-btn:hover{background:var(--accent);border-color:var(--accent);}
.action-btn:disabled{opacity:.35;cursor:not-allowed;}
.action-btn.export:hover{background:var(--green);border-color:var(--green);color:#000;}

/* Filter bar */
#filter-bar{padding:8px 20px;background:var(--surface2);border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;flex-wrap:wrap;}
#filter-bar span{font-size:11px;color:var(--muted);margin-right:4px;}
.filter-chip{font-size:11px;padding:4px 12px;border-radius:12px;background:var(--surface);border:1px solid var(--border);color:var(--muted);cursor:pointer;transition:all .15s;}
.filter-chip:hover{color:var(--text);border-color:var(--accent2);}
.filter-chip.active{background:var(--accent);border-color:var(--accent);color:#fff;}
#row-count{font-size:11px;color:var(--muted);margin-left:auto;}

/* Table */
#table-wrap{flex:1;overflow:auto;}
table{width:100%;border-collapse:collapse;font-size:13px;}
thead th{background:var(--surface2);color:var(--muted);font-weight:600;padding:10px 14px;text-align:left;position:sticky;top:0;z-index:1;border-bottom:1px solid var(--border);white-space:nowrap;cursor:pointer;user-select:none;}
thead th:hover{color:var(--text);}
thead th .arr{margin-left:4px;opacity:.3;}
thead th.sorted .arr{opacity:1;color:var(--accent2);}
tbody tr{border-bottom:1px solid var(--border);transition:background .1s;cursor:pointer;}
tbody tr:hover{background:var(--surface2);}
tbody td{padding:9px 14px;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;vertical-align:top;}
.null-val{color:var(--muted);font-style:italic;font-size:11px;}
.bool-true{color:var(--green);}
.bool-false{color:var(--red);}
.num-val{color:var(--yellow);font-family:monospace;}
.date-val{color:var(--accent2);font-size:12px;}
.json-badge{font-size:10px;background:var(--surface2);border:1px solid var(--border);padding:1px 6px;border-radius:4px;color:var(--muted);}

/* Pagination */
#pagination{padding:10px 20px;background:var(--surface);border-top:1px solid var(--border);display:flex;align-items:center;gap:8px;justify-content:center;}
.page-btn{background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:5px 12px;border-radius:5px;cursor:pointer;font-size:13px;transition:background .15s;}
.page-btn:hover:not(:disabled){background:var(--accent);border-color:var(--accent);}
.page-btn:disabled{opacity:.35;cursor:not-allowed;}
.page-btn.active{background:var(--accent);border-color:var(--accent);color:#fff;}
#page-info{font-size:12px;color:var(--muted);margin:0 8px;}

#empty{padding:60px;text-align:center;color:var(--muted);}
#empty .eicon{font-size:48px;margin-bottom:12px;}
#loading{display:none;padding:60px;text-align:center;color:var(--muted);}

/* ── Row detail panel ── */
#detail-panel{position:fixed;top:0;right:-460px;width:460px;height:100vh;background:var(--surface);border-left:1px solid var(--border);z-index:100;display:flex;flex-direction:column;transition:right .3s ease;overflow:hidden;}
#detail-panel.open{right:0;}
#detail-header{padding:14px 18px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;gap:8px;}
#detail-header h3{font-size:14px;font-weight:600;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
#detail-actions{display:flex;gap:8px;flex-shrink:0;}
#detail-close{cursor:pointer;font-size:20px;color:var(--muted);line-height:1;transition:color .15s;flex-shrink:0;}
#detail-close:hover{color:var(--text);}
#detail-body{flex:1;overflow-y:auto;padding:16px 18px;}
.detail-field{margin-bottom:14px;}
.detail-label{font-size:10px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.6px;margin-bottom:4px;}
.detail-value{font-size:13px;color:var(--text);word-break:break-word;line-height:1.5;}
.detail-value.null{color:var(--muted);font-style:italic;}
.detail-value.json-block{background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:10px;font-family:monospace;font-size:12px;white-space:pre-wrap;max-height:200px;overflow-y:auto;}
.detail-value.bool-t{color:var(--green);}
.detail-value.bool-f{color:var(--red);}
.detail-divider{height:1px;background:var(--border);margin:14px 0;}
/* Edit mode inputs */
.detail-input{width:100%;background:var(--bg);border:1px solid var(--border);color:var(--text);padding:6px 10px;border-radius:6px;font-size:13px;outline:none;line-height:1.5;}
.detail-input:focus{border-color:var(--accent);}
.detail-input.readonly{opacity:.45;cursor:not-allowed;}
/* Footer action bar */
#detail-footer{padding:12px 18px;border-top:1px solid var(--border);display:flex;gap:8px;align-items:center;}
.btn-save{background:var(--accent);border:1px solid var(--accent);color:#fff;padding:7px 18px;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600;transition:opacity .15s;}
.btn-save:hover{opacity:.85;}
.btn-save:disabled{opacity:.4;cursor:not-allowed;}
.btn-cancel{background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:7px 14px;border-radius:6px;cursor:pointer;font-size:13px;transition:background .15s;}
.btn-cancel:hover{background:var(--border);}
.btn-del{background:transparent;border:1px solid var(--red);color:var(--red);padding:7px 14px;border-radius:6px;cursor:pointer;font-size:13px;margin-left:auto;transition:all .15s;}
.btn-del:hover{background:var(--red);color:#fff;}
.btn-edit{background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:6px 14px;border-radius:6px;cursor:pointer;font-size:12px;transition:all .15s;}
.btn-edit:hover{border-color:var(--accent2);color:var(--accent2);}
/* Confirm overlay */
#confirm-box{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:200;display:none;align-items:center;justify-content:center;}
#confirm-box.show{display:flex;}
#confirm-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:28px 32px;max-width:360px;width:90%;text-align:center;}
#confirm-card h4{font-size:16px;margin-bottom:8px;}
#confirm-card p{color:var(--muted);font-size:13px;margin-bottom:24px;}
#confirm-card .cbns{display:flex;gap:10px;justify-content:center;}
.btn-confirm-del{background:var(--red);border:1px solid var(--red);color:#fff;padding:8px 22px;border-radius:6px;cursor:pointer;font-weight:600;font-size:13px;}
.btn-confirm-del:hover{opacity:.85;}
.btn-confirm-cancel{background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:8px 22px;border-radius:6px;cursor:pointer;font-size:13px;}
.save-status{font-size:12px;color:var(--muted);}

/* ── Advanced SQL (hidden by default) ── */
#sql-panel{flex:1;display:none;flex-direction:column;overflow:hidden;}
#sql-editor-area{padding:16px;background:var(--surface);border-bottom:1px solid var(--border);display:flex;flex-direction:column;gap:10px;}
#sql-editor-area label{font-size:11px;color:var(--muted);font-weight:700;text-transform:uppercase;letter-spacing:.5px;}
#sql-input{width:100%;height:120px;resize:vertical;background:var(--bg);border:1px solid var(--border);color:var(--text);padding:10px 14px;border-radius:6px;font-family:monospace;font-size:13px;outline:none;line-height:1.6;}
#sql-input:focus{border-color:var(--accent);}
#sql-toolbar{display:flex;align-items:center;gap:10px;}
#sql-status{font-size:12px;flex:1;}
#sql-status.ok{color:var(--green);}
#sql-status.err{color:var(--red);}
#sql-status.info{color:var(--muted);}
.run-btn{background:var(--accent);border:1px solid var(--accent);color:#fff;padding:7px 18px;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600;transition:opacity .15s;}
.run-btn:hover{opacity:.85;}
#sql-results-wrap{flex:1;overflow:auto;}

/* Mode tabs */
#mode-tabs{display:flex;background:var(--surface);border-bottom:1px solid var(--border);padding:0 8px;}
.mode-tab{padding:10px 16px;font-size:13px;cursor:pointer;color:var(--muted);border-bottom:2px solid transparent;transition:color .15s;}
.mode-tab:hover{color:var(--text);}
.mode-tab.active{color:var(--accent2);border-bottom-color:var(--accent);font-weight:600;}

/* Scrollbar */
::-webkit-scrollbar{width:6px;height:6px;}
::-webkit-scrollbar-track{background:transparent;}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px;}

/* Toast */
#toast{position:fixed;bottom:24px;right:24px;background:var(--green);color:#000;padding:10px 18px;border-radius:8px;font-size:13px;font-weight:600;opacity:0;transition:opacity .3s;pointer-events:none;z-index:999;}
#toast.show{opacity:1;}

/* Overlay */
#overlay{position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:99;display:none;}
#overlay.show{display:block;}
</style>
</head>
<body>

<!-- SIDEBAR -->
<div id="sidebar">
  <div id="sidebar-top">
    <h1>🗄 Injaaz Data</h1>
    <p>Live database · Render</p>
  </div>
  <div id="sidebar-search">
    <input type="text" placeholder="Find a section…" oninput="filterSidebar(this.value)">
  </div>
  <div id="table-list">
    <div style="padding:20px;color:var(--muted);font-size:12px;">Loading…</div>
  </div>
  <div id="db-footer">
    <div class="dot"></div>
    <span>Connected to Render</span>
  </div>
</div>

<!-- MAIN -->
<div id="main">
  <!-- Mode tabs -->
  <div id="mode-tabs">
    <div class="mode-tab active" onclick="switchMode('dashboard')">🏠 Home</div>
    <div class="mode-tab" onclick="switchMode('browse')" id="browse-tab" style="display:none">📋 Browse</div>
    <div class="mode-tab" onclick="switchMode('sql')">⚡ Advanced SQL</div>
  </div>

  <!-- DASHBOARD -->
  <div id="dashboard">
    <h2>Welcome back, Arshith 👋</h2>
    <p>Here's a live snapshot of your Injaaz application database.</p>
    <div class="cards-grid" id="kpi-cards">
      <div style="color:var(--muted);font-size:13px;padding:20px;">Loading stats…</div>
    </div>
    <div class="recent-section">
      <h3>📋 Recent Submissions</h3>
      <table class="recent-table" id="recent-table">
        <tbody><tr><td style="color:var(--muted);padding:20px;">Loading…</td></tr></tbody>
      </table>
    </div>
  </div>

  <!-- BROWSE PANEL -->
  <div id="browse-panel">
    <div id="toolbar">
      <div id="toolbar-left">
        <span id="toolbar-icon" style="font-size:20px;"></span>
        <div>
          <div id="toolbar-title">Select a table</div>
          <div id="toolbar-desc"></div>
        </div>
      </div>
      <div id="toolbar-right">
        <input id="search-box" type="text" placeholder="🔍 Search…" oninput="onSearch()" disabled>
        <button class="action-btn export" id="export-btn" onclick="exportCSV()" disabled>⬇ Export</button>
      </div>
    </div>
    <div id="filter-bar" style="display:none">
      <span>Filter:</span>
      <div id="filter-chips"></div>
      <span id="row-count"></span>
    </div>
    <div id="table-wrap">
      <div id="empty">
        <div class="eicon">👈</div>
        <p>Pick a section from the left to view data</p>
      </div>
      <div id="loading">⏳ Loading…</div>
      <table id="data-table" style="display:none">
        <thead id="thead"></thead>
        <tbody id="tbody"></tbody>
      </table>
    </div>
    <div id="pagination" style="display:none"></div>
  </div>

  <!-- SQL PANEL -->
  <div id="sql-panel">
    <div id="sql-editor-area">
      <label>⚡ SQL Query — Advanced users only</label>
      <textarea id="sql-input" placeholder="SELECT * FROM users LIMIT 10;&#10;-- Press Ctrl+Enter to run"></textarea>
      <div id="sql-toolbar">
        <button class="run-btn" onclick="runQuery()">▶ Run</button>
        <button class="action-btn" onclick="document.getElementById('sql-input').value=''">✕ Clear</button>
        <button class="action-btn export" id="sql-export-btn" onclick="exportQueryCSV()" disabled>⬇ Export CSV</button>
        <span id="sql-status" class="info">Ready · Ctrl+Enter to run</span>
      </div>
    </div>
    <div id="sql-results-wrap">
      <table id="sql-table" style="display:none;width:100%;border-collapse:collapse;font-size:13px;">
        <thead id="sql-thead"></thead>
        <tbody id="sql-tbody"></tbody>
      </table>
      <div id="sql-empty" style="display:none;padding:40px;text-align:center;color:var(--muted);">No rows returned.</div>
    </div>
  </div>
</div>

<!-- ROW DETAIL PANEL -->
<div id="overlay" onclick="closeDetail()"></div>
<div id="detail-panel">
  <div id="detail-header">
    <h3 id="detail-title">Row Details</h3>
    <div id="detail-actions">
      <button class="btn-edit" id="btn-edit" onclick="enterEditMode()">✏️ Edit</button>
    </div>
    <span id="detail-close" onclick="closeDetail()">✕</span>
  </div>
  <div id="detail-body"></div>
  <div id="detail-footer" style="display:none">
    <button class="btn-save" id="btn-save" onclick="saveEdits()">💾 Save Changes</button>
    <button class="btn-cancel" onclick="cancelEdit()">Cancel</button>
    <span class="save-status" id="save-status"></span>
    <button class="btn-del" onclick="confirmDelete()">🗑 Delete</button>
  </div>
</div>

<!-- CONFIRM DELETE DIALOG -->
<div id="confirm-box">
  <div id="confirm-card">
    <h4>⚠️ Delete this record?</h4>
    <p id="confirm-msg">This cannot be undone.</p>
    <div class="cbns">
      <button class="btn-confirm-cancel" onclick="closeConfirm()">Cancel</button>
      <button class="btn-confirm-del" onclick="doDelete()">Yes, Delete</button>
    </div>
  </div>
</div>

<div id="toast"></div>

<script>
let state = {
  tables:[], counts:{}, meta:{}, filters:{},
  activeTable:null, activeFilter:0,
  page:1, perPage:50, total:0,
  search:'', sortCol:'', sortDir:'asc',
  searchTimer:null, mode:'dashboard',
  lastQueryResult:null,
};

// ── Init ──────────────────────────────────────────────────────────────────
async function init() {
  const data = await get('/api/tables');
  state.tables = data.tables;
  state.counts = data.counts;
  state.meta   = data.meta || {};
  state.filters = data.filters || {};
  renderSidebar(state.tables);
  loadDashboard(data.dashboard);
  document.getElementById('sql-input').addEventListener('keydown', e => {
    if (e.key==='Enter' && (e.ctrlKey||e.metaKey)) { e.preventDefault(); runQuery(); }
  });
}

async function get(url) { return (await fetch(url)).json(); }

// ── Mode switching ────────────────────────────────────────────────────────
function switchMode(mode) {
  state.mode = mode;
  document.getElementById('dashboard').style.display    = mode==='dashboard' ? 'block' : 'none';
  document.getElementById('browse-panel').style.display = mode==='browse'    ? 'flex'  : 'none';
  document.getElementById('sql-panel').style.display    = mode==='sql'       ? 'flex'  : 'none';
  document.querySelectorAll('.mode-tab').forEach(t => t.classList.remove('active'));
  const idx = {dashboard:0, browse:1, sql:2}[mode];
  document.querySelectorAll('.mode-tab')[idx].classList.add('active');
}

// ── Dashboard ─────────────────────────────────────────────────────────────
async function loadDashboard(cards) {
  const grid = document.getElementById('kpi-cards');
  const data = await get('/api/dashboard');
  grid.innerHTML = data.cards.map(c => `
    <div class="kpi-card" onclick="selectTable('${c.table}')">
      <div class="kpi-icon">${c.icon}</div>
      <div class="kpi-count">${c.count.toLocaleString()}</div>
      <div class="kpi-label">${c.label}</div>
    </div>`).join('');

  // Recent submissions
  const sub = await get('/api/data?table=submissions&page=1&per_page=5&sort_col=created_at&sort_dir=desc&search=&preset_filter=');
  const rt = document.getElementById('recent-table');
  if (!sub.rows || sub.rows.length === 0) {
    rt.innerHTML = '<tbody><tr><td style="color:var(--muted);padding:20px;">No submissions yet.</td></tr></tbody>';
    return;
  }
  const cols = ['id','status','created_at'].filter(c => sub.columns.includes(c));
  const allCols = sub.columns.slice(0,5);
  const displayCols = cols.length ? cols : allCols;
  rt.innerHTML =
    '<thead><tr>' + displayCols.map(c=>`<th>${friendlyCol(c)}</th>`).join('') + '</tr></thead>' +
    '<tbody>' + sub.rows.map(r =>
      '<tr style="cursor:pointer" onclick=\'openDetailFromData(' + JSON.stringify(JSON.stringify(r)) + ',"Submission")\'>' +
      displayCols.map(c=>`<td>${formatCell(r[c],'')}</td>`).join('') + '</tr>'
    ).join('') + '</tbody>';
}

// ── Sidebar ───────────────────────────────────────────────────────────────
function renderSidebar(tables) {
  const list = document.getElementById('table-list');
  list.innerHTML = '<div class="section-label">All Sections</div>' +
    tables.map(t => {
      const m = state.meta[t] || {};
      return `<div class="table-item ${t===state.activeTable?'active':''}" onclick="selectTable('${t}')">
        <span class="ticon">${m.icon||'📦'}</span>
        <div class="tinfo">
          <div class="tname">${m.label||t}</div>
          <div class="tdesc">${m.desc||''}</div>
        </div>
        <span class="badge">${(state.counts[t]||0).toLocaleString()}</span>
      </div>`;
    }).join('');
}

function filterSidebar(q) {
  const filtered = q ? state.tables.filter(t => {
    const m = state.meta[t]||{};
    return (m.label||t).toLowerCase().includes(q.toLowerCase()) ||
           (m.desc||'').toLowerCase().includes(q.toLowerCase());
  }) : state.tables;
  renderSidebar(filtered);
}

// ── Browse ────────────────────────────────────────────────────────────────
async function selectTable(name) {
  state.activeTable  = name;
  state.page         = 1;
  state.search       = '';
  state.sortCol      = '';
  state.sortDir      = 'asc';
  state.activeFilter = 0;
  document.getElementById('search-box').value = '';
  document.getElementById('search-box').disabled = false;
  document.getElementById('export-btn').disabled = false;
  document.getElementById('browse-tab').style.display = '';
  renderSidebar(state.tables);
  renderFilterBar(name);
  switchMode('browse');

  const m = state.meta[name] || {};
  document.getElementById('toolbar-icon').textContent  = m.icon  || '📦';
  document.getElementById('toolbar-title').textContent = m.label || name;
  document.getElementById('toolbar-desc').textContent  = m.desc  || '';
  await loadData();
}

function renderFilterBar(table) {
  const filters = state.filters[table];
  const bar = document.getElementById('filter-bar');
  if (!filters || filters.length <= 1) { bar.style.display='none'; return; }
  bar.style.display='flex';
  document.getElementById('filter-chips').innerHTML = filters.map((f,i) =>
    `<span class="filter-chip ${i===state.activeFilter?'active':''}" onclick="applyFilter(${i})">${f[0]}</span>`
  ).join('');
}

function applyFilter(idx) {
  state.activeFilter = idx;
  state.page = 1;
  document.querySelectorAll('.filter-chip').forEach((c,i) => c.classList.toggle('active', i===idx));
  loadData();
}

async function loadData() {
  if (!state.activeTable) return;
  document.getElementById('empty').style.display    = 'none';
  document.getElementById('loading').style.display  = 'block';
  document.getElementById('data-table').style.display = 'none';
  document.getElementById('pagination').style.display = 'none';

  const filters     = state.filters[state.activeTable] || [['All','']];
  const preset      = (filters[state.activeFilter]||filters[0])[1];
  const params = new URLSearchParams({
    table: state.activeTable, page: state.page, per_page: state.perPage,
    search: state.search, sort_col: state.sortCol, sort_dir: state.sortDir,
    preset_filter: preset,
  });
  const data = await get('/api/data?' + params);
  state.total = data.total;

  document.getElementById('row-count').textContent =
    `${data.total.toLocaleString()} row${data.total!==1?'s':''}`;
  renderTable(data);
  renderPagination();
  document.getElementById('loading').style.display = 'none';
}

function renderTable(data) {
  const thead = document.getElementById('thead');
  const tbody = document.getElementById('tbody');

  // Pick sensible columns to show first (id, name/title, status, dates)
  const priority = ['id','username','full_name','name','title','status','role','created_at','updated_at'];
  const cols = [...new Set([
    ...priority.filter(p => data.columns.includes(p)),
    ...data.columns
  ])];

  thead.innerHTML = '<tr>' + cols.map(c => {
    const sorted = c === state.sortCol;
    const arrow  = sorted ? (state.sortDir==='asc'?'▲':'▼') : '▲';
    return `<th class="${sorted?'sorted':''}" onclick="sortBy('${c}')">
      ${friendlyCol(c)}<span class="arr">${arrow}</span></th>`;
  }).join('') + '</tr>';

  if (data.rows.length === 0) {
    tbody.innerHTML = `<tr><td colspan="${cols.length}" style="text-align:center;padding:40px;color:var(--muted)">No records found</td></tr>`;
  } else {
    tbody.innerHTML = data.rows.map(row =>
      `<tr onclick='openDetailFromData(${JSON.stringify(JSON.stringify(row))},"${state.meta[state.activeTable]?.label||state.activeTable}")'>` +
      cols.map(c => `<td title="${esc(String(row[c]??''))}">${formatCell(row[c], data.column_types[c])}</td>`).join('') +
      '</tr>'
    ).join('');
  }
  document.getElementById('data-table').style.display = '';
}

function sortBy(col) {
  state.sortDir = state.sortCol===col ? (state.sortDir==='asc'?'desc':'asc') : 'asc';
  state.sortCol = col;
  state.page = 1;
  loadData();
}

function onSearch() {
  clearTimeout(state.searchTimer);
  state.searchTimer = setTimeout(() => {
    state.search = document.getElementById('search-box').value;
    state.page = 1;
    loadData();
  }, 350);
}

function renderPagination() {
  const pages = Math.ceil(state.total / state.perPage);
  if (pages<=1) { document.getElementById('pagination').style.display='none'; return; }
  const pg = document.getElementById('pagination');
  pg.style.display='flex';
  let b = `<button class="page-btn" onclick="goPage(${state.page-1})" ${state.page===1?'disabled':''}>‹ Prev</button>`;
  let s = Math.max(1,state.page-3), e = Math.min(pages,s+6);
  if (e-s<6) s=Math.max(1,e-6);
  if (s>1) b+=`<button class="page-btn" onclick="goPage(1)">1</button><span style="color:var(--muted)">…</span>`;
  for (let i=s;i<=e;i++) b+=`<button class="page-btn ${i===state.page?'active':''}" onclick="goPage(${i})">${i}</button>`;
  if (e<pages) b+=`<span style="color:var(--muted)">…</span><button class="page-btn" onclick="goPage(${pages})">${pages}</button>`;
  b+=`<button class="page-btn" onclick="goPage(${state.page+1})" ${state.page>=pages?'disabled':''}>Next ›</button>`;
  b+=`<span id="page-info">Page ${state.page} of ${pages} · ${state.total.toLocaleString()} total</span>`;
  pg.innerHTML = b;
}

function goPage(p) {
  if (p<1||p>Math.ceil(state.total/state.perPage)) return;
  state.page=p; loadData();
}

// ── Row detail panel ──────────────────────────────────────────────────────
let detailState = { row: null, pkCol: 'id', pkVal: null, editMode: false };

// Read-only columns that should never be editable
const READONLY_COLS = new Set(['id','created_at','updated_at','password_hash']);

function openDetailFromData(jsonStr, title) {
  const row = JSON.parse(jsonStr);
  openDetail(row, title);
}

async function openDetail(row, title) {
  detailState.row     = row;
  detailState.editMode = false;

  // Fetch primary key for this table
  const pkData = await fetch('/api/pk', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({table: state.activeTable})
  }).then(r=>r.json());
  detailState.pkCol = pkData.pk || 'id';
  detailState.pkVal = row[detailState.pkCol];

  document.getElementById('detail-title').textContent = title + ' — Details';
  document.getElementById('detail-footer').style.display = 'none';
  document.getElementById('btn-edit').style.display = '';
  document.getElementById('save-status').textContent = '';
  renderDetailBody(row, false);

  document.getElementById('detail-panel').classList.add('open');
  document.getElementById('overlay').classList.add('show');
}

function renderDetailBody(row, editMode) {
  const body = document.getElementById('detail-body');
  body.innerHTML = Object.entries(row).map(([k, v]) => {
    const isReadOnly = READONLY_COLS.has(k) || k === detailState.pkCol;
    let display = '';

    if (editMode && !isReadOnly) {
      // Editable input
      const val = (v === null || v === undefined) ? '' : String(v);
      const isLong = val.length > 80;
      if (isLong) {
        display = `<textarea class="detail-input" data-key="${esc(k)}" rows="3">${esc(val)}</textarea>`;
      } else if (typeof v === 'boolean') {
        display = `<select class="detail-input" data-key="${esc(k)}">
          <option value="true" ${v?'selected':''}>✓ Yes</option>
          <option value="false" ${!v?'selected':''}>✗ No</option>
        </select>`;
      } else {
        display = `<input class="detail-input" data-key="${esc(k)}" value="${esc(val)}">`;
      }
    } else {
      // Read-only view
      if (v === null || v === undefined) {
        display = '<div class="detail-value null">Not set</div>';
      } else if (typeof v === 'boolean') {
        display = `<div class="detail-value ${v?'bool-t':'bool-f'}">${v?'✓ Yes':'✗ No'}</div>`;
      } else {
        const s = String(v);
        if ((s.startsWith('{') || s.startsWith('[')) && s.length > 2) {
          try {
            display = `<div class="detail-value json-block">${JSON.stringify(JSON.parse(s), null, 2)}</div>`;
          } catch { display = `<div class="detail-value">${esc(s)}</div>`; }
        } else if (s.length > 80) {
          display = `<div class="detail-value" style="white-space:pre-wrap">${esc(s)}</div>`;
        } else {
          display = `<div class="detail-value">${esc(s)}</div>`;
        }
      }
      // Lock icon for readonly fields in edit mode
      if (editMode && isReadOnly) {
        display += `<div style="font-size:10px;color:var(--muted);margin-top:3px;">🔒 Cannot be edited</div>`;
      }
    }

    return `<div class="detail-field">
      <div class="detail-label">${friendlyCol(k)}${isReadOnly && editMode ? ' 🔒':''}</div>
      ${display}
    </div>`;
  }).join('<div class="detail-divider"></div>');
}

function enterEditMode() {
  detailState.editMode = true;
  renderDetailBody(detailState.row, true);
  document.getElementById('detail-footer').style.display = 'flex';
  document.getElementById('btn-edit').style.display = 'none';
  document.getElementById('save-status').textContent = '';
}

function cancelEdit() {
  detailState.editMode = false;
  renderDetailBody(detailState.row, false);
  document.getElementById('detail-footer').style.display = 'none';
  document.getElementById('btn-edit').style.display = '';
  document.getElementById('save-status').textContent = '';
}

async function saveEdits() {
  const inputs = document.querySelectorAll('#detail-body [data-key]');
  const updates = {};
  inputs.forEach(el => {
    const key = el.getAttribute('data-key');
    const orig = String(detailState.row[key] ?? '');
    const val  = el.value;
    if (val !== orig) updates[key] = val === '' ? null : val;
  });

  if (Object.keys(updates).length === 0) {
    document.getElementById('save-status').textContent = 'No changes to save.';
    return;
  }

  const btn = document.getElementById('btn-save');
  btn.disabled = true; btn.textContent = '⏳ Saving…';
  document.getElementById('save-status').textContent = '';

  const res = await fetch('/api/update', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({
      table: state.activeTable,
      pk_col: detailState.pkCol,
      pk_val: detailState.pkVal,
      updates,
    })
  }).then(r=>r.json());

  btn.disabled = false; btn.textContent = '💾 Save Changes';

  if (res.error) {
    document.getElementById('save-status').textContent = '✗ ' + res.error;
    document.getElementById('save-status').style.color = 'var(--red)';
  } else {
    // Update local state
    Object.assign(detailState.row, updates);
    showToast('✓ Changes saved!');
    cancelEdit();
    loadData(); // Refresh table
  }
}

function confirmDelete() {
  const label = state.meta[state.activeTable]?.label || state.activeTable;
  document.getElementById('confirm-msg').textContent =
    `This will permanently delete this ${label} record (ID: ${detailState.pkVal}). This cannot be undone.`;
  document.getElementById('confirm-box').classList.add('show');
}

function closeConfirm() {
  document.getElementById('confirm-box').classList.remove('show');
}

async function doDelete() {
  closeConfirm();
  const res = await fetch('/api/delete', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({
      table: state.activeTable,
      pk_col: detailState.pkCol,
      pk_val: detailState.pkVal,
    })
  }).then(r=>r.json());

  if (res.error) {
    showToast('✗ ' + res.error, true);
  } else {
    showToast('🗑 Record deleted');
    closeDetail();
    loadData(); // Refresh table
  }
}

function closeDetail() {
  document.getElementById('detail-panel').classList.remove('open');
  document.getElementById('overlay').classList.remove('show');
  detailState.editMode = false;
  document.getElementById('detail-footer').style.display = 'none';
  document.getElementById('btn-edit').style.display = '';
}

// ── CSV Export ────────────────────────────────────────────────────────────
async function exportCSV() {
  if (!state.activeTable) return;
  const btn = document.getElementById('export-btn');
  btn.disabled=true; btn.textContent='⏳ Exporting…';
  try {
    const filters  = state.filters[state.activeTable]||[['All','']];
    const preset   = (filters[state.activeFilter]||filters[0])[1];
    const params = new URLSearchParams({
      table:state.activeTable, search:state.search,
      sort_col:state.sortCol, sort_dir:state.sortDir, preset_filter:preset,
    });
    const resp = await fetch('/api/export?'+params);
    const blob = await resp.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url;
    a.download = `${state.activeTable}_${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('✓ Downloaded!');
  } finally {
    btn.disabled=false; btn.innerHTML='⬇ Export';
  }
}

// ── SQL Runner ────────────────────────────────────────────────────────────
async function runQuery() {
  const sql = document.getElementById('sql-input').value.trim();
  if (!sql) return;
  const status = document.getElementById('sql-status');
  status.textContent='Running…'; status.className='info';
  document.getElementById('sql-table').style.display='none';
  document.getElementById('sql-empty').style.display='none';
  document.getElementById('sql-export-btn').disabled=true;
  const t0=Date.now();
  const data = await fetch('/api/query',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sql})}).then(r=>r.json());
  const ms=((Date.now()-t0)/1000).toFixed(2);
  if (data.error) { status.textContent='✗ '+data.error; status.className='err'; return; }
  if (!data.columns.length) { status.textContent=`✓ ${data.rowcount} row(s) affected · ${ms}s`; status.className='ok'; return; }
  state.lastQueryResult=data;
  status.textContent=`✓ ${data.rows.length.toLocaleString()} row${data.rows.length!==1?'s':''} · ${ms}s`;
  status.className='ok';
  document.getElementById('sql-export-btn').disabled=false;
  const thead=document.getElementById('sql-thead'), tbody=document.getElementById('sql-tbody');
  thead.innerHTML='<tr>'+data.columns.map(c=>`<th style="background:var(--surface2);color:var(--muted);font-weight:600;padding:10px 14px;text-align:left;border-bottom:1px solid var(--border);white-space:nowrap;">${c}</th>`).join('')+'</tr>';
  tbody.innerHTML=data.rows.map(r=>`<tr style="border-bottom:1px solid var(--border);">` +
    data.columns.map(c=>`<td style="padding:9px 14px;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${esc(String(r[c]??''))}">${formatCell(r[c],'')}</td>`).join('')+
    `</tr>`).join('');
  if (data.rows.length===0) document.getElementById('sql-empty').style.display='block';
  else document.getElementById('sql-table').style.display='';
}

function exportQueryCSV() {
  const data=state.lastQueryResult; if(!data) return;
  const rows=[data.columns.join(',')].concat(data.rows.map(row=>
    data.columns.map(c=>{const v=row[c];if(v==null)return '';const s=String(v);
      return (s.includes(',')||s.includes('"')||s.includes('\n'))?'"'+s.replace(/"/g,'""')+'"':s;
    }).join(',')
  ));
  const blob=new Blob([rows.join('\n')],{type:'text/csv'});
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a'); a.href=url;
  a.download=`query_${new Date().toISOString().slice(0,10)}.csv`; a.click();
  URL.revokeObjectURL(url); showToast('✓ Downloaded!');
}

// ── Helpers ───────────────────────────────────────────────────────────────
function friendlyCol(col) {
  const map={id:'ID',created_at:'Created',updated_at:'Updated',is_active:'Active?',
    is_read:'Read?',user_id:'User',full_name:'Full Name',password_hash:'Password',
    role:'Role',username:'Username',email:'Email',phone:'Phone',status:'Status',
    description:'Description',title:'Title',type:'Type',access_hvac:'HVAC Access',
    access_civil:'Civil Access',access_cleaning:'Cleaning Access'};
  return map[col] || col.replace(/_/g,' ').replace(/\b\w/g,l=>l.toUpperCase());
}

function formatCell(val, type) {
  if (val===null||val===undefined) return '<span class="null-val">—</span>';
  if (val===true)  return '<span class="bool-true">✓ Yes</span>';
  if (val===false) return '<span class="bool-false">✗ No</span>';
  const s=String(val);
  // JSON
  if ((s.startsWith('{')||s.startsWith('['))&&s.length>2) {
    try { JSON.parse(s); return '<span class="json-badge">{ JSON }</span>'; } catch {}
  }
  // Numbers
  if (type&&(type.includes('int')||type.includes('numeric')||type.includes('float')||type.includes('double')))
    return `<span class="num-val">${s}</span>`;
  // Dates — show relative + absolute
  if (type&&(type.includes('timestamp')||type.includes('date'))) {
    const d=new Date(val);
    if (!isNaN(d)) return `<span class="date-val" title="${d.toLocaleString()}">${relativeTime(d)}</span>`;
  }
  if (s.length>100) return esc(s.substring(0,100))+'<span style="color:var(--muted)">…</span>';
  return esc(s);
}

function relativeTime(d) {
  const diff=(Date.now()-d.getTime())/1000;
  if (diff<60) return 'just now';
  if (diff<3600) return Math.floor(diff/60)+'m ago';
  if (diff<86400) return Math.floor(diff/3600)+'h ago';
  if (diff<604800) return Math.floor(diff/86400)+'d ago';
  return d.toLocaleDateString();
}

function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

function showToast(msg, isError=false) {
  const t=document.getElementById('toast');
  t.textContent=msg;
  t.style.background = isError ? 'var(--red)' : 'var(--green)';
  t.style.color = isError ? '#fff' : '#000';
  t.classList.add('show');
  setTimeout(()=>t.classList.remove('show'),2800);
}

init();
</script>
</body>
</html>
"""


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, f, *a): pass

    def send_json(self, data, status=200):
        body = json.dumps(data, default=safe_json).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def send_csv(self, data: bytes, filename: str):
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", len(data))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/":
            body = HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)

        elif parsed.path == "/api/tables":
            try: self.send_json(api_tables())
            except Exception as e: self.send_json({"error": str(e)}, 500)

        elif parsed.path == "/api/dashboard":
            try: self.send_json(api_dashboard())
            except Exception as e: self.send_json({"error": str(e)}, 500)

        elif parsed.path == "/api/data":
            try:
                self.send_json(api_table_data(
                    table=qs.get("table",[""])[0],
                    page=int(qs.get("page",[1])[0]),
                    per_page=int(qs.get("per_page",[50])[0]),
                    search=qs.get("search",[""])[0],
                    sort_col=qs.get("sort_col",[""])[0],
                    sort_dir=qs.get("sort_dir",["asc"])[0],
                    preset_filter=qs.get("preset_filter",[""])[0],
                ))
            except Exception as e: self.send_json({"error": str(e)}, 500)

        elif parsed.path == "/api/export":
            try:
                table = qs.get("table",[""])[0]
                csv_data = api_export_csv(
                    table=table,
                    search=qs.get("search",[""])[0],
                    sort_col=qs.get("sort_col",[""])[0],
                    sort_dir=qs.get("sort_dir",["asc"])[0],
                    preset_filter=qs.get("preset_filter",[""])[0],
                )
                self.send_csv(csv_data, f"{table}_{datetime.now().strftime('%Y-%m-%d')}.csv")
            except Exception as e: self.send_json({"error": str(e)}, 500)

        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length))
        except Exception:
            self.send_json({"error": "Invalid JSON"}, 400)
            return

        if self.path == "/api/query":
            try: self.send_json(api_run_query(body.get("sql","").strip()))
            except Exception as e: self.send_json({"error": str(e)}, 500)

        elif self.path == "/api/pk":
            try: self.send_json({"pk": api_get_primary_key(body.get("table",""))})
            except Exception as e: self.send_json({"error": str(e)}, 500)

        elif self.path == "/api/update":
            try:
                self.send_json(api_update_row(
                    table=body.get("table",""),
                    pk_col=body.get("pk_col","id"),
                    pk_val=body.get("pk_val"),
                    updates=body.get("updates",{}),
                ))
            except Exception as e: self.send_json({"error": str(e)}, 500)

        elif self.path == "/api/delete":
            try:
                self.send_json(api_delete_row(
                    table=body.get("table",""),
                    pk_col=body.get("pk_col","id"),
                    pk_val=body.get("pk_val"),
                ))
            except Exception as e: self.send_json({"error": str(e)}, 500)

        else:
            self.send_response(404); self.end_headers()


def main():
    print("=" * 55)
    print("  🗄  Injaaz — Data Browser")
    print("=" * 55)
    print(f"\n  Connecting to Render PostgreSQL…")
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT version();")
        ver = cur.fetchone()[0].split(" on ")[0]
        cur.close(); conn.close()
        print(f"  ✅ Connected! ({ver})")
    except Exception as e:
        print(f"  ❌ Connection failed: {e}"); return

    url = f"http://localhost:{PORT}"
    print(f"\n  🌐 Opening at {url}")
    print(f"  Press Ctrl+C to stop.\n")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    server = http.server.HTTPServer(("localhost", PORT), Handler)
    try: server.serve_forever()
    except KeyboardInterrupt: print("\n  👋 Stopped.")


if __name__ == "__main__":
    main()
