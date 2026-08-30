import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
import json
import time
import re
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

st.set_page_config(
    page_title="Detective Agentic AI - Criminal Profiler",
    page_icon="🕵️‍♂️",
    layout="wide"
)

PLATFORM_URL = "https://ibmhackathon2026-uzj9dxbwnxgkcdffvztpfa.streamlit.app/"

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
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

ADMIN_PASSWORD = "Adi"

def _get_admin_password() -> str:
    try:
        return str(st.secrets["ADMIN_PASSWORD"])
    except Exception:
        return ADMIN_PASSWORD

def _get_gmail_app_password() -> str:
    """Read the Gmail App Password from Streamlit secrets."""
    for key in ("GMAIL_APP_PASSWORD", "EMAIL_APP_PASSWORD", "GMAIL_PASSWORD"):
        try:
            value = st.secrets[key]
            if value:
                return str(value).strip()
        except Exception:
            pass
    return ""

_ss_defaults = {
    "evals_left": 25,
    "max_evals": 25,
    "current_tier": "Pro Agency Trial",
    "latest_results": None,
    "pending_plan": None,
    "pending_amount": None,
    "pending_evals": None,
    "is_admin": False,
    "admin_open": False,
    "show_billing_portal": False,
    "partial_utr": None,
    "analysis_history": [],
}
for k, v in _ss_defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

@st.cache_resource
def load_agent():
    return DetectiveAgent()

agent = load_agent()

UPI_VPA = "adityasriv@ptyes"
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

# Sidebar
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
_max = st.session_state.max_evals
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
        st.session_state.pending_plan = None
        st.session_state.pending_amount = None
        st.session_state.pending_evals = None
    st.rerun()

if st.session_state.show_billing_portal:
    PLANS_SIDEBAR = {
        "🥉 Starter": {"amount": 500, "evals": 100, "label": "₹500/mo — 100 Evals"},
        "🥈 Pro": {"amount": 1000, "evals": 500, "label": "₹1,000/mo — 500 Evals"},
        "🥇 Enterprise": {"amount": 2000, "evals": "Unlimited", "label": "₹2,000/mo — Unlimited"},
    }
    st.sidebar.markdown("#### 📋 Choose a Plan")
    for pname, pinfo in PLANS_SIDEBAR.items():
        sb_key = f"sb_plan_{pname.replace(' ','_').replace('/','_')}"
        if st.sidebar.button(f"{pname} — {pinfo['label']}", key=sb_key, use_container_width=True):
            st.session_state.pending_plan = pname
            st.session_state.pending_amount = pinfo["amount"]
            st.session_state.pending_evals = pinfo["evals"]
            st.rerun()

    if st.session_state.pending_plan:
        _plan = st.session_state.pending_plan
        _amount = st.session_state.pending_amount
        _evals = st.session_state.pending_evals
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
            _utr = st.text_input("UTR / Transaction Ref No.", placeholder="e.g. 426789012345", max_chars=30)
            _paid_str = st.text_input("Amount You Paid (₹)", placeholder=f"e.g. {_amount}", max_chars=10)
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
                        plan=_plan, required_amount=float(_amount),
                        amount_paid=_paid_val, evals=_evals, utr=_utr.strip()
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
                        st.session_state.pending_plan = None
                        st.session_state.pending_amount = None
                        st.session_state.pending_evals = None
                        st.session_state.show_billing_portal = False
                        st.rerun()

if st.sidebar.button("🔄 Reset Demo & Clear Cache", use_container_width=True, key="sb_reset"):
    for k, v in _ss_defaults.items():
        st.session_state[k] = v
    st.rerun()

