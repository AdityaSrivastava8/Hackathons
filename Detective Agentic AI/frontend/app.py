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
@st.cache_resource
def load_agent():
    return DetectiveAgent()

agent = load_agent()

# ── UPI QR helper ──────────────────────────────────────────────────────────────
UPI_VPA  = "adityasriv@ptyes"
UPI_NAME = "Aditya Srivastava"

def make_upi_qr(amount: int, plan_ref: str) -> bytes:
    """
    Generate a UPI-payment QR code PNG as bytes.
    Uses segno (pure-Python, zero C deps, works on Streamlit Cloud),
    then falls back to qrcode[pil].
    """
    upi_uri = (
        f"upi://pay?pa={UPI_VPA}&pn={UPI_NAME.replace(' ', '%20')}"
        f"&am={amount}&cu=INR&tn={plan_ref.replace(' ', '_')}"
    )

    # ── Try segno (primary — pure Python) ─────────────────────────────────
    try:
        import segno
        buf = io.BytesIO()
        qr = segno.make(upi_uri, error="H")
        qr.save(buf, kind="png", scale=8, border=4, dark="black", light="white")
        buf.seek(0)
        return buf.getvalue()
    except ImportError:
        pass

    # ── Fallback: qrcode + Pillow ──────────────────────────────────────────
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

# ── Case Indexer (always visible) ─────────────────────────────────────────────
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

# ── B2B Plan status (always visible) ──────────────────────────────────────────
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
    # Reset any partially-selected plan when closing
    if not st.session_state.show_billing_portal:
        st.session_state.pending_plan   = None
        st.session_state.pending_amount = None
        st.session_state.pending_evals  = None
    st.rerun()

# ── Inline Billing Portal (renders directly under the button) ──────────────────
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

        # QR code rendered in sidebar
        try:
            _qr_bytes = make_upi_qr(_amount, f"Plan_Upgrade_{_plan.split()[-1]}")
            st.sidebar.image(_qr_bytes, caption=f"Scan to Pay ₹{_amount:,}", width=200)
        except Exception as _qe:
            st.sidebar.code(
                f"upi://pay?pa={UPI_VPA}&pn=Aditya%20Srivastava"
                f"&am={_amount}&cu=INR&tn=Plan_Upgrade",
                language="text"
            )

        # UTR + Amount submission form in sidebar
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

# ── Admin Payment Approvals (ADMIN ONLY) ──────────────────────────────────────
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
                _putr      = pmt.get("utr", "")
                _preq      = pmt.get("required_amount", pmt.get("amount", 0))
                _ppaid     = pmt.get("amount_paid",     pmt.get("amount", 0))
                _premain   = pmt.get("remaining_balance", 0)
                _pstatus   = pmt.get("status", "")
                _pevals    = pmt.get("evals", "?")
                _pplan     = pmt.get("plan", "?")

                _label = f"#{i+1} {_pplan} — UTR: {_putr}"
                with st.sidebar.expander(_label):
                    st.write(f"**Plan:** {_pplan}")
                    st.write(f"**Required:** ₹{_preq:,}")
                    st.write(f"**Paid:** ₹{_ppaid:,}")
                    if _premain:
                        st.write(f"**Deficit:** ₹{_premain:,}")
                    st.write(f"**Status:** {_pstatus}")
                    st.write(f"**UTR:** `{_putr}`")
                    st.write(f"**Submitted:** {pmt.get('timestamp','')}")
                    if pmt.get("topup_utrs"):
                        st.write(f"**Top-up UTRs:** {', '.join(pmt['topup_utrs'])}")

                    _acol, _fcol = st.columns(2)
                    # Approve button
                    if _acol.button("✅ Approve", key=f"pay_verify_{_putr}_approve"):
                        if approve_payment(_putr):
                            evals = _pevals
                            if evals == "Unlimited":
                                st.session_state.evals_left = "Unlimited"
                                st.session_state.max_evals  = "Unlimited"
                            else:
                                try:
                                    st.session_state.evals_left = int(evals)
                                    st.session_state.max_evals  = int(evals)
                                except Exception:
                                    pass
                            st.session_state.current_tier = _pplan
                            st.sidebar.success(f"✅ Quota unlocked — {_putr}")
                            st.rerun()
                    # Flag partial button
                    if _fcol.button("⚠️ Flag Partial", key=f"pay_verify_{_putr}_flag"):
                        if flag_partial(_putr):
                            st.session_state.partial_utr = _putr
                            st.sidebar.warning(f"Flagged as partial — user will be prompted for top-up.")
                            st.rerun()

