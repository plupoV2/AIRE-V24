
import os, re, json, hashlib, sqlite3, base64, math
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

import streamlit as st
import requests
import pandas as pd
import numpy as np

# ============================================================
# AIRE (Proof-of-Concept) v5
# Proprietary Notice:
# This software and its underwriting methodology ("AIRE Vector Grade™") are confidential and proprietary.
# © AIRE PROJECT. All rights reserved.
#
# v5 upgrades (corporate-ready):
# - Workspace settings (custom pipeline folders, scoring profile)
# - Deal notes + assignment + tags (pipeline collaboration)
# - Integrations: Webhook push on save/move/re-evaluate (CRM/BI friendly)
# - Memo gallery + share link copy (slug-based)
# - Stronger governance: export includes Deals + Notes + Versions + Audit + Calibration + Settings
#
# Stability fix:
# - Robust IRR solver avoids OverflowError on extreme rates / long holds.
# ============================================================

st.set_page_config(page_title="AIRE | AI Underwriting", layout="wide")

# ----------------------------
# Utilities
# ----------------------------
def now_utc() -> str:
    return datetime.utcnow().isoformat()

def stable_hash(s: str) -> int:
    h = hashlib.sha256(s.encode("utf-8")).hexdigest()
    return int(h[:8], 16)

def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9\s-]", "", (text or "")).strip().lower()
    s = re.sub(r"[\s_-]+", "-", s)
    return s[:70] if s else "memo"

def hex_to_rgb01(hx: str):
    hx = (hx or "#2563eb").lstrip("#")
    return tuple(int(hx[i:i+2], 16)/255.0 for i in (0,2,4))

def safe_email(x: str) -> str:
    return (x or "").strip().lower()

def gen_invite_code(workspace_id: int, email: str) -> str:
    raw = f"{workspace_id}|{safe_email(email)}|{now_utc()}|{stable_hash(email)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

def post_webhook(url: str, payload: Dict[str, Any]) -> Tuple[bool, str]:
    if not url:
        return False, "No webhook configured."
    try:
        r = requests.post(url, json=payload, timeout=8)
        if 200 <= r.status_code < 300:
            return True, f"Webhook OK ({r.status_code})"
        return False, f"Webhook failed ({r.status_code})"
    except Exception as e:
        return False, f"Webhook error: {e}"

# ----------------------------
# Theme + Branding
# ----------------------------
def _init_defaults():
    st.session_state.setdefault("theme", "Light")
    st.session_state.setdefault("brand_accent", "#2563eb")
    st.session_state.setdefault("brand_name", "AIRE")
    st.session_state.setdefault("brand_logo_b64", "")

_init_defaults()

with st.sidebar:
    st.markdown("### Appearance")
    st.session_state.theme = st.radio("Theme", ["Light", "Dark"], index=0 if st.session_state.theme=="Light" else 1)
    st.markdown("### Branding")
    st.session_state.brand_name = st.text_input("Brand name", value=st.session_state.brand_name)
    st.session_state.brand_accent = st.color_picker("Accent color", value=st.session_state.brand_accent)
    logo = st.file_uploader("Logo (PNG/JPG for memo)", type=["png","jpg","jpeg"])
    if logo:
        st.session_state.brand_logo_b64 = base64.b64encode(logo.read()).decode("utf-8")

THEME = st.session_state.theme
ACCENT = st.session_state.brand_accent
BRAND = st.session_state.brand_name

if THEME == "Dark":
    bg = "#0b1220"; card = "#0f172a"; border = "#22314b"; text = "#e5e7eb"; muted = "#cbd5e1"
else:
    bg = "#ffffff"; card = "#ffffff"; border = "#e5e7eb"; text = "#0f172a"; muted = "#334155"

st.markdown(f"""
<style>
#MainMenu, footer, header {{ visibility: hidden; }}
html, body, [class*="css"] {{
  background: {bg} !important;
  color: {text} !important;
  font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, "Helvetica Neue", Arial, "Noto Sans", "Liberation Sans", sans-serif !important;
}}
a {{ color: {ACCENT} !important; }}

/* App layout */
.block-container {{ padding-top: 1rem !important; max-width: 1100px; }}
section[data-testid="stSidebar"] {{ border-right: 1px solid {border} !important; }}

/* Minimal top bar */
.topbar {{ display:flex; align-items:center; justify-content:space-between; padding: 10px 6px 12px 6px; }}
.brand {{ font-weight: 900; letter-spacing: 0.2px; font-size: 16px; }}
.pill {{ border: 1px solid {border}; border-radius: 999px; padding: 7px 12px; background: {card}; color: {muted}; font-size: 12px; }}

/* Surfaces */
.card {{ border: 1px solid {border}; border-radius: 14px; padding: 16px; background: {card}; }}
.divider {{ height:1px; background:{border}; margin: 14px 0; }}
.h1 {{ font-size: 30px; font-weight: 900; line-height: 1.1; margin: 6px 0 6px 0; }}
.h2 {{ font-size: 16px; font-weight: 800; margin: 0 0 8px 0; color: {text}; }}
.p {{ color: {muted}; font-size: 14px; line-height: 1.55; }}
.small {{ font-size: 12px; color: {muted}; }}

/* Chat bubbles */
/* Action chips */
.chipRow {{ display:flex; flex-wrap:wrap; gap: 8px; margin-top: 10px; }}
.chipHint {{ font-size: 11px; color: {muted}; margin-top: 6px; }}
.chatWrap {{ display:flex; flex-direction:column; gap: 10px; }}
.bubble {{ max-width: 92%; padding: 12px 14px; border-radius: 14px; border: 1px solid {border}; background: {card}; }}
.bubble.user {{ margin-left:auto; border-color: rgba(37,99,235,0.28); background: rgba(37,99,235,0.08); }}
.bubble.assistant {{ margin-right:auto; }}
.bubble .role {{ font-size: 11px; color: {muted}; margin-bottom: 6px; }}
.kpiRow {{ display:flex; gap: 10px; flex-wrap: wrap; }}
.kpi {{ border: 1px solid {border}; border-radius: 12px; padding: 10px 12px; min-width: 160px; background: {card}; }}
.kpi .label {{ color: {muted}; font-size: 12px; }}
.kpi .value {{ color: {text}; font-weight: 900; font-size: 16px; margin-top: 2px; }}

/* ChatGPT-like thread list */
.threadList {{ display:flex; flex-direction:column; gap: 6px; }}
.threadItem {{ border: 1px solid {border}; border-radius: 12px; padding: 10px 10px; background: {card}; }}
.threadItem:hover {{ border-color: rgba(37,99,235,0.35); }}
.threadTop {{ display:flex; align-items:center; justify-content:space-between; gap: 10px; }}
.threadTitle {{ font-weight: 800; font-size: 12.5px; color: {text}; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width: 220px;}}
.threadMeta {{ font-size: 11px; color: {muted}; white-space:nowrap; }}
.threadPreview {{ font-size: 11.5px; color: {muted}; margin-top: 4px; line-height: 1.25; max-height: 2.5em; overflow:hidden; }}
.pinBtn {{ border: 1px solid {border}; border-radius: 10px; padding: 6px 8px; background: {bg}; color: {muted}; font-size: 12px; }}
</style>
""", unsafe_allow_html=True)

st.markdown(f"""<div class="topbar"><div class="brand">{BRAND}</div><div class="pill">Chat Underwriting</div></div>""", unsafe_allow_html=True)
# ----------------------------
# Database
# ----------------------------
DB_PATH = "aire.db"