st.sidebar.divider()
with st.sidebar.expander("🔐 Admin Portal", expanded=False):
    if st.session_state.is_admin:
        st.success("✅ Logged in as Admin")
        if st.button("🔓 Logout Admin", use_container_width=True, key="btn_admin_logout"):
            st.session_state.is_admin = False
            st.session_state.admin_open = False
            st.rerun()
    else:
        admin_pw = st.text_input("Admin Password", type="password", placeholder="Enter admin password…", key="admin_pw_input")
        if st.button("🔑 Login", use_container_width=True, key="btn_admin_login"):
            if admin_pw == _get_admin_password():
                st.session_state.is_admin = True
                st.rerun()
            else:
                st.error("❌ Incorrect password.")

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
                _putr = pmt.get("utr", "")
                _preq = pmt.get("required_amount", pmt.get("amount", 0))
                _ppaid = pmt.get("amount_paid", pmt.get("amount", 0))
                _premain = pmt.get("remaining_balance", 0)
                _pstatus = pmt.get("status", "")
                _pevals = pmt.get("evals", "?")
                _pplan = pmt.get("plan", "?")
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
                    if _acol.button("✅ Approve", key=f"pay_verify_{_putr}_approve"):
                        if approve_payment(_putr):
                            evals = _pevals
                            if evals == "Unlimited":
                                st.session_state.evals_left = "Unlimited"
                                st.session_state.max_evals = "Unlimited"
                            else:
                                try:
                                    st.session_state.evals_left = int(evals)
                                    st.session_state.max_evals = int(evals)
                                except Exception:
                                    pass
                            st.session_state.current_tier = _pplan
                            st.sidebar.success(f"✅ Quota unlocked — {_putr}")
                            st.rerun()
                    if _fcol.button("⚠️ Flag Partial", key=f"pay_verify_{_putr}_flag"):
                        if flag_partial(_putr):
                            st.session_state.partial_utr = _putr
                            st.sidebar.warning("Flagged as partial — user will be prompted for top-up.")
                            st.rerun()

st.sidebar.divider()
st.sidebar.markdown(
    "**💬 Feedback & Suggestions**\n\n"
    "Found a bug? Want a new feature?\n\n"
    "📧 [yeahboyadi@gmail.com](mailto:yeahboyadi@gmail.com)  \n"
    "📧 [akshat.v2166@gmail.com](mailto:akshat.v2166@gmail.com)"
)

st.title("🕵️‍♂️ Detective Agentic AI & RAG Profiling System")
st.markdown("Automated criminal pattern recognition, risk evaluation, and precedent retrieval engine.")
st.divider()

if st.session_state.partial_utr:
    _prec = get_partial_by_utr(st.session_state.partial_utr)
    if _prec:
        _p_paid = _prec.get("amount_paid", 0)
        _p_req = _prec.get("required_amount", 0)
        _p_remain = _prec.get("remaining_balance", 0)
        _p_plan = _prec.get("plan", "")
        _p_utr = _prec.get("utr", "")
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
                _topup_utr = st.text_input("Enter Top-Up UTR / Transaction Ref", placeholder="New 12-digit UTR after paying balance", max_chars=30)
                _topup_sub = st.form_submit_button("📨 Submit Top-Up Proof", use_container_width=True, type="primary")
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
        st.session_state.partial_utr = None

_tab_labels = ["🔍 Profiling Dashboard", "💳 Billing & Plans", "📬 Contact & Feedback"]
if st.session_state.is_admin:
    _tab_labels.append("📢 B2B Agency Acquisition")
_tabs = st.tabs(_tab_labels)
tab_profile = _tabs[0]
tab_billing = _tabs[1]
tab_contact = _tabs[2]
tab_outreach = _tabs[3] if st.session_state.is_admin else None

