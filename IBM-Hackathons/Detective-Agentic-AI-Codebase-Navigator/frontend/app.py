import sys
import os

# Update system path FIRST so Python can locate internal modules on Streamlit Cloud
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
import json
import time
import io
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

# ── Page config (MUST be first Streamlit call) ─────────────────────────────────
st.set_page_config(
    page_title="Detective Agentic AI - Criminal Profiler",
    page_icon="🕵️‍♂️",
    layout="wide"
)

# ── Data directory ─────────────────────────────────────────────────────────────
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

# ── Session State defaults ─────────────────────────────────────────────────────
_ss_defaults = {
    "evals_left": 25,
    "max_evals": 25,
    "current_tier": "Pro Agency Trial",
    "latest_results": None,
    "show_pricing": False,
    "pending_plan": None,          # plan selected but not yet paid
    "pending_amount": None,
    "pending_evals": None,
    "admin_open": False,
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
UPI_VPA    = "adityasriv@ptyes"
UPI_NAME   = "Aditya Srivastava"

def make_upi_qr(amount: int, plan_ref: str) -> "PIL.Image.Image":
    import qrcode
    upi_uri = (
        f"upi://pay?pa={UPI_VPA}&pn={UPI_NAME.replace(' ', '%20')}"
        f"&am={amount}&cu=INR&tn={plan_ref.replace(' ', '_')}"
    )
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=8, border=4)
    qr.add_data(upi_uri)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white")

