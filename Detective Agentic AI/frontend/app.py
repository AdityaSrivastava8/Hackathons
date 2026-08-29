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
                "Run Intelligence Analysis", type="primary", use_container_width=True
            )

    with col2:
        st.subheader("Analysis & Precedent Results")

        if submit_btn:
            if not behaviors.strip():
                st.warning("Please enter observed behaviors to analyze.")
            elif st.session_state.max_evals != "Unlimited" and st.session_state.evals_left <= 0:
                st.error("🚫 Evaluation Quota Exceeded! Please upgrade via the Billing tab.")
            else:
                with st.spinner("Analyzing traits against ChromaDB precedent vectors..."):
                    try:
                        name_str = suspect_name if suspect_name else "Unnamed Suspect"
                        
                        # Flexible agent caller to support different method signatures
                        def run_agent_eval(a_obj):
                            # Try standard positional call
                            try:
                                return a_obj.evaluate_suspect(name_str, behaviors)
                            except TypeError:
                                pass
                            
                            # Try named kwargs (mo_suspected / evidence_text)
                            try:
                                return a_obj.evaluate_suspect(
                                    suspect_name=name_str,
                                    mo_suspected=behaviors,
                                    evidence_text=behaviors
                                )
                            except TypeError:
                                pass
                            
                            # Fallback call
                            return a_obj.evaluate_suspect(name_str, behaviors, behaviors)

                        try:
                            res = run_agent_eval(agent)
                        except Exception:
                            load_agent.clear()
                            fresh_agent = load_agent()
                            res = run_agent_eval(fresh_agent)

                        # Successfully ran analysis -> Deduct 1 evaluation
                        if st.session_state.max_evals != "Unlimited":
                            st.session_state.evals_left = max(0, st.session_state.evals_left - 1)

                        st.session_state.latest_results = {
                            "name":           name_str,
                            "age":            age,
                            "behaviors":      behaviors,
                            "tendency_score": res.get("tendency_score", "0%"),
                            "risk_level":     res.get("risk_level", "UNKNOWN"),
                            "matched_cases":  res.get("similar_cases", []),
                            "summary_text":   res.get("summary", ""),
                            "timestamp":      time.time()
                        }
                        
                        st.rerun()  # Instantly update sidebar credit count

                    except Exception as err:
                        st.error(f"Analysis failed: {err}")

        if st.session_state.latest_results:
            res = st.session_state.latest_results
            m_col1, m_col2 = st.columns(2)
            m_col1.metric("Tendency Score", str(res["tendency_score"]))
            m_col2.metric("Risk Level", res["risk_level"])
            st.info(res["summary_text"])
            st.markdown("#### Matched Precedents")
            if res["matched_cases"]:
                for case in res["matched_cases"]:
                    with st.expander(
                        f"📌 {case.get('case_title','Historical Precedent')} ({case.get('location','Global')})"
                    ):
                        st.write(f"**Case ID:** {case.get('case_id','N/A')}")
                        st.write(f"**Details:** {case.get('summary', case.get('snippet','No snippet available.'))}")
            else:
                st.info("No close precedent matches found above threshold.")

            try:
                pdf_bytes = generate_pdf_report(
                    res["name"], res["age"], res["tendency_score"],
                    res["risk_level"], res["behaviors"], res["matched_cases"]
                )
                dynamic_key = f"dl_pdf_{int(res.get('timestamp', time.time()))}"
                st.download_button(
                    label="📥 Download Executive PDF Report",
                    data=pdf_bytes,
                    file_name=f"Profile_Report_{res['name'].replace(' ', '_')}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    key=dynamic_key
                )
            except Exception:
                st.caption("PDF generation ready.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — BILLING & UPI PAYMENT GATE
# ══════════════════════════════════════════════════════════════════════════════
with tab_billing:
    PLANS = {
        "🥉 Starter Agency": {"amount": 500,  "evals": 100,         "label": "₹500 / mo — 100 Evaluations"},
        "🥈 Pro Agency":      {"amount": 1000, "evals": 500,         "label": "₹1,000 / mo — 500 Evaluations"},
        "🥇 Enterprise SaaS": {"amount": 2000, "evals": "Unlimited", "label": "₹2,000 / mo — Unlimited Evaluations"},
    }

    st.subheader("Select Your Subscription Plan")
    st.caption("Quota is unlocked by the admin after UPI payment is verified.")

    p_col1, p_col2, p_col3 = st.columns(3)
    plan_cols = [p_col1, p_col2, p_col3]

    for col, (plan_name, plan_info) in zip(plan_cols, PLANS.items()):
        with col:
            st.markdown(f"### {plan_name}")
            st.markdown(f"**{plan_info['label']}**")
            if plan_name == "🥉 Starter Agency":
                st.markdown("* 100 Evaluations / mo\n* Standard RAG Precedent Search\n* Basic PDF Export")
            elif plan_name == "🥈 Pro Agency":
                st.markdown("* 500 Evaluations / mo\n* Fast ChromaDB Vector Search\n* Custom JSON File Indexer")
            else:
                st.markdown("* Unlimited Evaluations\n* Private Vector Database\n* Dedicated API & Priority Support")

            btn_key = f"plan_select_{plan_name.replace(' ','_').replace('/','_').replace('🥉','').replace('🥈','').replace('🥇','')}"
            if st.button(f"Select {plan_name}", key=btn_key, use_container_width=True):
                st.session_state.pending_plan   = plan_name
                st.session_state.pending_amount = plan_info["amount"]
                st.session_state.pending_evals  = plan_info["evals"]
                st.rerun()

    # ── UPI QR Payment Section ─────────────────────────────────────────────────
    if st.session_state.pending_plan:
        st.divider()
        plan   = st.session_state.pending_plan
        amount = st.session_state.pending_amount
        evals  = st.session_state.pending_evals

        st.subheader(f"💳 Complete Payment for {plan}")
        qr_col, inst_col = st.columns([1, 2])

        with qr_col:
            try:
                qr_bytes = make_upi_qr(amount, f"Detective_AI_{plan.split()[-1]}")
                st.image(qr_bytes, caption=f"Scan to Pay ₹{amount:,}", width=220)
            except Exception as e:
                st.warning(f"QR could not be generated: {e}")
                st.code(
                    f"upi://pay?pa={UPI_VPA}&pn=Aditya%20Srivastava"
                    f"&am={amount}&cu=INR&tn=Detective_AI_{plan.split()[-1]}",
                    language="text"
                )

        with inst_col:
            st.markdown(f"""
**Amount Payable:** ₹{amount:,}
**UPI ID:** `{UPI_VPA}`
**Payee Name:** Aditya Srivastava

**Steps:**
1. Open PhonePe / Google Pay / Paytm
2. Scan the QR code or pay to UPI ID above
3. Note the **12-digit UTR / Transaction Reference** shown in your payment app
4. Enter it below and click **Submit Proof**
            """)

            with st.form(key=f"utr_form_{plan.replace(' ','_').replace('/','_')}"):
                utr_input  = st.text_input(
                    "Enter UTR / Transaction Reference ID",
                    placeholder="e.g. 426789012345",
                    max_chars=30
                )
                paid_input = st.text_input(
                    "Amount You Paid (₹)",
                    placeholder=f"e.g. {amount}",
                    max_chars=10
                )
                submit_utr = st.form_submit_button("📨 Submit Payment Proof", use_container_width=True)

            if submit_utr:
                if not utr_input.strip():
                    st.error("Please enter your UTR / Transaction Reference.")
                elif not paid_input.strip():
                    st.error("Please enter the amount you paid.")
                else:
                    try:
                        paid_val = float(paid_input.replace(",", "").strip())
                    except ValueError:
                        st.error("Invalid amount — enter a number.")
                        paid_val = None

                    if paid_val is not None:
                        _s, _m, _r = submit_payment(
                            plan=plan,
                            required_amount=float(amount),
                            amount_paid=paid_val,
                            evals=evals,
                            utr=utr_input.strip(),
                        )
                        if _s == STATUS_FLAGGED:
                            st.error(_m)
                        elif _s == STATUS_PARTIAL:
                            st.warning(_m)
                            st.session_state.partial_utr    = utr_input.strip()
                            st.session_state.pending_plan   = None
                            st.session_state.pending_amount = None
                            st.session_state.pending_evals  = None
                            st.rerun()
                        else:
                            st.success(
                                "✅ Payment proof submitted! "
                                "Your quota will be unlocked after admin verification."
                            )
                            st.session_state.pending_plan   = None
                            st.session_state.pending_amount = None
                            st.session_state.pending_evals  = None
                            st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — CONTACT & FEEDBACK
# ══════════════════════════════════════════════════════════════════════════════
with tab_contact:
    st.subheader("📬 Contact, Feedback & Feature Requests")
    st.markdown(
        "Have a question, found a bug, or want to suggest a new feature? "
        "Reach out directly — every message is read personally."
    )
    st.divider()

    c1, c2 = st.columns(2)

    with c1:
        st.markdown("### 📧 Founders — Direct Contact")
        st.markdown(
            "**Aditya Srivastava**  \n"
            "Lead Developer & Founder  \n"
            "📩 [yeahboyadi@gmail.com](mailto:yeahboyadi@gmail.com)"
        )
        st.markdown(
            "**Akshat Verma**  \n"
            "Co-Founder  \n"
            "📩 [akshat.v2166@gmail.com](mailto:akshat.v2166@gmail.com)"
        )
        st.markdown("---")
        st.markdown("### 🐛 Bug Reports")
        st.markdown(
            "Please include:  \n"
            "- What you were doing  \n"
            "- What error / unexpected behaviour appeared  \n"
            "- Screenshot if possible  \n\n"
            "Send to **[yeahboyadi@gmail.com](mailto:yeahboyadi@gmail.com)** "
            "or **[akshat.v2166@gmail.com](mailto:akshat.v2166@gmail.com)** "
            "with subject line: `[BUG] Detective AI — <short description>`"
        )

    with c2:
        st.markdown("### 💡 Suggest a Feature")
        st.markdown(
            "Ideas for new capabilities are welcome:  \n"
            "- New case-matching algorithms  \n"
            "- Additional report formats  \n"
            "- Integrations (WhatsApp alerts, CRM sync, etc.)  \n\n"
            "Send to **[yeahboyadi@gmail.com](mailto:yeahboyadi@gmail.com)** "
            "or **[akshat.v2166@gmail.com](mailto:akshat.v2166@gmail.com)** "
            "with subject line: `[FEATURE REQUEST] <your idea>`"
        )
        st.markdown("---")
        st.markdown("### 🔒 Privacy & Data")
        st.markdown(
            "All suspect profiling data is processed locally in your session.  \n"
            "No case data is stored on our servers without your explicit upload.  \n"
            "Payments are verified manually — we never store card details."
        )

    st.divider()
    st.info(
        "⏱️ **Response time:** Typically within 24 hours on weekdays.  \n"
        "🌐 **Platform:** https://ibmhackathon2026-uzj9dxbwnxgkcdffvztpfa.streamlit.app/"
    )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — B2B AGENCY ACQUISITION  (ADMIN ONLY)
# ══════════════════════════════════════════════════════════════════════════════
if tab_outreach is not None:
    with tab_outreach:

        # Hard server-side guard — even if somehow rendered, block execution
        if not st.session_state.is_admin:
            st.error("🔒 Access denied. Admin authentication required.")
            st.stop()

        st.subheader("🔍 Step 1 — Scrape B2B Agency Leads")
        st.caption("Scrapes Google Maps listings for detective / investigative agencies in a target region.")

        scrape_col1, scrape_col2 = st.columns(2)
        with scrape_col1:
            search_query = st.text_input(
                "Target Search Query",
                value="Private Detective Agency",
                key="scrape_query"
            )
        with scrape_col2:
            target_region = st.text_input(
                "Target Region",
                value="Delhi NCR",
                key="scrape_region"
            )

        max_results = st.slider("Max Leads to Scrape", min_value=5, max_value=50, value=15, key="scrape_max")

        if st.button("🚀 Start Lead Scraping", type="primary", use_container_width=True, key="btn_scrape"):
            with st.spinner(f"Searching for '{search_query}' in '{target_region}'..."):
                new_leads = scrape_leads_sync(search_query, target_region, max_results)
                if new_leads and "error" in new_leads[0]:
                    st.error(f"Scraping failed: {new_leads[0]['error']}")
                else:
                    st.success(f"✅ Extracted {len(new_leads)} new leads. Saved to data/leads.json.")

        st.divider()
        st.subheader("📋 Current Lead Database")

        all_leads = load_leads()

        generated_count = sum(1 for l in all_leads if l.get("source", "") == "Generated (Verify Manually)")
        if generated_count:
            st.warning(
                f"⚠️ **{generated_count} lead(s) have auto-generated placeholder emails** "
                f"(source: *Generated (Verify Manually)*). "
                "**Edit their `contact_email` in the table below, then click 💾 Save Lead Edits before dispatching.**"
            )

        if not all_leads:
            st.info("No leads yet. Run a scrape above or manually add leads below.")
        else:
            df_leads = pd.DataFrame(all_leads)
            edited_df = st.data_editor(
                df_leads,
                use_container_width=True,
                num_rows="dynamic",
                key="leads_editor",
                column_config={
                    "agency_name":   st.column_config.TextColumn("Agency Name"),
                    "location":      st.column_config.TextColumn("Location"),
                    "contact_email": st.column_config.TextColumn("Contact Email"),
                    "website":       st.column_config.LinkColumn("Website"),
                    "source":        st.column_config.TextColumn("Source"),
                    "status":        st.column_config.SelectboxColumn(
                        "Status",
                        options=["Prospect", "Contacted", "Replied", "Converted", "Skipped"]
                    ),
                },
            )

            save_col, dl_col = st.columns(2)
            with save_col:
                if st.button("💾 Save Lead Edits", use_container_width=True, key="btn_save_leads"):
                    save_leads(edited_df.to_dict(orient="records"))
                    st.success("Lead database saved.")
            with dl_col:
                csv_bytes = edited_df.to_csv(index=False).encode()
                st.download_button(
                    "📥 Export Leads as CSV",
                    data=csv_bytes,
                    file_name="agency_leads.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key="dl_leads_csv"
                )

        if all_leads:
            st.markdown("")
            if st.button(
                "🗑️ Clear All Leads (reset lead database)",
                use_container_width=False,
                key="btn_clear_leads",
                type="secondary",
                help="Wipes data/leads.json completely. Run a fresh scrape afterwards."
            ):
                save_leads([])
                st.success("✅ Lead database cleared. Run a fresh scrape to repopulate.")
                st.rerun()

        st.divider()

        # ── Email Campaign ─────────────────────────────────────────────────────
        st.subheader("📧 Step 2 — Configure & Dispatch Cold Email Campaign")

        if not all_leads:
            st.info("Scrape leads first before configuring an email campaign.")
        else:
            st.markdown("**Select leads to include in this campaign:**")
            selected_indices: list = []
            sel_cols = st.columns(3)
            for i, lead in enumerate(all_leads):
                if sel_cols[i % 3].checkbox(
                    f"{lead.get('agency_name','?')} — {lead.get('location','?')}",
                    key=f"chk_lead_{i}"
                ):
                    selected_indices.append(i)

            selected_leads = [all_leads[i] for i in selected_indices]
            st.markdown(f"**{len(selected_leads)} lead(s) selected**")

            # ── Pre-dispatch email preview ─────────────────────────────────────
            if selected_leads:
                unverified = [l for l in selected_leads if l.get("source", "") == "Generated (Verify Manually)"]
                if unverified:
                    st.error(
                        f"🚫 **{len(unverified)} of your selected leads have placeholder emails** "
                        f"(auto-generated, not real). Sending to these will bounce.  \n"
                        "**Fix:** scroll up to the lead table → edit the `contact_email` column → click 💾 Save Lead Edits → then come back and dispatch."
                    )
                    with st.expander("📋 Show selected leads & their emails"):
                        for l in selected_leads:
                            is_fake = l.get("source", "") == "Generated (Verify Manually)"
                            badge = "⚠️ PLACEHOLDER" if is_fake else "✅ Real"
                            st.markdown(
                                f"**{l.get('agency_name','?')}** — "
                                f"`{l.get('contact_email','(none)')}` — {badge}"
                            )

            st.markdown("---")
            st.markdown("**Email Template Editor**")

            email_subject = st.text_input(
                "Email Subject Template",
                value=COLD_EMAIL_SUBJECT,
                key="email_subject_tpl"
            )
            email_body = st.text_area(
                "Email Body Template  (`{agency_name}` and `{location}` are replaced per lead)",
                value=COLD_EMAIL_BODY,
                height=280,
                key="email_body_tpl"
            )
            app_password = st.text_input(
                "Gmail App Password (16-digit)",
                type="password",
                placeholder="xxxx xxxx xxxx xxxx",
                key="gmail_app_pass",
                help="Google Account → Security → 2-Step Verification → App Passwords"
            )

            st.warning(
                "⚠️ Emails will be sent **immediately** when you click Approve & Dispatch. "
                "Make sure the lead list and template are correct before proceeding."
            )

            dispatch_btn = st.button(
                "✅ Approve & Dispatch Campaign",
                type="primary",
                use_container_width=True,
                disabled=(len(selected_leads) == 0),
                key="btn_dispatch_campaign"
            )

            if dispatch_btn:
                pw = app_password.strip().replace(" ", "")
                if not pw:
                    st.error("❌ Please enter your Gmail App Password before dispatching.")
                elif len(pw) != 16:
                    st.error(
                        f"❌ Gmail App Passwords are exactly 16 characters (you entered {len(pw)}). "
                        "Go to Google Account → Security → 2-Step Verification → App Passwords to generate one."
                    )
                else:
                    progress_bar = st.progress(0, text="Initialising...")
                    log_area     = st.empty()
                    dispatch_log: list = []

                    def update_progress(idx: int, total: int, agency: str, status: str, error: str = "") -> None:
                        pct  = int(idx / total * 100)
                        if status == "SENT":
                            icon = "✅"
                            line = f"{icon} [{idx}/{total}] {agency} — SENT"
                        elif status == "SKIPPED":
                            icon = "⏭️"
                            line = f"{icon} [{idx}/{total}] {agency} — SKIPPED (no valid email)"
                        else:
                            icon = "❌"
                            err_short = (error[:120] + "…") if len(error) > 120 else error
                            line = f"{icon} [{idx}/{total}] {agency} — FAILED: {err_short}"
                        dispatch_log.append(line)
                        progress_bar.progress(pct, text=f"Sending {idx}/{total}…")
                        log_area.code("\n".join(dispatch_log), language="text")

                    results = send_cold_emails(
                        leads=selected_leads,
                        app_password=pw,
                        subject_template=email_subject,
                        body_template=email_body,
                        delay_seconds=4,
                        progress_callback=update_progress,
                    )

                    # Check for init failure (bad password / auth error before any send)
                    if results and results[0].get("status") == "INIT_FAIL":
                        progress_bar.empty()
                        st.error(
                            f"❌ Could not connect to Gmail SMTP.\n\n"
                            f"**Error:** {results[0].get('error', 'Unknown')}\n\n"
                            "Make sure you are using a **Gmail App Password** (not your regular password). "
                            "Google Account → Security → 2-Step Verification → App Passwords."
                        )
                    else:
                        sent    = sum(1 for r in results if r["status"] == "SENT")
                        failed  = sum(1 for r in results if r["status"] == "FAILED")
                        skipped = sum(1 for r in results if r["status"] == "SKIPPED")
                        progress_bar.progress(100, text="Campaign complete!")
                        st.success(
                            f"Campaign finished — ✅ {sent} sent, ❌ {failed} failed, ⏭️ {skipped} skipped."
                        )

                        contacted_names = {r["agency_name"] for r in results if r["status"] == "SENT"}
                        updated = load_leads()
                        for lead in updated:
                            if lead.get("agency_name") in contacted_names:
                                lead["status"] = "Contacted"
                        save_leads(updated) 