with tab_profile:
    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("Suspect Information & Observations")
        with st.form(key="suspect_profiling_form"):
            suspect_name = st.text_input("Suspect Name / Alias", placeholder="John Doe")
            age = st.text_input("Age", placeholder="34")
            behaviors = st.text_area("Observed Behaviors, MO, & Traits", height=180,
                                     placeholder="Entering residential premises during late hours, targeting locked cabinets...")
            submit_btn = st.form_submit_button("Run Intelligence Analysis", type="primary", use_container_width=True)
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
                        name_str = suspect_name.strip() if suspect_name.strip() else "Unnamed Suspect"
                        res = agent.evaluate_suspect(
                            name=name_str, behavior=behaviors,
                            mo_suspected=behaviors, personality_notes=behaviors
                        )
                        if st.session_state.max_evals != "Unlimited":
                            st.session_state.evals_left = max(0, st.session_state.evals_left - 1)
                        matched_cases = res.get("similar_cases", [])
                        risk_lbl = res.get("risk_level", "UNKNOWN")
                        st.session_state.latest_results = {
                            "name": res.get("suspect_name", name_str),
                            "age": age, "behaviors": behaviors,
                            "tendency_score": res.get("tendency_score", "0%"),
                            "risk_level": risk_lbl,
                            "matched_cases": matched_cases,
                            "summary_text": res.get("summary", f"Suspect pattern evaluated for behavior traits: {behaviors[:60]}..."),
                            "timestamp": time.time()
                        }
                        st.session_state.analysis_history.append(st.session_state.latest_results.copy())
                    except Exception as err:
                        st.error(f"Analysis failed: {err}")

        if st.session_state.latest_results:
            res = st.session_state.latest_results
            st.markdown(f"### Profile: **{res['name']}**")
            m_col1, m_col2 = st.columns(2)
            m_col1.metric("Tendency Score", str(res["tendency_score"]))
            m_col2.metric("Risk Level", res["risk_level"])
            st.info(res["summary_text"])
            st.markdown("#### Matched Precedents")
            if res["matched_cases"]:
                for case in res["matched_cases"]:
                    with st.expander(f"📌 {case.get('case_title','Historical Precedent')} ({case.get('location','Global')})"):
                        st.write(f"**Case ID:** {case.get('case_id','N/A')}")
                        st.write(f"**Details:** {case.get('summary', case.get('snippet','No snippet available.'))}")
            else:
                st.info("No direct precedent matches found in ChromaDB above threshold.")
            try:
                pdf_bytes = generate_pdf_report(
                    res["name"], res["age"], res["tendency_score"],
                    res["risk_level"], res["behaviors"], res["matched_cases"]
                )
                dynamic_key = f"dl_pdf_{int(res.get('timestamp', time.time()))}"
                st.download_button(
                    label="📥 Download Executive PDF Report", data=pdf_bytes,
                    file_name=f"Profile_Report_{res['name'].replace(' ', '_')}.pdf",
                    mime="application/pdf", use_container_width=True, key=dynamic_key
                )
            except Exception:
                st.caption("PDF generation ready.")

with tab_billing:
    PLANS = {
        "🥉 Starter Agency": {"amount": 500, "evals": 100, "label": "₹500 / mo — 100 Evaluations"},
        "🥈 Pro Agency": {"amount": 1000, "evals": 500, "label": "₹1,000 / mo — 500 Evaluations"},
        "🥇 Enterprise SaaS": {"amount": 2000, "evals": "Unlimited", "label": "₹2,000 / mo — Unlimited Evaluations"},
    }
    st.subheader("Select Your Subscription Plan")
    st.caption("Quota is unlocked by the admin after UPI payment is verified.")
    p_col1, p_col2, p_col3 = st.columns(3)
    for col, (plan_name, plan_info) in zip([p_col1, p_col2, p_col3], PLANS.items()):
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
                st.session_state.pending_plan = plan_name
                st.session_state.pending_amount = plan_info["amount"]
                st.session_state.pending_evals = plan_info["evals"]
                st.rerun()

    if st.session_state.pending_plan:
        st.divider()
        plan = st.session_state.pending_plan
        amount = st.session_state.pending_amount
        evals = st.session_state.pending_evals
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
                utr_input = st.text_input("Enter UTR / Transaction Reference ID", placeholder="e.g. 426789012345", max_chars=30)
                paid_input = st.text_input("Amount You Paid (₹)", placeholder=f"e.g. {amount}", max_chars=10)
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
                            plan=plan, required_amount=float(amount),
                            amount_paid=paid_val, evals=evals, utr=utr_input.strip()
                        )
                        if _s == STATUS_FLAGGED:
                            st.error(_m)
                        elif _s == STATUS_PARTIAL:
                            st.warning(_m)
                            st.session_state.partial_utr = utr_input.strip()
                            st.session_state.pending_plan = None
                            st.session_state.pending_amount = None
                            st.session_state.pending_evals = None
                            st.rerun()
                        else:
                            st.success("✅ Payment proof submitted! Your quota will be unlocked after admin verification.")
                            st.session_state.pending_plan = None
                            st.session_state.pending_amount = None
                            st.session_state.pending_evals = None
                            st.rerun()