def pil_to_bytes(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
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
st.sidebar.header("⚙️ Admin Case Indexer")
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

# B2B Plan status
st.sidebar.markdown("### B2B Agency Plan")
_max  = st.session_state.max_evals
_left = st.session_state.evals_left
if _max == "Unlimited":
    quota_display = "Unlimited"
else:
    quota_display = f"{min(_left, _max)}/{_max}"

st.sidebar.info(
    f"**Current Tier:** {st.session_state.current_tier}\n\n"
    f"**Evaluations Remaining:** {quota_display}"
)
if _max != "Unlimited" and isinstance(_left, int) and _left <= 0:
    st.sidebar.error("⚠️ Trial Limit Reached")

if st.sidebar.button("💳 Upgrade / Billing Portal", use_container_width=True, key="sb_upgrade"):
    st.session_state.show_pricing = not st.session_state.show_pricing
    st.session_state.pending_plan   = None
    st.session_state.pending_amount = None
    st.session_state.pending_evals  = None
    st.rerun()

if st.sidebar.button("🔄 Reset Demo & Clear Cache", use_container_width=True, key="sb_reset"):
    for k, v in _ss_defaults.items():
        st.session_state[k] = v
    st.rerun()

st.sidebar.divider()

# Admin Payment Approvals toggle
if st.sidebar.button("🛠️ Admin Payment Approvals", use_container_width=True, key="sb_admin"):
    st.session_state.admin_open = not st.session_state.admin_open
    st.rerun()

# ── Admin Panel (inline, below sidebar buttons) ────────────────────────────────
if st.session_state.admin_open:
    st.sidebar.markdown("#### Pending Payment Submissions")
    payments = load_payments()
    pending = [p for p in payments if p.get("status") == "PENDING"]
    if not pending:
        st.sidebar.info("No pending submissions.")
    else:
        for i, pmt in enumerate(pending):
            with st.sidebar.expander(f"#{i+1} {pmt.get('plan')} — UTR: {pmt.get('utr')}"):
                st.write(f"**Plan:** {pmt.get('plan')}")
                st.write(f"**Amount:** ₹{pmt.get('amount')}")
                st.write(f"**Evals:** {pmt.get('evals')}")
                st.write(f"**UTR:** {pmt.get('utr')}")
                st.write(f"**Submitted:** {pmt.get('timestamp','')}")
                if st.button("✅ Approve & Unlock Quota", key=f"approve_{i}_{pmt.get('utr')}"):
                    # Release quota
                    evals = pmt.get("evals")
                    if evals == "Unlimited":
                        st.session_state.evals_left = "Unlimited"
                        st.session_state.max_evals  = "Unlimited"
                    else:
                        st.session_state.evals_left = int(evals)
                        st.session_state.max_evals  = int(evals)
                    st.session_state.current_tier = pmt.get("plan", "")
                    # Mark approved
                    for p in payments:
                        if p.get("utr") == pmt.get("utr"):
                            p["status"] = "APPROVED"
                    save_payments(payments)
                    st.sidebar.success(f"Quota unlocked for UTR {pmt.get('utr')}!")
                    st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# MAIN TABS
# ══════════════════════════════════════════════════════════════════════════════
st.title("🕵️‍♂️ Detective Agentic AI & RAG Profiling System")
st.markdown("Automated criminal pattern recognition, risk evaluation, and precedent retrieval engine.")
st.divider()

tab_profile, tab_billing, tab_outreach = st.tabs([
    "🔍 Profiling Dashboard",
    "💳 Billing & Plans",
    "📢 B2B Agency Acquisition",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — PROFILING DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
with tab_profile:
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Suspect Information & Observations")
        with st.form(key="suspect_profiling_form"):
            suspect_name = st.text_input("Suspect Name / Alias", placeholder="John Doe")
            age = st.text_input("Age", placeholder="34")
            behaviors = st.text_area(
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
                        try:
                            res = agent.evaluate_suspect(
                                name=name_str,
                                behavior=behaviors,
                                mo_suspected=behaviors,
                                personality_notes="Observed via profiling dashboard."
                            )
                        except Exception:
                            load_agent.clear()
                            fresh_agent = load_agent()
                            res = fresh_agent.evaluate_suspect(
                                name=name_str,
                                behavior=behaviors,
                                mo_suspected=behaviors,
                                personality_notes="Observed via profiling dashboard."
                            )

                        if st.session_state.max_evals != "Unlimited":
                            st.session_state.evals_left = max(0, st.session_state.evals_left - 1)

                        st.session_state.latest_results = {
                            "name": name_str,
                            "age": age,
                            "behaviors": behaviors,
                            "tendency_score": res.get("tendency_score", "0%"),
                            "risk_level": res.get("risk_level", "UNKNOWN"),
                            "matched_cases": res.get("similar_cases", []),
                            "summary_text": res.get("summary", ""),
                            "timestamp": time.time()
                        }
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
        "🥉 Starter Agency":  {"amount": 7999,  "evals": 100,         "label": "₹7,999 / mo — 100 Evaluations"},
        "🥈 Pro Agency":       {"amount": 24999, "evals": 500,         "label": "₹24,999 / mo — 500 Evaluations"},
        "🥇 Enterprise SaaS":  {"amount": 64999, "evals": "Unlimited", "label": "₹64,999 / mo — Unlimited Evaluations"},
    }

    st.subheader("Select Your Subscription Plan")
    st.caption("Quota is unlocked by an admin after UPI payment is verified.")

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

            btn_key = f"plan_select_{plan_name.replace(' ','_').replace('/', '_')}"
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
                qr_img     = make_upi_qr(amount, f"Detective_AI_{plan.split()[1]}")
                qr_bytes   = pil_to_bytes(qr_img)
                st.image(qr_bytes, caption=f"Scan to Pay ₹{amount:,}", width=220)
            except Exception as e:
                st.warning(f"QR generation requires `qrcode[pil]` and `Pillow`. Error: {e}")
                st.code(
                    f"upi://pay?pa={UPI_VPA}&pn=Aditya%20Srivastava"
                    f"&am={amount}&cu=INR&tn=Detective_AI_{plan.split()[1]}",
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

            with st.form(key=f"utr_form_{plan.replace(' ','_')}"):
                utr_input = st.text_input(
                    "Enter UTR / Transaction Reference ID (12 digits)",
                    placeholder="e.g. 426789012345",
                    max_chars=30
                )
                submit_utr = st.form_submit_button("📨 Submit Payment Proof", use_container_width=True)

            if submit_utr:
                if not utr_input.strip():
                    st.error("Please enter your UTR / Transaction Reference.")
                else:
                    payments = load_payments()
                    # Prevent duplicate UTR submissions
                    existing_utrs = {p.get("utr") for p in payments}
                    if utr_input.strip() in existing_utrs:
                        st.warning("This UTR has already been submitted.")
                    else:
                        payments.append({
                            "plan":      plan,
                            "amount":    amount,
                            "evals":     evals,
                            "utr":       utr_input.strip(),
                            "status":    "PENDING",
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        })
                        save_payments(payments)
                        st.success(
                            "✅ Payment proof submitted! Your quota will be unlocked after admin verification. "
                            "You'll see the updated plan in the sidebar."
                        )
                        st.session_state.pending_plan   = None
                        st.session_state.pending_amount = None
                        st.session_state.pending_evals  = None
                        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — B2B AGENCY ACQUISITION
# ══════════════════════════════════════════════════════════════════════════════
with tab_outreach:
    import pandas as pd

    st.subheader("🔍 Step 1 — Scrape B2B Agency Leads")

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
        with st.spinner(f"Scraping Google Maps for '{search_query}' in '{target_region}'..."):
            new_leads = scrape_leads_sync(search_query, target_region, max_results)
            if new_leads and "error" in new_leads[0]:
                st.error(f"Scraping failed: {new_leads[0]['error']}")
            else:
                st.success(f"✅ Extracted {len(new_leads)} new leads. Saved to data/leads.json.")

    st.divider()
    st.subheader("📋 Current Lead Database")

    all_leads = load_leads()

    if not all_leads:
        st.info("No leads yet. Run a scrape above or leads will appear here once scraped.")
    else:
        df_leads = pd.DataFrame(all_leads)

        # Editable dataframe with selection
        edited_df = st.data_editor(
            df_leads,
            use_container_width=True,
            num_rows="dynamic",
            key="leads_editor",
            column_config={
                "agency_name":    st.column_config.TextColumn("Agency Name"),
                "location":       st.column_config.TextColumn("Location"),
                "contact_email":  st.column_config.TextColumn("Contact Email"),
                "website":        st.column_config.LinkColumn("Website"),
                "source":         st.column_config.TextColumn("Source"),
                "status":         st.column_config.SelectboxColumn(
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

    st.divider()

    # ── Email Campaign ─────────────────────────────────────────────────────────
    st.subheader("📧 Step 2 — Configure & Dispatch Cold Email Campaign")

    if not all_leads:
        st.info("Scrape leads first before configuring an email campaign.")
    else:
        df_for_email = pd.DataFrame(all_leads)

        st.markdown("**Select leads to include in this campaign:**")
        selected_indices = []
        sel_cols = st.columns(3)
        for i, lead in enumerate(all_leads):
            col = sel_cols[i % 3]
            if col.checkbox(
                f"{lead.get('agency_name','?')} — {lead.get('location','?')}",
                key=f"chk_lead_{i}"
            ):
                selected_indices.append(i)

        selected_leads = [all_leads[i] for i in selected_indices]

        st.markdown(f"**{len(selected_leads)} lead(s) selected**")

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
            key=f"btn_dispatch_{int(time.time()*1000) % 100000}"
        )

        if dispatch_btn:
            if not app_password.strip():
                st.error("Please enter your Gmail App Password to send emails.")
            elif len(selected_leads) == 0:
                st.warning("No leads selected.")
            else:
                progress_bar = st.progress(0, text="Initialising...")
                log_area = st.empty()
                dispatch_log = []

                def update_progress(idx, total, agency, status):
                    pct = int(idx / total * 100)
                    icon = "✅" if status == "SENT" else "❌"
                    dispatch_log.append(f"{icon} [{idx}/{total}] {agency} — {status}")
                    progress_bar.progress(pct, text=f"Sending {idx}/{total}...")
                    log_area.code("\n".join(dispatch_log), language="text")

                results = send_cold_emails(
                    leads=selected_leads,
                    app_password=app_password.strip(),
                    subject_template=email_subject,
                    body_template=email_body,
                    delay_seconds=4,
                    progress_callback=update_progress,
                )

                sent   = sum(1 for r in results if r["status"] == "SENT")
                failed = sum(1 for r in results if r["status"] == "FAILED")
                progress_bar.progress(100, text="Campaign complete!")
                st.success(f"Campaign finished — ✅ {sent} sent, ❌ {failed} failed.")

                # Mark contacted leads in DB
                contacted_names = {
                    r["agency_name"] for r in results if r["status"] == "SENT"
                }
                updated = load_leads()
                for lead in updated:
                    if lead.get("agency_name") in contacted_names:
                        lead["status"] = "Contacted"
                save_leads(updated)
