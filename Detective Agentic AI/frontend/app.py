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
    "evals_left":           25,
    "max_evals":            25,
    "current_tier":         "Pro Agency Trial",
    "latest_results":      None,
    "pending_plan":        None,
    "pending_amount":      None,
    "pending_evals":       None,
    "is_admin":            False,
    "admin_open":          False,
    "show_billing_portal": False,
    "partial_utr":          None,   # UTR of a partial payment waiting for top-up
    "leads_data":          load_leads(),
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

if st.sidebar.button("🔄 Reset Demo & Clear Cache", use_container_width=True, key="sb_reset"):
    for k, v in _ss_defaults.items():
        st.session_state[k] = v
    st.rerun()

st.sidebar.divider()

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
                    
                    _acol, _fcol = st.columns(2)
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

st.sidebar.divider()
st.sidebar.markdown(
    "**💬 Feedback & Suggestions**\n\n"
    "📧 [yeahboyadi@gmail.com](mailto:yeahboyadi@gmail.com)  \n"
    "📧 [akshat.v2166@gmail.com](mailto:akshat.v2166@gmail.com)"
)

# ══════════════════════════════════════════════════════════════════════════════
# MAIN AREA
# ══════════════════════════════════════════════════════════════════════════════
st.title("🕵️‍♂️ Detective Agentic AI & RAG Profiling System")
st.markdown("Automated criminal pattern recognition, risk evaluation, and precedent retrieval engine.")
st.divider()

_tab_labels = ["🔍 Profiling Dashboard", "💳 Billing & Plans", "📬 Contact & Feedback"]
if st.session_state.is_admin:
    _tab_labels.append("📢 B2B Agency Acquisition")

_tabs = st.tabs(_tab_labels)
tab_profile  = _tabs[0]
tab_billing  = _tabs[1]
tab_contact  = _tabs[2]
tab_outreach = _tabs[3] if st.session_state.is_admin else None

# ── TAB 1: PROFILING DASHBOARD ─────────────────────────────────────────────────
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
                        name_str = suspect_name if suspect_name else "Unnamed Suspect"
                        res = agent.evaluate_suspect(
                            name=name_str, behavior=behaviors, mo_suspected=behaviors, personality_notes="Observed via dashboard."
                        )
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
                    except Exception as err:
                        st.error(f"Analysis failed: {err}")

        if st.session_state.latest_results:
            res = st.session_state.latest_results
            m_col1, m_col2 = st.columns(2)
            m_col1.metric("Tendency Score", str(res["tendency_score"]))
            m_col2.metric("Risk Level", res["risk_level"])
            st.info(res["summary_text"])

# ── TAB 2: BILLING & PLANS ─────────────────────────────────────────────────────
with tab_billing:
    st.subheader("Select Your Subscription Plan")
    st.caption("Quota is unlocked by the admin after UPI payment is verified.")

# ── TAB 3: CONTACT & FEEDBACK ──────────────────────────────────────────────────
with tab_contact:
    st.subheader("📬 Contact, Feedback & Feature Requests")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### 📧 Founders — Direct Contact")
        st.markdown("**Aditya Srivastava**  \nLead Developer & Founder  \n📩 [yeahboyadi@gmail.com](mailto:yeahboyadi@gmail.com)")
        st.markdown("**Akshat Verma**  \nCo-Founder  \n📩 [akshat.v2166@gmail.com](mailto:akshat.v2166@gmail.com)")
    with c2:
        st.markdown("### 🔒 Privacy & Security")
        st.markdown(
            "All suspect profiling data is processed locally in your session.  \n"
            "No case data is stored on our servers without your explicit upload.  \n"
            "Payments are verified manually — we never store card or sensitive payment details directly."
        )

# ── TAB 4: B2B AGENCY ACQUISITION (ADMIN ONLY) ─────────────────────────────────
if st.session_state.is_admin and tab_outreach:
    with tab_outreach:
        st.subheader("📢 Agency Scraper & Automated Outreach Pipeline")
        st.caption("Scrape verified detective agency contacts across India and dispatch automated cold email proposals.")

        st.markdown("### 1. Indian Detective Agency Lead Database")
        leads_df = pd.DataFrame(st.session_state.leads_data)
        st.dataframe(leads_df, use_container_width=True)

        st.divider()

        st.markdown("### 2. Cold Email Campaign Preview")
        preview_agency = st.selectbox(
            "Select Lead Agency to Preview Email",
            options=[l["agency_name"] for l in st.session_state.leads_data]
        )
        selected_lead = next((l for l in st.session_state.leads_data if l["agency_name"] == preview_agency), st.session_state.leads_data[0])

        # Formatted Email Preview
        sample_email_body = COLD_EMAIL_BODY.format(agency_name=selected_lead["agency_name"])
        
        with st.expander(f"✉️ Email Preview for: {selected_lead['agency_name']} ({selected_lead['email']})", expanded=True):
            st.markdown(f"**To:** `{selected_lead['email']}`")
            st.markdown(f"**Subject:** `{COLD_EMAIL_SUBJECT}`")
            st.markdown("---")
            st.text_area("Email Content", value=sample_email_body, height=360)

        st.divider()

        st.markdown("### 3. Email Dispatcher")
        st.info(f"Loaded **{len(st.session_state.leads_data)} leads** ready for dispatch.")
        if st.button("🚀 Dispatch Cold Emails", type="primary", use_container_width=True):
            with st.spinner("Dispatching emails to agency contacts..."):
                sent = send_cold_emails(st.session_state.leads_data)
                st.success(f"✅ Dispatched outreach emails to {sent} agencies successfully!") 