with tab_contact:
    st.subheader("📬 Contact, Feedback & Feature Requests")
    st.markdown("Have a question, found a bug, or want to suggest a new feature? Reach out directly — every message is read personally.")
    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### 📧 Founders — Direct Contact")
        st.markdown("**Aditya Srivastava** \nLead Developer & Founder  \n📩 [yeahboyadi@gmail.com](mailto:yeahboyadi@gmail.com)")
        st.markdown("**Akshat Verma** \nCo-Founder  \n📩 [akshat.v2166@gmail.com](mailto:akshat.v2166@gmail.com)")
        st.markdown("---")
        st.markdown("### 🐛 Bug Reports")
        st.markdown("Please include:  \n- What you were doing  \n- What error / unexpected behaviour appeared  \n- Screenshot if possible  \n\nSend to **[yeahboyadi@gmail.com](mailto:yeahboyadi@gmail.com)** or **[akshat.v2166@gmail.com](mailto:akshat.v2166@gmail.com)** with subject line: `[BUG] Detective AI — <short description>`")
    with c2:
        st.markdown("### 💡 Suggest a Feature")
        st.markdown("Ideas for new capabilities are welcome:  \n- New case-matching algorithms  \n- Additional report formats  \n- Integrations (WhatsApp alerts, CRM sync, etc.)  \n\nSend to **[yeahboyadi@gmail.com](mailto:yeahboyadi@gmail.com)** or **[akshat.v2166@gmail.com](mailto:akshat.v2166@gmail.com)** with subject line: `[FEATURE REQUEST] <your idea>`")
        st.markdown("---")
        st.markdown("### 🔒 Privacy & Data")
        st.markdown("All suspect profiling data is processed locally in your session.  \nNo case data is stored on our servers without your explicit upload.  \nPayments are verified manually — we never store card details.")
    st.divider()
    st.info(
        "⏱️ **Response time:** Typically within 24 hours on weekdays.  \n"
        f"🌐 **Platform:** {PLATFORM_URL}"
    )

