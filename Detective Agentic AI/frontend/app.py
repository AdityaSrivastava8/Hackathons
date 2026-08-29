import sys
import os

# Update system path FIRST so Python can locate internal modules on Streamlit Cloud
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
import json
import time
import io
import pandas as pd
from fpdf import FPDF
from agent.analyzer import DetectiveAgent
from agent.outreach import (
    scrape_leads_sync,
    send_cold_emails,
    load_leads,
    save_leads,
    COLD_EMAIL_SUBJECT,
    COLD_EMAIL_BODY,
)
from agent.billing import (
    submit_payment,
    submit_topup,
    approve_payment,
    flag_partial,
    get_pending_payments,
    get_partial_by_utr,
    STATUS_PENDING,
    STATUS_APPROVED,
    STATUS_PARTIAL,
    STATUS_TOPUP_DONE,
    STATUS_FLAGGED,
)

# ── Page config (MUST be first Streamlit call) ─────────────────────────────────
st.set_page_config(
    page_title="Detective Agentic AI - Criminal Profiler",
    page_icon="🕵️‍♂️",
    layout="wide"
)

# ── Data directory ─────────────────────────────────────────────────────────────
DATA_DIR      = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
PAYMENTS_FILE = os.path.join(DATA_DIR, "payments.json")

def _ensure_data():
    os.makedirs(DATA_DIR, exist_ok=True)

def load_payments():
    _ensure_data()
    if not os.path.exists(PAYMENTS_FILE):
        return []
    try:
        with open(PAYMENTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_payments(payments):
    _ensure_data()
    with open(PAYMENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(payments, f, indent=2, ensure_ascii=False)

# ── Admin password ─────────────────────────────────────────────────────────────
ADMIN_PASSWORD = "Adi"   # master admin password

def _get_admin_password() -> str:
    try:
        return str(st.secrets["ADMIN_PASSWORD"])
    except Exception:
        return ADMIN_PASSWORD

# ── Session State defaults ─────────────────────────────────────────────────────
_ss_defaults = {
    "evals_left":          25,
    "max_evals":           25,
    "current_tier":        "Pro Agency Trial",
    "latest_results":      None,
    "pending_plan":        None,
    "pending_amount":      None,
    "pending_evals":       None,
    "is_admin":            False,
    "admin_open":          False,
    "show_billing_portal": False,
    "partial_utr":         None,   # UTR of a partial payment waiting for top-up
}
for k, v in _ss_defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Agent ──────────────────────────────────────────────────────────────────────
def load_agent():
    return DetectiveAgent()

agent = load_agent()

# ── UPI QR helper ──────────────────────────────────────────────────────────────
UPI_VPA  = "adityasriv@ptyes"
UPI_NAME = "Aditya Srivastava"

def make_upi_qr(amount: int, plan_ref: str) -> bytes:
    upi_uri = (
        f"upi://pay?pa={UPI_VPA}&pn={UPI_NAME.replace(' ', '%20')}"
        f"&am={amount}&cu=INR&tn={plan_ref.replace(' ', '_')}"
    )

    try:
        import segno
        buf = io.BytesIO()
        qr = segno.make(upi_uri, error="H")
        qr.save(buf, kind="png", scale=8, border=4, dark="black", light="white")
        buf.seek(0)
        return buf.getvalue()
    except ImportError:
        pass

    import qrcode as _qr
    import qrcode.constants as _qrc
    q = _qr.QRCode(error_correction=_qrc.ERROR_CORRECT_H, box_size=8, border=4)
    q.add_data(upi_uri)
    q.make(fit=True)
    pil_img = q.make_image(fill_color="black", back_color="white").get_image()
    buf = io.BytesIO()
    pil_img.save(buf, "PNG")
    buf.seek(0)
    return buf.getvalue()

# ── PDF Report ─────────────────────────────────────────────────────────────────
def generate_pdf_report(suspect_name, age, tendency_score, risk_level, behaviors, matched_cases):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "EXECUTIVE CRIMINAL PROFILE REPORT", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, f"Suspect Name: {suspect_name}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Age: {age if age else 'Unknown'}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Calculated Tendency Score: {tendency_score}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Risk Assessment Level: {risk_level}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Observed Behaviors & Modus Operandi:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 6, str(behaviors))
    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Matched Historical Precedents:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    for idx, case in enumerate(matched_cases, 1):
        pdf.cell(0, 6,
            f"{idx}. {case.get('case_title','Unknown Case')} ({case.get('location','N/A')})",
            new_x="LMARGIN", new_y="NEXT")
        snippet = case.get("summary", case.get("snippet", ""))[:150]
        pdf.multi_cell(0, 5, f"   Snippet: {snippet}...")
        pdf.ln(2)
    return bytes(pdf.output())

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

st.sidebar.header("⚙️ Case Indexer")
uploaded_file = st.sidebar.file_uploader("Upload Case JSON to Vector DB", type=["json"])
if uploaded_file is not None:
    try:
        case_data = json.load(uploaded_file)
        cases_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "cases"))
        os.makedirs(cases_dir, exist_ok=True)
        save_path = os.path.join(cases_dir, uploaded_file.name)
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(case_data, f, indent=4)
        st.sidebar.success(f"Indexed '{uploaded_file.name}'!")
    except Exception as e:
        st.sidebar.error(f"Upload failed: {e}")