# ── Contact / Feedback (always visible at bottom of sidebar) ──────────────────
st.sidebar.divider()
st.sidebar.markdown(
    "**💬 Feedback & Suggestions**\n\n"
    "Found a bug? Want a new feature?\n\n"
    "📧 [yeahboyadi@gmail.com](mailto:yeahboyadi@gmail.com)  \n"
    "📧 [akshat.v2166@gmail.com](mailto:akshat.v2166@gmail.com)"
)

# ══════════════════════════════════════════════════════════════════════════════
# MAIN AREA — Role-based tab list
# ══════════════════════════════════════════════════════════════════════════════
st.title("🕵️‍♂️ Detective Agentic AI & RAG Profiling System")
st.markdown("Automated criminal pattern recognition, risk evaluation, and precedent retrieval engine.")
st.divider()

# ── Partial Payment Alert Banner (shown above tabs if active) ─────────────────
if st.session_state.partial_utr:
    _prec = get_partial_by_utr(st.session_state.partial_utr)
    if _prec:
        _p_paid     = _prec.get("amount_paid", 0)
        _p_req      = _prec.get("required_amount", 0)
        _p_remain   = _prec.get("remaining_balance", 0)
        _p_plan     = _prec.get("plan", "")
        _p_utr      = _prec.get("utr", "")
        _p_evals    = _prec.get("evals", "")

        st.warning(
            f"⚠️ **Payment Incomplete** — You paid ₹{_p_paid:,.0f} out of "
            f"₹{_p_req:,.0f} for the **{_p_plan}** plan. "
            f"Please pay the remaining balance of **₹{_p_remain:,.0f}** to unlock your evaluations."
        )

        _tp_qr_col, _tp_inst_col = st.columns([1, 2])
        with _tp_qr_col:
            try:
                _tp_qr = make_upi_qr(int(_p_remain), f"TopUp_{_p_plan.split()[-1]}")
                st.image(_tp_qr, caption=f"Scan to Pay ₹{_p_remain:,.0f} (balance)", width=200)
            except Exception:
                st.code(
                    f"upi://pay?pa={UPI_VPA}&pn=Aditya%20Srivastava"
                    f"&am={int(_p_remain)}&cu=INR&tn=TopUp_Balance",
                    language="text"
                )

        with _tp_inst_col:
            st.markdown(
                f"**UPI ID:** `{UPI_VPA}`  \n"
                f"**Amount:** ₹{_p_remain:,.0f}  \n"
                f"**Payee:** Aditya Srivastava"
            )
            with st.form(key=f"topup_form_{_p_utr}"):
                _topup_utr = st.text_input(
                    "Enter Top-Up UTR / Transaction Ref",
                    placeholder="New 12-digit UTR after paying balance",
                    max_chars=30
                )
                _topup_sub = st.form_submit_button(
                    "📨 Submit Top-Up Proof", use_container_width=True, type="primary"
                )

            if _topup_sub:
                if not _topup_utr.strip():
                    st.error("Please enter your top-up UTR.")
                else:
                    _ts, _tm = submit_topup(_topup_utr.strip(), _p_utr)
                    if "✅" in _tm:
                        st.success(_tm)
                        st.session_state.partial_utr = None
                        st.rerun()
                    else:
                        st.error(_tm)

        st.divider()
    else:
        # Record no longer partial (admin approved) — clear flag
        st.session_state.partial_utr = None

# Build tab list dynamically based on auth state
_tab_labels = ["🔍 Profiling Dashboard", "💳 Billing & Plans", "📬 Contact & Feedback"]
if st.session_state.is_admin:
    _tab_labels.append("📢 B2B Agency Acquisition")

_tabs = st.tabs(_tab_labels)
tab_profile  = _tabs[0]
tab_billing  = _tabs[1]
tab_contact  = _tabs[2]
tab_outreach = _tabs[3] if st.session_state.is_admin else None

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — PROFILING DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
with tab_profile:
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Suspect Information & Observations")
        with st.form(key="suspect_profiling_form"):
            suspect_name = st.text_input("Suspect Name / Alias", placeholder="John Doe")
            age          = st.text_input("Age", placeholder="34")
            behaviors    = st.text_area(
                "Observed Behaviors, MO, & Traits",
                height=180,
                placeholder="Entering residential premises during late hours, targeting locked cabinets..."
            )
            submit_btn = st.form_submit_button(
                "Run Intelligenc 