if st.session_state.is_admin:
    with tab_outreach:
        st.subheader("📢 B2B Lead Scraper & Cold Email Outreach")
        st.caption("Scrape target agency/detective contact information, select specific prospects, preview emails, and dispatch only after approval.")

        col_kw, col_loc = st.columns(2)
        with col_kw:
            target_keyword = st.text_input("Target Keyword / Niche", value="Detective Agency", key="outreach_kw")
        with col_loc:
            target_location = st.text_input("Location", value="Delhi", key="outreach_loc")

        if st.button("🔎 Scrape Leads", type="primary", use_container_width=True, key="btn_scrape_leads"):
            with st.spinner("Scraping leads across web sources..."):
                try:
                    scraped_data = scrape_leads_sync(target_keyword, target_location)
                    if scraped_data:
                        st.success(f"Successfully scraped {len(scraped_data)} leads!")
                        st.dataframe(pd.DataFrame(scraped_data), use_container_width=True)
                    else:
                        st.info("No leads found matching your criteria.")
                except Exception as e:
                    st.error(f"Scraping failed: {e}")

        st.divider()
        st.markdown("### 📧 Email Dispatcher")
        saved_leads = load_leads()

        if saved_leads:
            email_ready_count = sum(
                1 for lead in saved_leads
                if isinstance(lead, dict) and re.fullmatch(
                    r"[^\s@]+@[^\s@]+\.[^\s@]+",
                    str(
                        lead.get("contact_email")
                        or lead.get("email")
                        or lead.get("email_address")
                        or ""
                    ).strip(),
                )
            )
            st.write(
                f"Loaded **{len(saved_leads)}** prospects — "
                f"**{email_ready_count}** have a valid email address."
            )
            if email_ready_count == 0:
                st.warning(
                    "No verified email addresses are available yet. "
                    "Prospects without a published email are kept for manual "
                    "enrichment and will not be emailed."
                )

            def _lead_label(lead, index):
                if not isinstance(lead, dict):
                    return f"Prospect {index + 1}"
                name = (
                    lead.get("agency_name") or lead.get("company_name") or
                    lead.get("company") or lead.get("business_name") or
                    lead.get("name") or lead.get("title") or f"Prospect {index + 1}"
                )
                email = lead.get("email") or lead.get("email_address") or lead.get("contact_email") or ""
                name, email = str(name).strip(), str(email).strip()
                return f"{name} — {email}" if email else name

            lead_labels = [_lead_label(lead, index) for index, lead in enumerate(saved_leads)]

            st.markdown("#### 🎯 Choose Recipients")
            st.caption("Use a command such as `send to Delhi Inquiry Bureau`, `send to ABC and XYZ`, or `send to all`.")

            selection_command = st.text_input(
                "Recipient Selection Command",
                placeholder="e.g. send to Delhi Inquiry Bureau and ABC Agency",
                key="outreach_selection_command"
            )

            command_matches, command_not_found = [], []
            if selection_command.strip():
                command_lower = selection_command.lower().strip()
                if command_lower in {"all", "send all", "send to all", "email all", "email everyone", "send to everyone"}:
                    command_matches = list(lead_labels)
                else:
                    cleaned = re.sub(r"^(please\s+)?(send|email|mail)(\s+to)?\s*", "", command_lower, flags=re.I)
                    cleaned = re.sub(r"^(agencies|leads|recipients)\s*[:=-]?\s*", "", cleaned, flags=re.I)
                    requested_names = [p.strip() for p in re.split(r"\s*,\s*|\s+and\s+", cleaned) if p.strip()]
                    normalized_labels = [re.sub(r"[^a-z0-9@.]+", " ", label.lower()).strip() for label in lead_labels]
                    for requested in requested_names:
                        req = re.sub(r"[^a-z0-9@.]+", " ", requested.lower()).strip()
                        found = False
                        for label, norm in zip(lead_labels, normalized_labels):
                            if req in norm or norm in req:
                                if label not in command_matches:
                                    command_matches.append(label)
                                found = True
                        if not found:
                            command_not_found.append(requested)

            if command_matches:
                st.success(f"Command matched **{len(command_matches)}** recipient(s).")
            if command_not_found:
                st.warning("No matching recipient found for: " + ", ".join(command_not_found))

            if selection_command.strip():
                last_command = st.session_state.get("_outreach_last_selection_command")
                if last_command != selection_command:
                    st.session_state["outreach_selected_labels"] = list(command_matches)
                    st.session_state["_outreach_last_selection_command"] = selection_command

            selected_labels = st.multiselect(
                "Select recipients to email",
                options=lead_labels,
                key="outreach_selected_labels"
            )
            selected_indices = [i for i, label in enumerate(lead_labels) if label in selected_labels]
            selected_leads = [saved_leads[i] for i in selected_indices]
            st.info(f"Selected **{len(selected_leads)}** of **{len(saved_leads)}** prospects.")

            st.markdown("#### 🔐 Gmail Authentication")
            st.caption(
                "Enter the Gmail App Password for the sending account. "
                "It is used only for this session and is not saved to your project files."
            )
            gmail_session_password = st.text_input(
                "Gmail App Password",
                type="password",
                placeholder="Enter your 16-character Google App Password",
                key="b2b_gmail_session_password",
            )

            st.markdown("#### 👁️ Email Preview")

            def _render_email(template, lead):
                if not isinstance(lead, dict):
                    return str(template)
                recipient_name = (
                    lead.get("agency_name") or lead.get("company_name") or
                    lead.get("company") or lead.get("business_name") or
                    lead.get("name") or "Agency"
                )
                recipient_email = lead.get("email") or lead.get("email_address") or lead.get("contact_email") or ""
                rendered = str(template)
                replacements = {
                    "{agency_name}": str(recipient_name),
                    "{company_name}": str(recipient_name),
                    "{company}": str(recipient_name),
                    "{business_name}": str(recipient_name),
                    "{recipient}": str(recipient_name),
                    "{name}": str(recipient_name),
                    "{email}": str(recipient_email),
                    "{location}": str(lead.get("location", "")),
                }
                for placeholder, value in replacements.items():
                    rendered = rendered.replace(placeholder, value)

                # Only preview-link fix: ensure the live platform URL is used.
                rendered = rendered.replace(
                    "https://detective-ai.streamlit.app",
                    PLATFORM_URL.rstrip("/")
                )
                return rendered

            if selected_leads:
                preview_options = [_lead_label(lead, i) for i, lead in enumerate(selected_leads)]
                preview_label = st.selectbox("Preview email for", options=preview_options, key="outreach_preview_agency_label")
                preview_index = preview_options.index(preview_label)
                preview_lead = selected_leads[preview_index]
                preview_email = preview_lead.get("email") or preview_lead.get("email_address") or preview_lead.get("contact_email") or ""
                st.text_input("To", value=str(preview_email), disabled=True, key="outreach_preview_to")
                st.text_input("Agency / Recipient", value=preview_label, disabled=True, key="outreach_preview_agency")
                st.text_input("Subject", value=_render_email(COLD_EMAIL_SUBJECT, preview_lead), disabled=True, key="outreach_preview_subject")
                st.text_area("Email Body", value=_render_email(COLD_EMAIL_BODY, preview_lead), height=300, disabled=True, key="outreach_preview_body")
                st.caption("Nothing is sent until you click the dispatch button below.")

            st.divider()
            if selected_leads:
                if st.button(f"🚀 Dispatch Cold Emails to {len(selected_leads)} Selected Recipients", use_container_width=True, key="btn_dispatch_selected_emails"):
                    app_password = str(gmail_session_password or "").strip()
                    if not app_password:
                        st.error("Enter the Gmail App Password above, then try again.")
                    else:
                        progress_box = st.empty()
                        with st.spinner(f"Sending emails to {len(selected_leads)} selected recipients..."):
                            try:
                                dispatch_result = send_cold_emails(
                                    selected_leads,
                                    app_password,
                                    COLD_EMAIL_SUBJECT,
                                    COLD_EMAIL_BODY,
                                    delay_seconds=5,
                                    progress_callback=lambda i, total, agency, status, error="": progress_box.info(
                                        f"Sending {i}/{total}: {agency} — {status}"
                                        + (f" — {error}" if error else "")
                                    ),
                                )
                                successful = [x for x in dispatch_result if str(x.get("status", "")).upper() in {"SENT", "SUCCESS", "SUCCESSFUL"}]
                                failed = [x for x in dispatch_result if str(x.get("status", "")).upper() not in {"SENT", "SUCCESS", "SUCCESSFUL"}]
                                if successful:
                                    st.success(f"Successfully sent **{len(successful)}** email(s).")
                                if failed:
                                    st.warning(f"**{len(failed)}** email(s) were not sent.")
                                    for item in failed:
                                        st.error(f"{item.get('agency_name', item.get('recipient', 'Unknown'))}: {item.get('error', 'Unknown error')}")
                                if not successful and not failed:
                                    st.info("No emails were dispatched.")

                                # Persist dispatch results so the admin can see
                                # which prospects have already been contacted.
                                result_by_email = {
                                    str(item.get("recipient", "")).strip().lower(): item
                                    for item in dispatch_result
                                    if item.get("recipient")
                                }
                                changed = False
                                for lead in saved_leads:
                                    if not isinstance(lead, dict):
                                        continue
                                    lead_email = str(
                                        lead.get("contact_email")
                                        or lead.get("email")
                                        or lead.get("email_address")
                                        or ""
                                    ).strip().lower()
                                    item = result_by_email.get(lead_email)
                                    if not item:
                                        continue

                                    new_status = str(item.get("status", "Prospect"))
                                    if lead.get("status") != new_status:
                                        lead["status"] = new_status
                                        changed = True

                                    if new_status == "SENT":
                                        lead["last_contacted_at"] = time.strftime(
                                            "%Y-%m-%d %H:%M:%S"
                                        )
                                        changed = True

                                if changed:
                                    save_leads(saved_leads)

                            except Exception as e:
                                st.error(f"Email dispatch failed: {e}")
            else:
                st.button("🚀 Dispatch Cold Emails", use_container_width=True, key="btn_dispatch_disabled", disabled=True)
        else:
            st.info("No saved leads available to email. Perform a lead scrape first.") 