def db_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cur = conn.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS workspaces (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        workspace_id INTEGER NOT NULL,
        role TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(email, workspace_id)
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS invitations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        workspace_id INTEGER NOT NULL,
        email TEXT NOT NULL,
        role TEXT NOT NULL,
        code TEXT NOT NULL,
        created_at TEXT NOT NULL,
        accepted_at TEXT,
        UNIQUE(workspace_id, email)
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS workspace_settings (
        workspace_id INTEGER PRIMARY KEY,
        created_at TEXT NOT NULL,
        folders_json TEXT NOT NULL,
        scoring_profile TEXT NOT NULL,
        webhook_url TEXT NOT NULL
    )""")
    
    cur.execute("""CREATE TABLE IF NOT EXISTS thread_memory (
        workspace_id INTEGER NOT NULL,
        mem_key TEXT NOT NULL,
        value_json TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (workspace_id, mem_key)
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        workspace_id INTEGER NOT NULL,
        actor_email TEXT NOT NULL,
        action TEXT NOT NULL,
        target_type TEXT,
        target_id INTEGER,
        meta TEXT,
        created_at TEXT NOT NULL
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS deals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        workspace_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        source TEXT NOT NULL,
        address TEXT NOT NULL,
        folder TEXT NOT NULL,
        slug TEXT NOT NULL,
        grade_letter TEXT NOT NULL,
        grade_score REAL NOT NULL,
        irr_base REAL NOT NULL,
        oer REAL NOT NULL,
        noi REAL NOT NULL,
        payload TEXT NOT NULL
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS deal_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        workspace_id INTEGER NOT NULL,
        deal_id INTEGER NOT NULL,
        version_num INTEGER NOT NULL,
        reason TEXT NOT NULL,
        created_at TEXT NOT NULL,
        grade_letter TEXT NOT NULL,
        grade_score REAL NOT NULL,
        irr_base REAL NOT NULL,
        oer REAL NOT NULL,
        noi REAL NOT NULL,
        payload TEXT NOT NULL,
        UNIQUE(workspace_id, deal_id, version_num)
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS deal_notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        workspace_id INTEGER NOT NULL,
        deal_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        author_email TEXT NOT NULL,
        assignee_email TEXT,
        tags_json TEXT NOT NULL,
        notes TEXT NOT NULL
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS memos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        workspace_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        slug TEXT NOT NULL,
        brand TEXT NOT NULL,
        accent TEXT NOT NULL,
        payload TEXT NOT NULL
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS calibration (
        workspace_id INTEGER PRIMARY KEY,
        created_at TEXT NOT NULL,
        vacancy_bias REAL NOT NULL,
        oer_bias REAL NOT NULL,
        irr_bias REAL NOT NULL
    )""")
    conn.commit()
    return conn

CONN = db_conn()

# ----------------------------
# Data access
# ----------------------------
def audit(workspace_id: int, actor_email: str, action: str, target_type: Optional[str]=None, target_id: Optional[int]=None, meta: Optional[Dict[str, Any]]=None):
    cur = CONN.cursor()
    cur.execute("""INSERT INTO audit_log (workspace_id, actor_email, action, target_type, target_id, meta, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (workspace_id, safe_email(actor_email), action, target_type, target_id, json.dumps(meta or {}), now_utc()))
    CONN.commit()

def ensure_workspace(name: str) -> int:
    cur = CONN.cursor()
    cur.execute("SELECT id FROM workspaces WHERE name=?", (name,))
    row = cur.fetchone()
    if row:
        return int(row[0])
    cur.execute("INSERT INTO workspaces (name, created_at) VALUES (?, ?)", (name, now_utc()))
    CONN.commit()
    return int(cur.lastrowid)

def ensure_user(email: str, workspace_id: int, role: str) -> None:
    cur = CONN.cursor()
    cur.execute("INSERT OR IGNORE INTO users (email, workspace_id, role, created_at) VALUES (?, ?, ?, ?)",
                (safe_email(email), workspace_id, role, now_utc()))
    CONN.commit()

def get_user_role(email: str, workspace_id: int) -> str:
    cur = CONN.cursor()
    cur.execute("SELECT role FROM users WHERE email=? AND workspace_id=?", (safe_email(email), workspace_id))
    row = cur.fetchone()
    return row[0] if row else "analyst"

def list_users(workspace_id: int) -> pd.DataFrame:
    cur = CONN.cursor()
    cur.execute("SELECT email, role, created_at FROM users WHERE workspace_id=? ORDER BY created_at ASC", (workspace_id,))
    return pd.DataFrame(cur.fetchall(), columns=["email","role","created_at"])

def set_user_role(workspace_id: int, email: str, role: str):
    cur = CONN.cursor()
    cur.execute("UPDATE users SET role=? WHERE workspace_id=? AND email=?", (role, workspace_id, safe_email(email)))
    CONN.commit()

def upsert_invite(workspace_id: int, email: str, role: str) -> str:
    code = gen_invite_code(workspace_id, email)
    cur = CONN.cursor()
    cur.execute("""INSERT INTO invitations (workspace_id, email, role, code, created_at, accepted_at)
                   VALUES (?, ?, ?, ?, ?, NULL)
                   ON CONFLICT(workspace_id, email) DO UPDATE SET
                     role=excluded.role,
                     code=excluded.code,
                     created_at=excluded.created_at,
                     accepted_at=NULL""",
                (workspace_id, safe_email(email), role, code, now_utc()))
    CONN.commit()
    return code

def accept_invite(workspace_id: int, email: str, code: str) -> Tuple[bool, str]:
    cur = CONN.cursor()
    cur.execute("SELECT role, code, accepted_at FROM invitations WHERE workspace_id=? AND email=?",
                (workspace_id, safe_email(email)))
    row = cur.fetchone()
    if not row:
        return False, "No invite found."
    role, real_code, accepted_at = row
    if real_code != code:
        return False, "Invite code mismatch."
    if accepted_at:
        return False, "Invite already accepted."
    ensure_user(email, workspace_id, role)
    cur.execute("UPDATE invitations SET accepted_at=? WHERE workspace_id=? AND email=?", (now_utc(), workspace_id, safe_email(email)))
    CONN.commit()
    return True, f"Invite accepted. Role: {role.upper()}."

def list_invites(workspace_id: int) -> pd.DataFrame:
    cur = CONN.cursor()
    cur.execute("SELECT email, role, code, created_at, accepted_at FROM invitations WHERE workspace_id=? ORDER BY created_at DESC", (workspace_id,))
    return pd.DataFrame(cur.fetchall(), columns=["email","role","code","created_at","accepted_at"])

def upsert_settings(workspace_id: int, folders: List[str], scoring_profile: str, webhook_url: str):
    cur = CONN.cursor()
    cur.execute("""
        INSERT INTO workspace_settings (workspace_id, created_at, folders_json, scoring_profile, webhook_url)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(workspace_id) DO UPDATE SET
            created_at=excluded.created_at,
            folders_json=excluded.folders_json,
            scoring_profile=excluded.scoring_profile,
            webhook_url=excluded.webhook_url
    """, (workspace_id, now_utc(), json.dumps(folders), scoring_profile, webhook_url))
    CONN.commit()

def get_settings(workspace_id: int) -> Dict[str, Any]:
    cur = CONN.cursor()
    cur.execute("SELECT folders_json, scoring_profile, webhook_url FROM workspace_settings WHERE workspace_id=?", (workspace_id,))
    row = cur.fetchone()
    if not row:
        default = {"folders": ["Hot","Maybe","Trash"], "scoring_profile": "Core", "webhook_url": ""}
        upsert_settings(workspace_id, default["folders"], default["scoring_profile"], default["webhook_url"])
        return default
    return {"folders": json.loads(row[0]), "scoring_profile": row[1], "webhook_url": row[2]}


def get_thread_memory(workspace_id: int, mem_key: str) -> Dict[str, Any]:
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT value_json FROM thread_memory WHERE workspace_id=? AND mem_key=?", (workspace_id, mem_key))
    row = cur.fetchone()
    conn.close()
    if not row:
        return {}
    try:
        return json.loads(row[0])
    except Exception:
        return {}

def upsert_thread_memory(workspace_id: int, mem_key: str, value: Dict[str, Any]) -> None:
    conn = db_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO thread_memory (workspace_id, mem_key, value_json, updated_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(workspace_id, mem_key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at",
        (workspace_id, mem_key, json.dumps(value), datetime.datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()

def _mem_key_for_deal(deal: Dict[str, Any]) -> str:
    city = (deal or {}).get("city") or ""
    state = (deal or {}).get("state") or ""
    if city and state:
        return f"city:{city.strip().lower()}-{state.strip().lower()}"
    if city:
        return f"city:{city.strip().lower()}"
    return "global"

def update_memory_from_memo(workspace_id: int, memo: Dict[str, Any]) -> None:
    if not memo:
        return
    deal = memo.get("deal", {}) or {}
    mi = memo.get("model_inputs", {}) or {}
    metrics = memo.get("metrics", {}) or {}

    snapshot = {
        "hold_years": float(mi.get("hold_years", 5)),
        "rent_growth": float(mi.get("rent_growth", 0.03)),
        "expense_growth": float(mi.get("expense_growth", 0.025)),
        "exit_cap": float(mi.get("exit_cap", 0.065)),
        "sale_cost_pct": float(mi.get("sale_cost_pct", 0.05)),
        "down_payment_pct": float(mi.get("down_payment_pct", 0.25)),
        "interest_rate": float(mi.get("interest_rate", 0.065)),
        "amort_years": float(mi.get("amort_years", 30)),
        "vacancy_rate": float(deal.get("vacancy_rate", metrics.get("vacancy_rate", 0.08)) if isinstance(deal, dict) else 0.08),
        "expense_ratio": float(metrics.get("oer", 0.45)),
    }

    def _blend(old: Dict[str, Any], new: Dict[str, Any], alpha: float) -> Dict[str, Any]:
        out = dict(old or {})
        for k, v in (new or {}).items():
            if isinstance(v, (int, float)) and isinstance(out.get(k), (int, float)):
                out[k] = (1 - alpha) * float(out[k]) + alpha * float(v)
            else:
                out[k] = v
        return out

    # global
    g_old = get_thread_memory(workspace_id, "global")
    g_n = int(g_old.get("n", 0)) + 1
    g_alpha = 1.0 / min(g_n, 20)
    g_val = _blend(g_old.get("defaults", {}), snapshot, g_alpha)
    upsert_thread_memory(workspace_id, "global", {"n": g_n, "defaults": g_val})

    # city
    key = _mem_key_for_deal(deal)
    c_old = get_thread_memory(workspace_id, key)
    c_n = int(c_old.get("n", 0)) + 1
    c_alpha = 1.0 / min(c_n, 15)
    c_val = _blend(c_old.get("defaults", {}), snapshot, c_alpha)
    upsert_thread_memory(workspace_id, key, {"n": c_n, "defaults": c_val})

def apply_memory_defaults(workspace_id: int, deal: Dict[str, Any], mi: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(mi or {})
    g = get_thread_memory(workspace_id, "global").get("defaults", {}) or {}
    c = get_thread_memory(workspace_id, _mem_key_for_deal(deal)).get("defaults", {}) or {}
    merged = dict(g); merged.update(c)
    for k in ["hold_years","rent_growth","expense_growth","exit_cap","sale_cost_pct","down_payment_pct","interest_rate","amort_years"]:
        if k in merged and (k not in out or out.get(k) is None):
            out[k] = merged[k]
    if isinstance(deal, dict) and "vacancy_rate" not in deal and "vacancy_rate" in merged:
        deal["vacancy_rate"] = float(merged["vacancy_rate"])
    return out

def upsert_calibration(workspace_id: int, vacancy_bias: float, oer_bias: float, irr_bias: float):
    cur = CONN.cursor()
    cur.execute("""
        INSERT INTO calibration (workspace_id, created_at, vacancy_bias, oer_bias, irr_bias)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(workspace_id) DO UPDATE SET
            created_at=excluded.created_at,
            vacancy_bias=excluded.vacancy_bias,
            oer_bias=excluded.oer_bias,
            irr_bias=excluded.irr_bias
    """, (workspace_id, now_utc(), vacancy_bias, oer_bias, irr_bias))
    CONN.commit()

def get_calibration(workspace_id: int) -> Dict[str, float]:
    cur = CONN.cursor()
    cur.execute("SELECT vacancy_bias, oer_bias, irr_bias FROM calibration WHERE workspace_id=?", (workspace_id,))
    row = cur.fetchone()
    if not row:
        upsert_calibration(workspace_id, 0.0, 0.0, 0.0)
        return {"vacancy_bias": 0.0, "oer_bias": 0.0, "irr_bias": 0.0}
    return {"vacancy_bias": float(row[0]), "oer_bias": float(row[1]), "irr_bias": float(row[2])}

def save_deal_version(workspace_id: int, deal_id: int, version_num: int, reason: str,
                      grade_letter: str, grade_score: float, irr_base: float, oer: float, noi: float, payload: Dict[str, Any]):
    cur = CONN.cursor()
    cur.execute("""INSERT OR REPLACE INTO deal_versions
                   (workspace_id, deal_id, version_num, reason, created_at, grade_letter, grade_score, irr_base, oer, noi, payload)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (workspace_id, deal_id, version_num, reason, now_utc(), grade_letter, grade_score, irr_base, oer, noi, json.dumps(payload)))
    CONN.commit()

def next_version_num(workspace_id: int, deal_id: int) -> int:
    cur = CONN.cursor()
    cur.execute("SELECT COALESCE(MAX(version_num), 0) FROM deal_versions WHERE workspace_id=? AND deal_id=?", (workspace_id, deal_id))
    return int(cur.fetchone()[0]) + 1

def save_deal(workspace_id: int, actor_email: str, source: str, address: str, folder: str, slug: str,
              grade_letter: str, grade_score: float, irr_base: float, oer: float, noi: float, payload: Dict[str, Any]) -> int:
    cur = CONN.cursor()
    cur.execute("""INSERT INTO deals (workspace_id, created_at, source, address, folder, slug, grade_letter, grade_score, irr_base, oer, noi, payload)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (workspace_id, now_utc(), source, address, folder, slug, grade_letter, grade_score, irr_base, oer, noi, json.dumps(payload)))
    CONN.commit()
    deal_id = int(cur.lastrowid)
    audit(workspace_id, actor_email, "deal_saved", "deal", deal_id, {"folder": folder, "slug": slug})
    save_deal_version(workspace_id, deal_id, 1, "initial_save", grade_letter, grade_score, irr_base, oer, noi, payload)
    return deal_id

def update_deal_latest(workspace_id: int, deal_id: int, grade_letter: str, grade_score: float, irr_base: float, oer: float, noi: float, payload: Dict[str, Any]):
    cur = CONN.cursor()
    cur.execute("""UPDATE deals SET grade_letter=?, grade_score=?, irr_base=?, oer=?, noi=?, payload=? WHERE workspace_id=? AND id=?""",
                (grade_letter, grade_score, irr_base, oer, noi, json.dumps(payload), workspace_id, deal_id))
    CONN.commit()

def list_deals(workspace_id: int, folder: Optional[str]=None):
    cur = CONN.cursor()
    if folder:
        cur.execute("""SELECT id, created_at, folder, address, slug, grade_letter, grade_score, irr_base, oer, noi, payload
                       FROM deals WHERE workspace_id=? AND folder=? ORDER BY id DESC""", (workspace_id, folder))
    else:
        cur.execute("""SELECT id, created_at, folder, address, slug, grade_letter, grade_score, irr_base, oer, noi, payload
                       FROM deals WHERE workspace_id=? ORDER BY id DESC""", (workspace_id,))
    return cur.fetchall()

def move_deal(workspace_id: int, actor_email: str, deal_id: int, folder: str):
    cur = CONN.cursor()
    cur.execute("UPDATE deals SET folder=? WHERE workspace_id=? AND id=?", (folder, workspace_id, deal_id))
    CONN.commit()
    audit(workspace_id, actor_email, "deal_moved", "deal", deal_id, {"new_folder": folder})

def get_deal_row(workspace_id: int, deal_id: int):
    cur = CONN.cursor()
    cur.execute("""SELECT id, created_at, folder, address, slug, grade_letter, grade_score, irr_base, oer, noi, payload
                   FROM deals WHERE workspace_id=? AND id=?""", (workspace_id, deal_id))
    return cur.fetchone()

def list_versions(workspace_id: int, deal_id: int) -> pd.DataFrame:
    cur = CONN.cursor()
    cur.execute("""SELECT version_num, reason, created_at, grade_letter, grade_score, irr_base, oer, noi
                   FROM deal_versions WHERE workspace_id=? AND deal_id=? ORDER BY version_num DESC""",
                (workspace_id, deal_id))
    return pd.DataFrame(cur.fetchall(), columns=["version","reason","created_at","grade","score","irr","oer","noi"])

def add_note(workspace_id: int, deal_id: int, author_email: str, assignee_email: str, tags: List[str], notes: str):
    cur = CONN.cursor()
    cur.execute("""INSERT INTO deal_notes (workspace_id, deal_id, created_at, author_email, assignee_email, tags_json, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (workspace_id, deal_id, now_utc(), safe_email(author_email), safe_email(assignee_email), json.dumps(tags), notes))
    CONN.commit()
    audit(workspace_id, author_email, "deal_note_added", "deal", deal_id, {"assignee": safe_email(assignee_email), "tags": tags})

def list_notes(workspace_id: int, deal_id: int) -> pd.DataFrame:
    cur = CONN.cursor()
    cur.execute("""SELECT created_at, author_email, assignee_email, tags_json, notes
                   FROM deal_notes WHERE workspace_id=? AND deal_id=? ORDER BY id DESC""",
                (workspace_id, deal_id))
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["created_at","author","assignee","tags","notes"])
    if not df.empty:
        df["tags"] = df["tags"].apply(lambda x: ", ".join(json.loads(x)) if x else "")
    return df

def save_memo(workspace_id: int, actor_email: str, slug: str, payload: Dict[str, Any], brand: str, accent: str) -> int:
    cur = CONN.cursor()
    cur.execute("""INSERT INTO memos (workspace_id, created_at, slug, brand, accent, payload)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (workspace_id, now_utc(), slug, brand, accent, json.dumps(payload)))
    CONN.commit()
    memo_id = int(cur.lastrowid)
    audit(workspace_id, actor_email, "memo_saved", "memo", memo_id, {"slug": slug})
    return memo_id

def load_memo_by_slug(workspace_id: int, slug: str):
    cur = CONN.cursor()
    cur.execute("""SELECT id, created_at, slug, brand, accent, payload
                   FROM memos WHERE workspace_id=? AND slug=? ORDER BY id DESC LIMIT 1""", (workspace_id, slug))
    row = cur.fetchone()
    if not row:
        return None
    mid, created, slug, brand, accent, payload = row
    obj = json.loads(payload)
    obj["_meta"] = {"memo_id": mid, "created_at": created, "slug": slug, "brand": brand, "accent": accent}
    return obj

def list_memos(workspace_id: int, limit: int=200) -> pd.DataFrame:
    cur = CONN.cursor()
    cur.execute("""SELECT id, created_at, slug, brand, accent FROM memos WHERE workspace_id=? ORDER BY id DESC LIMIT ?""",
                (workspace_id, limit))
    return pd.DataFrame(cur.fetchall(), columns=["memo_id","created_at","slug","brand","accent"])

def list_audit(workspace_id: int, limit: int=200) -> pd.DataFrame:
    cur = CONN.cursor()
    cur.execute("""SELECT created_at, actor_email, action, target_type, target_id, meta
                   FROM audit_log WHERE workspace_id=? ORDER BY id DESC LIMIT ?""", (workspace_id, limit))
    df = pd.DataFrame(cur.fetchall(), columns=["created_at","actor","action","target_type","target_id","meta"])
    if not df.empty:
        df["meta"] = df["meta"].apply(lambda x: json.loads(x) if x else {})
    return df

# ----------------------------
# Listing import (demo + RESO scaffold)
# ----------------------------
def demo_listing_from_link(link_or_address: str) -> Dict[str, Any]:
    seed = stable_hash(link_or_address.strip().lower())
    units = 1 + (seed % 64)
    avg_rent = 1100 + (seed % 2200)
    price = int((max(1, units) * avg_rent * 12) / (0.055 + ((seed % 25)/1000)))
    vacancy = round(0.05 + ((seed % 70)/1000), 3)
    taxes = int(price * (0.010 + ((seed % 30)/10000)))
    insurance = int(max(1800, price * (0.002 + ((seed % 20)/10000))))
    utilities_party = "Tenant Paid" if (seed % 2 == 0) else "Landlord Paid"
    return {
        "source": "demo",
        "address": f"{100 + (seed % 900)} Market St, Phoenix, AZ",
        "property_type": "Multifamily" if units >= 10 else "Single Family",
        "price": price,
        "units": units if units >= 2 else 1,
        "sqft": 900 * max(1, units),
        "avg_rent": avg_rent if units >= 2 else avg_rent * 1.6,
        "vacancy": vacancy,
        "other_income_mo": int((seed % 250) * (1 if units > 10 else 0)),
        "taxes": taxes,
        "insurance": insurance,
        "hoa_mo": int((seed % 250) * (1 if units <= 8 else 0)),
        "utilities_mo": int((seed % 600) * (1 if utilities_party == "Landlord Paid" else 0)),
        "management_pct": 0.08,
        "repairs_pct": 0.06,
        "capex_pct": 0.04,
        "utilities_party": utilities_party,
        "year_built": 1950 + (seed % 70),
        "city": "Phoenix",
        "state": "AZ",
    }

def reso_import(link_or_address: str) -> Optional[Dict[str, Any]]:
    base_url = st.secrets.get("RESO_BASE_URL", "")
    token = st.secrets.get("RESO_BEARER_TOKEN", "")
    if not base_url or not token:
        return None
    q = link_or_address.strip()
    headers = {"Authorization": f"Bearer {token}"}
    url = base_url.rstrip("/") + "/Property?$top=1&$filter=contains(UnparsedAddress,'" + q.replace("'", "''") + "')"
    try:
        r = requests.get(url, headers=headers, timeout=12)
        if r.status_code != 200:
            return None
        data = r.json()
        items = data.get("value", [])
        if not items:
            return None
        p = items[0]
        return {
            "source": "reso",
            "address": p.get("UnparsedAddress") or q,
            "property_type": p.get("PropertySubType") or p.get("PropertyType") or "Unknown",
            "price": p.get("ListPrice") or 0,
            "units": p.get("NumberOfUnitsTotal") or 0,
            "sqft": p.get("LivingArea") or p.get("BuildingAreaTotal") or 0,
            "year_built": p.get("YearBuilt") or None,
            "avg_rent": 0,
            "vacancy": 0.07,
            "other_income_mo": 0,
            "taxes": 0,
            "insurance": 0,
            "hoa_mo": 0,
            "utilities_mo": 0,
            "management_pct": 0.08,
            "repairs_pct": 0.06,
            "capex_pct": 0.04,
            "utilities_party": "Unknown",
            "city": p.get("City") or "",
            "state": p.get("StateOrProvince") or "",
        }
    except Exception:
        return None

def import_listing(link_or_address: str) -> Dict[str, Any]:
    return reso_import(link_or_address) or demo_listing_from_link(link_or_address)

# ----------------------------
# Metrics + Robust IRR
# ----------------------------
def compute_metrics(deal: Dict[str, Any], calib: Dict[str, float]) -> Dict[str, Any]:
    units = max(1, int(deal.get("units") or 1))
    avg_rent = float(deal.get("avg_rent") or 0) or (1600 if deal.get("property_type") in ("Single Family","Condo","Townhouse") else 1400)
    gpr = units * avg_rent * 12
    other_income = float(deal.get("other_income_mo") or 0) * 12
    vacancy = float(deal.get("vacancy") or 0.07) + calib.get("vacancy_bias", 0.0)
    vacancy = max(0.0, min(0.25, vacancy))
    egi = (gpr + other_income) * (1 - vacancy)

    taxes = float(deal.get("taxes") or 0)
    insurance = float(deal.get("insurance") or 0)
    hoa = float(deal.get("hoa_mo") or 0) * 12
    utilities = float(deal.get("utilities_mo") or 0) * 12
    mgmt = egi * float(deal.get("management_pct") or 0.08)
    repairs = egi * float(deal.get("repairs_pct") or 0.06)
    capex = egi * float(deal.get("capex_pct") or 0.04)

    opex = taxes + insurance + hoa + utilities + mgmt + repairs + capex
    opex = max(0.0, opex * (1 + calib.get("oer_bias", 0.0)))
    oer = opex / egi if egi > 0 else 0
    noi = egi - opex
    price = float(deal.get("price") or 0)
    cap_rate = noi / price if price > 0 else 0
    return {"units": units, "avg_rent": avg_rent, "gpr": gpr, "other_income": other_income, "vacancy": vacancy,
            "egi": egi, "taxes": taxes, "insurance": insurance, "hoa": hoa, "utilities": utilities, "mgmt": mgmt,
            "repairs": repairs, "capex": capex, "opex": opex, "oer": oer, "noi": noi, "cap_rate": cap_rate}

def pmt(rate: float, nper: int, pv: float) -> float:
    if rate == 0: return pv / max(nper, 1)
    return pv * rate / (1 - (1 + rate) ** (-nper))

def _npv_safe(rate: float, cashflows: List[float]) -> float:
    # rate is periodic; enforce domain
    if rate <= -0.999999:
        return float("inf")
    lr = math.log1p(rate)
    total = 0.0
    for t, cf in enumerate(cashflows):
        exp_arg = t * lr
        if exp_arg > 700:   # exp(>709) overflows in float64; term ~ 0
            disc = float("inf")
        elif exp_arg < -700:
            disc = 0.0
        else:
            disc = math.exp(exp_arg)
        if disc == 0.0:
            # huge negative exp_arg => discount ~ 0 => term ~ inf, but that's unstable; clamp
            return float("inf") if cf > 0 else float("-inf")
        if disc == float("inf"):
            # huge positive exp_arg => denominator infinite => term ~ 0
            continue
        total += cf / disc
    return total

def irr_robust(cashflows: List[float]) -> float:
    # Returns periodic IRR. Avoids Newton blowups by bracketing + bisection.
    # Search a grid for sign changes.
    lo, hi = -0.95, 5.0
    grid = [-0.95, -0.8, -0.6, -0.4, -0.2, -0.1, -0.05, -0.02, 0.0, 0.01, 0.02, 0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0]
    vals = []
    for r in grid:
        try:
            vals.append(_npv_safe(r, cashflows))
        except Exception:
            vals.append(float("nan"))

    # Find first bracket where NPV changes sign
    bracket = None
    for i in range(len(grid)-1):
        a, b = grid[i], grid[i+1]
        fa, fb = vals[i], vals[i+1]
        if not (math.isfinite(fa) and math.isfinite(fb)):
            continue
        if fa == 0.0:
            return a
        if fb == 0.0:
            return b
        if (fa > 0 and fb < 0) or (fa < 0 and fb > 0):
            bracket = (a, b, fa, fb)
            break

    if bracket is None:
        # fallback: try numpy if available; else return 0
        try:
            r = np.irr(np.array(cashflows, dtype=float))  # type: ignore
            if r is not None and not np.isnan(r):
                return float(r)
        except Exception:
            pass
        return 0.0

    a, b, fa, fb = bracket
    # bisection
    for _ in range(80):
        mid = (a + b) / 2
        fm = _npv_safe(mid, cashflows)
        if not math.isfinite(fm):
            # nudge slightly toward finite region
            mid = (mid + a) / 2
            fm = _npv_safe(mid, cashflows)
        if abs(fm) < 1e-6:
            return mid
        if (fa > 0 and fm < 0) or (fa < 0 and fm > 0):
            b, fb = mid, fm
        else:
            a, fa = mid, fm
    return (a + b) / 2

def build_cashflows(deal: Dict[str, Any], m: Dict[str, Any], hold_years: int, rent_growth: float, expense_growth: float,
                    exit_cap: float, sale_cost_pct: float,
                    down_payment_pct: float, interest_rate: float, amort_years: int) -> Dict[str, Any]:
    months = hold_years * 12
    price = float(deal.get("price") or 0) or (m["noi"] / max(0.05, m["cap_rate"] or 0.06))
    equity0 = -price * down_payment_pct
    loan0 = price * (1 - down_payment_pct)

    r_m = interest_rate / 12.0
    nper = amort_years * 12
    pay = pmt(r_m, nper, loan0)

    cashflows = [equity0]
    loan_balance = loan0

    egi_m0 = m["egi"] / 12.0
    opex_m0 = m["opex"] / 12.0

    for month in range(1, months + 1):
        y = (month - 1) // 12
        egi_m = egi_m0 * ((1 + rent_growth) ** y)
        opex_m = opex_m0 * ((1 + expense_growth) ** y)
        noi_m = egi_m - opex_m
        interest = loan_balance * r_m
        principal = max(0.0, pay - interest)
        loan_balance = max(0.0, loan_balance - principal)
        cashflows.append(noi_m - pay)

    last_noi_annual = (egi_m0 * ((1+rent_growth) ** (hold_years-1)) - opex_m0 * ((1+expense_growth) ** (hold_years-1))) * 12.0
    sale_price = last_noi_annual / max(0.01, exit_cap)
    sale_cost = sale_price * sale_cost_pct
    net_sale = sale_price - sale_cost - loan_balance
    cashflows[-1] += net_sale

    irr_m = irr_robust(cashflows)
    irr_a = (1 + irr_m) ** 12 - 1 if irr_m > -0.999 else -1.0
    eq_mult = (sum(cf for cf in cashflows[1:] if cf > 0) / abs(cashflows[0])) if cashflows[0] != 0 else 0
    return {"cashflows": cashflows, "irr_monthly": irr_m, "irr_annual": irr_a, "equity_multiple": eq_mult,
            "sale_price": sale_price, "net_sale": net_sale, "end_loan_balance": loan_balance}

def aire_grade(m: Dict[str, Any], irr_a: float, calib: Dict[str, float], scoring_profile: str) -> Dict[str, Any]:
    score = 100.0
    flags = []
    oer = m["oer"]; cap = m["cap_rate"]; vac = m["vacancy"]
    irr_adj = irr_a + calib.get("irr_bias", 0.0)

    profile = (scoring_profile or "Core").lower()
    if profile == "value-add":
        oer_high_pen = 14; irr_bonus_high = 6; cap_low_pen = 10
    elif profile == "growth":
        oer_high_pen = 12; irr_bonus_high = 8; cap_low_pen = 8
    else:
        oer_high_pen = 18; irr_bonus_high = 4; cap_low_pen = 12

    if oer > 0.55: score -= oer_high_pen; flags.append("High operating expense ratio (>55%).")
    elif oer > 0.45: score -= 10; flags.append("Elevated operating expense ratio (>45%).")
    elif oer < 0.25: score -= 6; flags.append("Unusually low expense ratio — verify inputs.")

    if cap <= 0: score -= 18; flags.append("Cap rate unavailable — missing NOI or price.")
    elif cap < 0.045: score -= cap_low_pen; flags.append("Low cap rate — thin yield.")
    elif cap > 0.09: score += 4; flags.append("High cap rate — verify condition/risks.")

    if vac > 0.12: score -= 10; flags.append("High vacancy assumption (>12%).")
    elif vac < 0.04: score -= 4; flags.append("Very low vacancy — confirm market realism.")

    if irr_adj < 0.08: score -= 8; flags.append("Low IRR (<8%) in base case.")
    elif irr_adj > 0.18: score += irr_bonus_high; flags.append("High IRR (>18%) — double-check assumptions.")

    score = max(0, min(100, score))
    letter = "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D" if score >= 60 else "F"
    return {"score": score, "letter": letter, "confidence": 0.78, "flags": flags, "irr_adj": irr_adj, "profile": scoring_profile}

def apply_chat_update(user_text: str, deal: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    t = user_text.lower()


def suggest_actions(deal: Dict[str, Any], mi: Dict[str, Any], metrics: Dict[str, Any], grade: Dict[str, Any]) -> List[Dict[str, str]]:
    actions: List[Dict[str, str]] = []
    flags = grade.get("flags", []) if isinstance(grade, dict) else []
    vr = float((deal or {}).get("vacancy_rate", (metrics or {}).get("vacancy_rate", 0.08)) or 0.08)

    # Always helpful quick toggles
    if vr > 0.08:
        actions.append({"label": "Vacancy → 8%", "command": "vacancy to 8%"})
    actions.append({"label": "Try rate 6.75%", "command": "rate to 6.75%"})
    actions.append({"label": "Down payment → 30%", "command": "down payment to 30%"})
    actions.append({"label": "Exit cap +0.50%", "command": "exit cap +0.50%"})

    for f in (flags or [])[:8]:
        lf = str(f).lower()
        if "expense" in lf or "oer" in lf:
            actions.append({"label": "Expenses down 5%", "command": "expenses down 5%"})
        if "rent" in lf:
            actions.append({"label": "Rent +$100", "command": "rent +100"})
        if "tax" in lf:
            actions.append({"label": "Set taxes $22k", "command": "taxes to 22000"})
        if "insurance" in lf:
            actions.append({"label": "Set insurance $3k", "command": "insurance to 3000"})

    actions.append({"label": "Sensitivity grid", "command": "sensitivity grid"})
    actions.append({"label": "Stress test", "command": "stress test"})

    # de-dupe
    seen = set()
    out = []
    for a in actions:
        if a["label"] in seen:
            continue
        seen.add(a["label"])
        out.append(a)
    return out[:8]


def quick_sensitivity(deal: Dict[str, Any], mi: Dict[str, Any], metrics: Dict[str, Any]) -> Dict[str, float]:
    """Fast, lightweight sensitivity probe to rank action chips."""
    try:
        base = build_cashflows(deal, metrics, int(mi.get("hold_years", 5)), float(mi.get("rent_growth", 0.03)), float(mi.get("expense_growth", 0.025)),
                               float(mi.get("exit_cap", 0.065)), float(mi.get("sale_cost_pct", 0.05)),
                               float(mi.get("down_payment_pct", 0.25)), float(mi.get("interest_rate", 0.065)), int(mi.get("amort_years", 30)))
        base_irr = float(base.get("irr_annual", 0.0))
    except Exception:
        return {}

    def _irr_with(**kw):
        mi2 = dict(mi or {})
        mi2.update(kw)
        try:
            mod = build_cashflows(deal, metrics, int(mi2.get("hold_years", 5)), float(mi2.get("rent_growth", 0.03)), float(mi2.get("expense_growth", 0.025)),
                                  float(mi2.get("exit_cap", 0.065)), float(mi2.get("sale_cost_pct", 0.05)),
                                  float(mi2.get("down_payment_pct", 0.25)), float(mi2.get("interest_rate", 0.065)), int(mi2.get("amort_years", 30)))
            return float(mod.get("irr_annual", 0.0))
        except Exception:
            return base_irr

    # small stresses
    irr_exit = _irr_with(exit_cap=float(mi.get("exit_cap", 0.065)) + 0.005)
    irr_rate = _irr_with(interest_rate=float(mi.get("interest_rate", 0.065)) + 0.005)
    irr_rent = _irr_with(rent_growth=max(0.0, float(mi.get("rent_growth", 0.03)) - 0.01))

    return {
        "base": base_irr,
        "exit_cap_+50bps": base_irr - irr_exit,
        "rate_+50bps": base_irr - irr_rate,
        "rent_growth_-1pt": base_irr - irr_rent,
    }


def _last_user_message(chat: List[Dict[str, str]]) -> str:
    for msg in reversed(chat or []):
        if isinstance(msg, dict) and msg.get("role") == "user":
            return (msg.get("content") or "").strip().lower()
    return ""

def suggest_action_chips(
    deal: Dict[str, Any],
    mi: Dict[str, Any],
    metrics: Dict[str, Any],
    grade: Dict[str, Any],
    chat: Optional[List[Dict[str, str]]] = None
) -> List[Dict[str, str]]:
    """Adaptive action chips shown under the assistant's last message.

    Ranked by:
      1) quick sensitivity (what moves IRR the most),
      2) grade flags (where the model sees risk),
      3) last user message context (what the user is asking about right now).
    """
    actions = suggest_actions(deal, mi, metrics, grade)
    sens = quick_sensitivity(deal, mi, metrics)
    flags = grade.get("flags", []) if isinstance(grade, dict) else []
    last_user = _last_user_message(chat or [])

    def _ctx_bonus(cmd: str) -> float:
        cmd = (cmd or "").lower()
        if not last_user:
            return 0.0

        buckets = {
            "rent": ["rent", "lease", "rents", "market rent"],
            "vacancy": ["vacancy", "occupancy", "tenant", "turnover"],
            "expenses": ["expense", "oer", "utilities", "repairs", "maintenance", "hoa", "insurance", "tax"],
            "debt": ["rate", "interest", "loan", "debt", "amort", "refi", "refinance", "dscr"],
            "exit": ["exit", "cap", "cap rate", "sale", "sell", "disposition"],
            "sensitivity": ["sensitivity", "stress", "downside", "what if", "scenario"],
        }

        active = set()
        for b, kws in buckets.items():
            if any(kw in last_user for kw in kws):
                active.add(b)

        if not active:
            return 0.0

        bonus = 0.0
        if "rent" in active and "rent" in cmd:
            bonus += 0.45
        if "vacancy" in active and "vacancy" in cmd:
            bonus += 0.50
        if "expenses" in active and (("expense" in cmd) or ("tax" in cmd) or ("insurance" in cmd) or ("hoa" in cmd) or ("utilities" in cmd)):
            bonus += 0.50
        if "debt" in active and (("rate" in cmd) or ("down payment" in cmd) or ("amort" in cmd) or ("refi" in cmd)):
            bonus += 0.45
        if "exit" in active and (("exit cap" in cmd) or ("cap" in cmd) or ("sale" in cmd)):
            bonus += 0.45
        if "sensitivity" in active and ("sensitivity" in cmd or "stress" in cmd):
            bonus += 0.60
        return bonus

    def score(a: Dict[str, str]) -> float:
        cmd = (a.get("command") or "").lower()
        sc = 0.0

        # Sensitivity weighting
        if "exit cap" in cmd:
            sc += 5.0 * float(sens.get("exit_cap_+50bps", 0.0))
        if "rate" in cmd:
            sc += 5.0 * float(sens.get("rate_+50bps", 0.0))
        if "rent" in cmd:
            sc += 3.0 * float(sens.get("rent_growth_-1pt", 0.0))

        # Flag weighting
        for f in flags:
            lf = str(f).lower()
            if ("expense" in lf or "oer" in lf) and ("expense" in cmd or "oer" in cmd):
                sc += 0.35
            if "vacancy" in lf and "vacancy" in cmd:
                sc += 0.35
            if "rent" in lf and "rent" in cmd:
                sc += 0.30
            if "cap" in lf and "exit cap" in cmd:
                sc += 0.30
            if "rate" in lf and "rate" in cmd:
                sc += 0.25

        # Context weighting
        sc += _ctx_bonus(cmd)

        # Encourage exploration tools when volatility is high
        if "sensitivity" in cmd or "stress" in cmd:
            sc += 0.15 + (0.8 if max(sens.get("exit_cap_+50bps",0), sens.get("rate_+50bps",0), sens.get("rent_growth_-1pt",0)) > 0.02 else 0.0)
        return sc

    actions_sorted = sorted(actions, key=score, reverse=True)

    # If user context exists, prefer matching actions but keep at least one exploration tool.
    if last_user:
        wants = []
        if any(k in last_user for k in ["rent", "lease"]): wants.append("rent")
        if any(k in last_user for k in ["vacancy", "occup", "tenant"]): wants.append("vacancy")
        if any(k in last_user for k in ["expense", "oer", "tax", "insurance", "hoa", "utility", "repairs", "maintenance"]): wants.append("expenses")
        if any(k in last_user for k in ["rate", "loan", "debt", "refi", "amort"]): wants.append("debt")
        if any(k in last_user for k in ["exit", "cap", "sell", "sale"]): wants.append("exit")
        if any(k in last_user for k in ["stress", "sensitivity", "scenario", "what if"]): wants.append("sensitivity")

        def matches(a):
            c = (a.get("command") or "").lower()
            if "rent" in wants and "rent" in c: return True
            if "vacancy" in wants and "vacancy" in c: return True
            if "expenses" in wants and (("expense" in c) or ("tax" in c) or ("insurance" in c) or ("hoa" in c) or ("utilities" in c)): return True
            if "debt" in wants and (("rate" in c) or ("down payment" in c) or ("amort" in c) or ("refi" in c)): return True
            if "exit" in wants and (("exit cap" in c) or ("cap" in c) or ("sale" in c)): return True
            if "sensitivity" in wants and ("sensitivity" in c or "stress" in c): return True
            return False

        focused = [a for a in actions_sorted if matches(a)]
        explore = [a for a in actions_sorted if ("sensitivity" in (a.get("command") or "").lower() or "stress" in (a.get("command") or "").lower())]
        chips = (focused[:4] + explore[:2])[:5] if focused else actions_sorted[:5]
    else:
        chips = actions_sorted[:5]

    # Always ensure at least one grid/stress option exists
    if not any(("sensitivity" in (c.get("command") or "").lower() or "stress" in (c.get("command") or "").lower()) for c in chips):
        for a in actions_sorted:
            c = (a.get("command") or "").lower()
            if "sensitivity" in c or "stress" in c:
                chips = chips[:-1] + [a]
                break
    return chips


def maybe_render_shareable_memo(workspace_id: int):
    memo_slug = st.query_params.get("memo_slug")
    if memo_slug:
        memo_obj = load_memo_by_slug(workspace_id, str(memo_slug))
        if memo_obj:
            meta = memo_obj["_meta"]
            st.markdown(f"## Shareable Memo — `{meta.get('slug')}`")
            st.caption("View-only memo page. Remove `memo_slug` from the URL to return to the app.")
            d = memo_obj["deal"]; m = memo_obj["metrics"]; g = memo_obj["grade"]; mod = memo_obj["model"]
            st.markdown(f"**{d.get('address','')}**  \nGrade: **{g['letter']} ({g['score']:.0f})** · IRR: **{mod.get('irr_annual',0):.1%}** · OER: **{m.get('oer',0):.1%}** · NOI: **${m.get('noi',0):,.0f}**")
            st.stop()

# ============================
# Underwrite
# ============================

# ============================================================
# Chat Threads UI (Pipeline as "chat history")
# ============================================================

def _get_memo_from_deal_row(row) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    payload = json.loads(row[-1])
    return payload.get("memo")

def _suggest_followups(flags: List[str]) -> List[str]:
    qs = []
    for f in (flags or [])[:4]:
        lf = f.lower()
        if "expense" in lf:
            qs.append("Break down expenses: what line items drive OER and what can be reduced?")
        elif "vacancy" in lf:
            qs.append("What is the market vacancy and how does it change cashflow?")
        elif "cap rate" in lf:
            qs.append("What comps justify the exit cap rate and current cap rate?")
        elif "irr" in lf:
            qs.append("What assumptions must be true to get IRR above 12%?")
        else:
            qs.append(f"What evidence do we need to validate: {f}")
    if not qs:
        qs = ["What’s the biggest risk on this deal?", "What assumption is most sensitive?", "What would make this deal a 'No'?"]
    out = []
    for q in qs:
        if q not in out:
            out.append(q)
    return out[:4]

def _render_bubbles(chat_msgs: List[Dict[str,str]]):
    st.markdown('<div class="chatWrap">', unsafe_allow_html=True)
    for msg in chat_msgs:
        role = msg.get("role","assistant")
        cls = "user" if role == "user" else "assistant"
        content = (msg.get("content","") or "").replace("\n","<br/>")
        st.markdown(f'''
        <div class="bubble {cls}">
          <div class="role">{role.upper()}</div>
          <div>{content}</div>
        </div>
        ''', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# --- Sidebar: Threads (Pipeline) ---
if not st.session_state.get("email"):
    st.info("Enter your email in the sidebar to enable threads + saved deals.")
    st.stop()

rows_all = list_deals(workspace_id, None)
threads = []
for (deal_id, created, folder_, address, slug, gl, gs, irr, oer, noi, payload) in rows_all:
    memo = json.loads(payload).get("memo", {})
    threads.append({
        "deal_id": int(deal_id),
        "created_at": created,
        "folder": folder_,
        "address": address,
        "slug": slug,
        "grade": gl,
        "score": gs,
        "irr": irr,
        "oer": oer,
        "noi": noi,
        "memo": memo
    })

with st.sidebar:
    st.markdown("### Threads")
    st.caption("Pipeline works like chat history. Click a deal to open its thread.")

    st.markdown("#### New deal")
    link = st.text_input("Paste listing link/address", key="thread_import_link", placeholder="Paste link or address…")
    if st.button("Import", use_container_width=True):
        if link.strip():
            st.session_state.deal = import_listing(link.strip())
            st.session_state.draft_model_inputs = apply_memory_defaults(workspace_id, st.session_state.deal, st.session_state.get("draft_model_inputs") or {})
            st.session_state.active_deal_id = None
            st.session_state.chat = [{"role":"assistant","content":"Imported. Ask follow-ups or adjust assumptions (e.g., “vacancy to 10% and taxes to 22000”)."}]
            audit(workspace_id, st.session_state["email"], "listing_imported", "listing", None, {"input": link.strip()})
            st.rerun()
        else:
            st.warning("Paste a link or address.")

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    folder_filter = st.selectbox("Folder", ["All"] + folders, index=0)
    q = st.text_input("Search", value="", placeholder="Search address or messages…")

    filtered = threads
    if folder_filter != "All":
        filtered = [t for t in filtered if t["folder"] == folder_filter]
    if q.strip():
        qq = q.strip().lower()
        filtered = [t for t in filtered if qq in _search_blob(t)]

    if not filtered:
        st.caption("No saved deals yet. Import a new deal above.")
    else:
        # ChatGPT-like ordering: pinned first, then most recent
        filtered = sorted(filtered, key=lambda x: (0 if _is_pinned(x["memo"]) else 1, -int(x["deal_id"])))[:160]
        st.markdown('<div class="threadList">', unsafe_allow_html=True)

        for t in filtered:
            memo = t["memo"] or {}
            pinned = _is_pinned(memo)
            ts = _rel_time(str(t.get("created_at","")))
            title = f'{t["grade"]} • {t["address"] or "Deal"}'
            if len(title) > 42:
                title = title[:42].rstrip() + "…"
            preview = _chat_preview(memo)

            # Two controls: pin toggle + open
            c_pin, c_open = st.columns([1, 6], gap="small")
            with c_pin:
                icon = "★" if pinned else "☆"
                if st.button(icon, key=f"pin_{t['deal_id']}", help="Pin/unpin", use_container_width=True):
                    new_memo = _set_pinned_in_memo(memo, not pinned)
                    update_deal_latest(
                        workspace_id, int(t["deal_id"]),
                        t["grade"], float(t["score"]), float(t["irr"]),
                        float(t["oer"]), float(t["noi"]),
                        {"memo": new_memo}
                    )
                    st.rerun()

            with c_open:
                st.markdown(f'''
                <div class="threadItem">
                  <div class="threadTop">
                    <div class="threadTitle">{title}</div>
                    <div class="threadMeta">{("pinned • " if pinned else "")}{ts}</div>
                  </div>
                  <div class="threadPreview">{preview}</div>
                </div>
                ''', unsafe_allow_html=True)

                if st.button("Open", key=f"open_{t['deal_id']}", use_container_width=True):
                    st.session_state.active_deal_id = int(t["deal_id"])
                    st.session_state.deal = None
                    st.session_state.chat = (memo.get("chat") or [{"role":"assistant","content":"Thread loaded. Ask changes like “rent to 1750” or “vacancy to 9%”."}])
                    st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)


    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    with st.expander("Workspace tools", expanded=False):
        st.caption("Exports + governance are what companies pay for.")
        if threads:
            import io
            df = pd.DataFrame([{
                "deal_id": t["deal_id"], "folder": t["folder"], "address": t["address"], "slug": t["slug"],
                "grade": t["grade"], "score": round(float(t["score"]),1),
                "irr": float(t["irr"]), "oer": float(t["oer"]), "noi": float(t["noi"])
            } for t in threads]).sort_values(["folder","irr","score"], ascending=[True, False, False])
            st.download_button("Export CSV", data=df.to_csv(index=False).encode("utf-8"), file_name=f"{BRAND}_pipeline.csv", use_container_width=True)

            xbuf = io.BytesIO()
            with pd.ExcelWriter(xbuf, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name="Pipeline", index=False)
                list_audit(workspace_id, limit=500).to_excel(writer, sheet_name="AuditLog", index=False)
                pd.DataFrame([get_calibration(workspace_id)]).to_excel(writer, sheet_name="Calibration", index=False)
                pd.DataFrame([get_settings(workspace_id)]).to_excel(writer, sheet_name="Settings", index=False)
            xbuf.seek(0)
            st.download_button("Export Excel Bundle", data=xbuf.read(), file_name=f"{BRAND}_workspace_bundle.xlsx", use_container_width=True)
        else:
            st.caption("Save at least one deal to export.")

    role = st.session_state.get("role","analyst")
    with st.expander("Admin", expanded=False):
        st.caption("Roles + invites + webhooks (corporate-ready).")
        if role != "admin":
            st.info("You are an Analyst. Admin controls are locked in this POC.")
        users_df = list_users(workspace_id)
        st.dataframe(users_df, use_container_width=True, height=180)

        if role == "admin":
            st.markdown("#### Invitations")
            inv_email = st.text_input("Invite email", value="", key="inv_email_thread")
            inv_role = st.selectbox("Role", ["analyst","admin"], index=0, key="inv_role_thread")
            if st.button("Generate invite", use_container_width=True, key="gen_inv_thread"):
                if inv_email.strip():
                    code = upsert_invite(workspace_id, inv_email.strip(), inv_role)
                    st.success("Invite created.")
                    st.code(f"?invite={code}", language="text")
                else:
                    st.warning("Enter an email.")

            st.markdown("#### Webhook (optional)")
            settings = get_settings(workspace_id)
            webhook_new = st.text_input("Webhook URL", value=settings.get("webhook_url",""), key="wh_thread")
            if st.button("Save webhook", use_container_width=True):
                s = get_settings(workspace_id)
                upsert_settings(workspace_id, s["folders"], s["scoring_profile"], webhook_new.strip())
                st.success("Saved.")

# --- Main: Either open a saved thread or work on an imported draft ---
active_id = st.session_state.get("active_deal_id")
active_memo = None
active_row = None

maybe_render_shareable_memo(workspace_id)

if active_id:
    active_row = get_deal_row(workspace_id, int(active_id))
    active_memo = _get_memo_from_deal_row(active_row)

draft_deal = st.session_state.get("deal")

if not active_memo and not draft_deal:
    st.markdown('<div class="h1">Chat underwriting</div>', unsafe_allow_html=True)
    st.markdown('<div class="p">Import a listing from the sidebar, then chat to refine assumptions. Saved deals appear as threads.</div>', unsafe_allow_html=True)
    st.stop()

if draft_deal:
    calib = get_calibration(workspace_id)
    mi = st.session_state.get("draft_model_inputs") or {
        "hold_years": 5, "rent_growth": 0.03, "expense_growth": 0.025,
        "exit_cap": 0.065, "sale_cost_pct": 0.05,
        "down_payment_pct": 0.25, "interest_rate": 0.065, "amort_years": 30
    }
    mi = apply_memory_defaults(workspace_id, draft_deal, mi)
    st.session_state["draft_model_inputs"] = mi

    m = compute_metrics(draft_deal, calib)
    model = build_cashflows(draft_deal, m, int(mi["hold_years"]), float(mi["rent_growth"]), float(mi["expense_growth"]),
                            float(mi["exit_cap"]), float(mi["sale_cost_pct"]),
                            float(mi["down_payment_pct"]), float(mi["interest_rate"]), int(mi["amort_years"]))
    g = aire_grade(m, float(model["irr_annual"]), calib, scoring_profile)

    memo_payload = {
        "deal": draft_deal, "metrics": m, "grade": g, "model": model,
        "model_inputs": mi, "workspace": {"name": ws_name, "profile": scoring_profile},
        "chat": st.session_state.get("chat", [])
    }
    mode = "draft"
else:
    memo_payload = active_memo
    mode = "saved"

deal = memo_payload["deal"]
m = memo_payload["metrics"]
g = memo_payload["grade"]
model = memo_payload["model"]
mi = memo_payload.get("model_inputs", {})

left, right = st.columns([3,2], gap="large")

with left:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown(f"<div class='h2'>{'New deal' if mode=='draft' else 'Deal thread'}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='p'><b>{deal.get('address','')}</b></div>", unsafe_allow_html=True)

    st.markdown(f'''
    <div class="kpiRow">
      <div class="kpi"><div class="label">Grade</div><div class="value">{g['letter']} <span class="small">({g['score']:.0f})</span></div></div>
      <div class="kpi"><div class="label">IRR</div><div class="value">{model.get('irr_annual',0):.1%}</div></div>
      <div class="kpi"><div class="label">Expense Ratio</div><div class="value">{m.get('oer',0):.1%}</div></div>
      <div class="kpi"><div class="label">NOI</div><div class="value">${m.get('noi',0):,.0f}</div></div>
    </div>
    ''', unsafe_allow_html=True)

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    st.session_state.setdefault("chat", memo_payload.get("chat") or [{"role":"assistant","content":"Ask me to adjust assumptions. Example: “vacancy to 10% and taxes to 22000”."}])
    _render_bubbles(st.session_state.chat)

    # Action chips under the assistant's last message
    chips = suggest_action_chips(deal, mi, m, g, st.session_state.chat)
    if chips:
        st.markdown("<div class='chipHint'><b>Quick actions</b> (one-click)</div>", unsafe_allow_html=True)
        cols = st.columns(min(len(chips), 5))
        for i, chip in enumerate(chips):
            with cols[i]:
                if st.button(chip['label'], key=f"chip_{i}_{mode}", use_container_width=True):
                    st.session_state.chat.append({'role':'user','content': chip['command']})
                    deal_updated, reply = apply_chat_update(chip['command'], dict(deal))
                    st.session_state.chat.append({'role':'assistant','content': reply})
                    if mode == 'draft':
                        st.session_state.deal = deal_updated
                        memo_payload['deal'] = deal_updated
                    else:
                        st.session_state.saved_working_deal = deal_updated
                    audit(workspace_id, st.session_state['email'], 'action_chip', 'deal_thread', int(active_id) if active_id else None, {'command': chip['command'], 'label': chip['label']})
                    st.rerun()


    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    st.markdown("<div class='p'><b>Suggested follow-ups</b></div>", unsafe_allow_html=True)
    st.markdown("<div class='p'><b>Suggested actions</b></div>", unsafe_allow_html=True)
    acts = suggest_actions(deal, mi, m, g)
    if acts:
        a_cols = st.columns(min(len(acts), 4))
        for i, a in enumerate(acts[:8]):
            with a_cols[i % 4]:
                if st.button(a['label'], key=f"act_{i}_{mode}", use_container_width=True):
                    st.session_state.chat.append({'role':'user','content': a['command']})
                    deal_updated, reply = apply_chat_update(a['command'], dict(deal))
                    st.session_state.chat.append({'role':'assistant','content': reply})
                    if mode == 'draft':
                        st.session_state.deal = deal_updated
                        memo_payload['deal'] = deal_updated
                    else:
                        st.session_state.saved_working_deal = deal_updated
                    audit(workspace_id, st.session_state['email'], 'suggested_action', 'deal_thread', int(active_id) if active_id else None, {'command': a['command'], 'label': a['label']})
                    st.rerun()

    sQs = _suggest_followups(g.get("flags", []))
    cols = st.columns(len(sQs))
    for i, qx in enumerate(sQs):
        with cols[i]:
            if st.button("Ask", key=f"sugg_{i}", use_container_width=True):
                st.session_state.chat.append({"role":"user","content":qx})
                st.session_state.chat.append({"role":"assistant","content":"Good question. Adjust with “rent to … / vacancy to … / taxes to … / price to …” then click Re-run."})
                st.rerun()

    user = st.chat_input("Message AIRE… (e.g., rent to 1750, vacancy to 9%)")
    if user:
        st.session_state.chat.append({"role":"user","content":user})
        deal_updated, reply = apply_chat_update(user, dict(deal))
        st.session_state.chat.append({"role":"assistant","content":reply})
        if mode == "draft":
            st.session_state.deal = deal_updated
            memo_payload["deal"] = deal_updated
        else:
            st.session_state.saved_working_deal = deal_updated
        audit(workspace_id, st.session_state["email"], "assistant_update", "deal_thread", int(active_id) if active_id else None, {"user_text": user, "reply": reply})
        st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

with right:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("<div class='h2'>Assumptions</div>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        mi["hold_years"] = st.number_input("Hold (years)", 1, 30, int(mi.get("hold_years",5)))
        mi["rent_growth"] = st.slider("Rent growth", 0.0, 0.12, float(mi.get("rent_growth",0.03)), 0.0025)
        mi["expense_growth"] = st.slider("Expense growth", 0.0, 0.12, float(mi.get("expense_growth",0.025)), 0.0025)
        mi["exit_cap"] = st.slider("Exit cap", 0.03, 0.12, float(mi.get("exit_cap",0.065)), 0.0025)
    with c2:
        mi["down_payment_pct"] = st.slider("Down payment", 0.05, 0.60, float(mi.get("down_payment_pct",0.25)), 0.01)
        mi["interest_rate"] = st.slider("Rate", 0.0, 0.15, float(mi.get("interest_rate",0.065)), 0.0025)
        mi["amort_years"] = st.number_input("Amort (years)", 5, 40, int(mi.get("amort_years",30)))
        mi["sale_cost_pct"] = st.slider("Sale costs", 0.0, 0.10, float(mi.get("sale_cost_pct",0.05)), 0.005)

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    st.markdown("<div class='p'><b>Confirm assumptions</b></div>", unsafe_allow_html=True)
    st.checkbox("Rents reflect real comps", value=True)
    st.checkbox("Taxes/insurance verified", value=False)
    st.checkbox("Vacancy aligns with market", value=False)
    st.checkbox("Exit cap is defensible", value=False)

    if st.button("Re-run analysis", use_container_width=True):
        calib = get_calibration(workspace_id)
        if mode == "draft":
            dcur = st.session_state.get("deal") or dict(deal)
        else:
            dcur = st.session_state.get("saved_working_deal") or dict(deal)
        m2 = compute_metrics(dcur, calib)
        model2 = build_cashflows(dcur, m2, int(mi["hold_years"]), float(mi["rent_growth"]), float(mi["expense_growth"]),
                                 float(mi["exit_cap"]), float(mi["sale_cost_pct"]),
                                 float(mi["down_payment_pct"]), float(mi["interest_rate"]), int(mi["amort_years"]))
        g2 = aire_grade(m2, float(model2["irr_annual"]), calib, scoring_profile)
        memo_payload.update({"deal": dcur, "metrics": m2, "model": model2, "grade": g2, "model_inputs": mi, "chat": st.session_state.chat})
        if mode == "draft":
            st.session_state.deal = dcur
            st.session_state["draft_model_inputs"] = mi
        else:
            st.session_state.saved_working_memo = memo_payload
        st.rerun()

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    pdf = generate_memo_pdf_bytes(BRAND, ACCENT, st.session_state.brand_logo_b64, memo_payload)
    st.download_button("Download memo (PDF)", data=pdf, file_name=f"{BRAND}_Memo_{slugify(deal.get('address','property'))}.pdf", use_container_width=True)

    if mode == "draft":
        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
        folder = st.selectbox("Save to folder", folders, index=folders.index("Maybe") if "Maybe" in folders else 0)
        if st.button("Save as new thread", use_container_width=True):
            update_memory_from_memo(workspace_id, memo_payload)

            slug = slugify(f"{deal.get('city','')}-{m.get('units',1)}u-{g.get('letter','A')}-{deal.get('address','')}")
            memo_payload["chat"] = st.session_state.chat
            did = save_deal(workspace_id, st.session_state["email"], deal.get("source","demo"), deal.get("address",""),
                            folder, slug, g["letter"], float(g["score"]), float(model["irr_annual"]), float(m["oer"]), float(m["noi"]),
                            {"memo": memo_payload})
            save_memo(workspace_id, st.session_state["email"], slug, memo_payload, BRAND, ACCENT)
            st.session_state.active_deal_id = did
            st.session_state.deal = None
            st.success(f"Saved. Opened thread #{did}.")
            st.rerun()
    else:
        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
        st.caption("Update this thread to create a new version (audit + version history).")
        if st.button("Update thread (new version)", use_container_width=True):
            update_memory_from_memo(workspace_id, memo_payload)

            calib = get_calibration(workspace_id)
            working = st.session_state.get("saved_working_memo") or memo_payload
            dcur = working["deal"]
            m2 = compute_metrics(dcur, calib)
            model2 = build_cashflows(dcur, m2, int(mi["hold_years"]), float(mi["rent_growth"]), float(mi["expense_growth"]),
                                     float(mi["exit_cap"]), float(mi["sale_cost_pct"]),
                                     float(mi["down_payment_pct"]), float(mi["interest_rate"]), int(mi["amort_years"]))
            g2 = aire_grade(m2, float(model2["irr_annual"]), calib, scoring_profile)
            working.update({"metrics": m2, "model": model2, "grade": g2, "model_inputs": mi, "chat": st.session_state.chat})
            update_deal_latest(workspace_id, int(active_id), g2["letter"], float(g2["score"]), float(model2["irr_annual"]),
                               float(m2["oer"]), float(m2["noi"]), {"memo": working})
            vnum = next_version_num(workspace_id, int(active_id))
            save_deal_version(workspace_id, int(active_id), vnum, "thread_update",
                              g2["letter"], float(g2["score"]), float(model2["irr_annual"]), float(m2["oer"]), float(m2["noi"]), {"memo": working})
            audit(workspace_id, st.session_state["email"], "deal_thread_updated", "deal", int(active_id), {"version": vnum})
            st.success("Thread updated + versioned.")
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)