st.sidebar.divider()

st.sidebar.markdown("### B2B Agency Plan")
_max  = st.session_state.max_evals
_left = st.session_state.evals_left
quota_display = "Unlimited" if _max == "Unlimited" else f"{min(_left, _max)}/{_max}"

st.sidebar.info(
    f"**Current Tier:** {st.session_state.current_tier}\n\n"
    f"**Evaluations Remaining:** {quota_display}"
)
if _max != "Unlimited" and isinstance(_left, int) and _left <= 0:
    st.sidebar.error("⚠️ Trial Limit Reached")

if st.sidebar.button("💳 Upgrade / Billing Portal", use_container_width=True, key="sb_upgrade"):
    st.session_state.show_billing_portal = not st.session_state.show_billing_portal
    if not st.session_state.show_billing_portal:
        st.session_state.pending_plan   = None
        st.session_state.pending_amount = None
        st.session_state.pending_evals  = None
    st.rerun()

if st.session_state.show_billing_portal:
    PLANS_SIDEBAR = {
        "🥉 Starter":    {"amount": 500,  "evals": 100,         "label": "₹500/mo — 100 Evals"},
        "🥈 Pro":        {"amount": 1000, "evals": 500,         "label": "₹1,000/mo — 500 Evals"},
        "🥇 Enterprise": {"amount": 2000, "evals": "Unlimited", "label": "₹2,000/mo — Unlimited"},
    }
    st.sidebar.markdown("#### 📋 Choose a Plan")
    for pname, pinfo in PLANS_SIDEBAR.items():
        sb_key = f"sb_plan_{pname.replace(' ','_').replace('/','_')}"
        if st.sidebar.button(f"{pname} — {pinfo['label']}", key=sb_key, use_container_width=True):
            st.session_state.pending_plan   = pname
            st.session_state.pending_amount = pinfo["amount"]
            st.session_state.pending_evals  = pinfo["evals"]
            st.rerun()

    if st.session_state.pending_plan:
        _plan   = st.session_state.pending_plan
        _amount = st.session_state.pending_amount
        _evals  = st.session_state.pending_evals

        st.sidebar.markdown(f"---\n**💳 Pay for {_plan}**")
        st.sidebar.markdown(f"Amount: **₹{_amount:,}** · UPI: `{UPI_VPA}`")

        try:
            _qr_bytes = make_upi_qr(_amount, f"Plan_Upgrade_{_plan.split()[-1]}")
            st.sidebar.image(_qr_bytes, caption=f"Scan to Pay ₹{_amount:,}", width=200)
        except Exception:
            st.sidebar.code(
                f"upi://pay?pa={UPI_VPA}&pn=Aditya%20Srivastava"
                f"&am={_amount}&cu=INR&tn=Plan_Upgrade",
                language="text"
            )

        with st.sidebar.form(key="sb_utr_form"):
            _utr = st.text_input(
                "UTR / Transaction Ref No.",
                placeholder="e.g. 426789012345",
                max_chars=30
            )
            _paid_str = st.text_input(
                "Amount You Paid (₹)",
                placeholder=f"e.g. {_amount}",
                max_chars=10
            )
            _sub = st.form_submit_button("📨 Submit Payment Proof", use_container_width=True)

        if _sub:
            if not _utr.strip():
                st.sidebar.error("Please enter your UTR number.")
            elif not _paid_str.strip():
                st.sidebar.error("Please enter the amount you paid.")
            else:
                try:
                    _paid_val = float(_paid_str.replace(",", "").strip())
                except ValueError:
                    st.sidebar.error("Invalid amount — enter a number.")
                    _paid_val = None

                if _paid_val is not None:
                    _status, _msg, _remaining = submit_payment(
                        plan=_plan,
                        required_amount=float(_amount),
                        amount_paid=_paid_val,
                        evals=_evals,
                        utr=_utr.strip(),
                    )
                    if _status == STATUS_FLAGGED:
                        st.sidebar.error(_msg)
                    elif _status == STATUS_PARTIAL:
                        st.sidebar.warning(_msg)
                        st.session_state.partial_utr = _utr.strip()
                        st.session_state.show_billing_portal = False
                        st.rerun()
                    else:
                        st.sidebar.success("✅ Submitted! Quota will be unlocked after admin verification.")
                        st.session_state.pending_plan        = None
                        st.session_state.pending_amount      = None
                        st.session_state.pending_evals       = None
                        st.session_state.show_billing_portal = False
                        st.rerun()

if st.sidebar.button("🔄 Reset Demo & Clear Cache", use_container_width=True, key="sb_reset"):
    for k, v in _ss_defaults.items():
        st.session_state[k] = v
    st.rerun()

st.sidebar.divider()

# ── 🔐 Admin Portal Login ──────────────────────────────────────────────────────
with st.sidebar.expander("🔐 Admin Portal", expanded=False):
    if st.session_state.is_admin:
        st.success("✅ Logged in as Admin")
        if st.button("🔓 Logout Admin", use_container_width=True, key="btn_admin_logout"):
            st.session_state.is_admin   = False
            st.session_state.admin_open = False
            st.rerun()
    else:
        admin_pw = st.text_input(
            "Admin Password",
            type="password",
            placeholder="Enter admin password…",
            key="admin_pw_input"
        )
        if st.button("🔑 Login", use_container_width=True, key="btn_admin_login"):
            if admin_pw == _get_admin_password():
                st.session_state.is_admin = True
                st.rerun()
            else:
                st.error("❌ Incorrect password.")

# ── Admin Payment Approvals ───────────────────────────────────────────────────
if st.session_state.is_admin:
    st.sidebar.divider()
    if st.sidebar.button("🛠️ Admin Payment Approvals", use_container_width=True, key="sb_admin"):
        st.session_state.admin_open = not st.session_state.admin_open
        st.rerun()

    if st.session_state.admin_open:
        st.sidebar.markdown("#### 🧾 All Pending Submissions")
        _all_pending = get_pending_payments()
        if not _all_pending:
            st.sidebar.info("No pending submissions.")
        else:
            for i, pmt in enumerate(_all_pending):
                _putr      = pmt.get("utr```python
def matched(s):
    count = 0
    for char in s:
        if char == "(":
            count += 1
        elif char == ")":
            count -= 1
            if count < 0:
                return False
    return count == 0 
