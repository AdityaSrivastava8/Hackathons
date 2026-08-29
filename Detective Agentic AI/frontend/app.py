import streamlit as st
import json
import os
import io
import time
from datetime import datetime

# Optional external imports with fallback handling
try:
    import segno
    HAS_SEGNO = True
except ImportError:
    HAS_SEGNO = False

try:
    from PIL import Image
    import qrcode
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False

# -----------------------------------------------------------------------------
# APP CONFIGURATION & STATE INITIALIZATION
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Detective Agentic AI & RAG Profiling System",
    page_icon="🕵️‍♂️",
    layout="wide"
)

# Initialize Session States
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False
if "payments" not in st.session_state:
    st.session_state.payments = []
if "user_plan" not in st.session_state:
    st.session_state.user_plan = "Free Tier"
if "indexed_cases" not in st.session_state:
    st.session_state.indexed_cases = []

# -----------------------------------------------------------------------------
# HELPER FUNCTIONS
# -----------------------------------------------------------------------------
def generate_upi_qr(upi_id, name, amount):
    """Generates a UPI payment QR code buffer."""
    upi_url = f"upi://pay?pa={upi_id}&pn={name}&am={amount}&cu=INR"
    buf = io.BytesIO()
    
    if HAS_SEGNO:
        qrcode_obj = segno.make(upi_url)
        qrcode_obj.save(buf, kind='png', scale=5)
        buf.seek(0)
        return buf
    elif HAS_QRCODE:
        img = qrcode.make(upi_url)
        img.save(buf, format='PNG')
        buf.seek(0)
        return buf
    else:
        return None

# -----------------------------------------------------------------------------
# SIDEBAR NAVIGATION & INDEXER
# -----------------------------------------------------------------------------
with st.sidebar:
    st.title("🕵️ Control Panel")
    st.write(f"**Current Plan:** {st.session_state.user_plan}")
    
    st.markdown("---")
    st.subheader("📁 Vector Case Indexer")
    uploaded_file = st.file_uploader("Upload Case File (JSON)", type=["json"])
    if uploaded_file is not None:
        try:
            case_data = json.load(uploaded_file)
            st.session_state.indexed_cases.append(case_data)
            st.success(f"Indexed case: {case_data.get('case_id', 'Unknown ID')}")
        except Exception as e:
            st.error(f"Error parsing JSON: {e}")

    st.markdown("---")
    # Admin Authentication
    st.subheader("🔐 Admin Access")
    if not st.session_state.is_admin:
        admin_pass = st.text_input("Admin Key", type="password")
        if st.button("Login as Admin"):
            if admin_pass == "admin123":  # Change to your secure key or secret
                st.session_state.is_admin = True
                st.success("Admin authenticated!")
                st.rerun()
            else:
                st.error("Invalid credentials")
    else:
        st.success("Logged in as Admin")
        if st.button("Logout"):
            st.session_state.is_admin = False
            st.rerun()

# -----------------------------------------------------------------------------
# MAIN APPLICATION INTERFACE
# -----------------------------------------------------------------------------
st.title("🔎 Detective Agentic AI & RAG Profiling System")

# Tab Navigation
tabs = ["Profiling & Analysis", "Pricing & Upgrade", "Contact & Security"]
if st.session_state.is_admin:
    tabs.extend(["Admin Dashboard", "Outreach & Leads"])

selected_tabs = st.tabs(tabs)

# --- TAB 1: Profiling & Analysis ---
with selected_tabs[0]:
    st.header("Suspect Profiling & Behavioral RAG Analysis")
    col1, col2 = st.columns([2, 1])
    
    with col1:
        suspect_name = st.text_input("Suspect Name / Identifier")
        observations = st.text_area("Observed Behaviors / Evidence Logs", height=150)
        risk_level = st.select_slider("Assessed Risk Level", options=["Low", "Medium", "High", "Critical"])
        
        if st.button("Run RAG Profiling Engine"):
            if suspect_name and observations:
                with st.spinner("Querying vector database and synthesizing profile..."):
                    time.sleep(1.5)  # Simulated processing
                    st.success("Analysis Complete!")
                    st.markdown("### Profile Summary")
                    st.write(f"**Subject:** {suspect_name}")
                    st.write(f"**Risk Rating:** {risk_level}")
                    st.write(f"**Matched Precedents:** {len(st.session_state.indexed_cases)} loaded cases evaluated.")
            else:
                st.warning("Please provide suspect details and behavioral logs.")

    with col2:
        st.markdown("### Case Index Summary")
        st.metric("Indexed Cases", len(st.session_state.indexed_cases))
        st.info("Upload new JSON case files in the sidebar to expand retrieval coverage.")

# --- TAB 2: Pricing & Upgrade ---
with selected_tabs[1]:
    st.header("Upgrade Access Plan")
    p_col1, p_col2 = st.columns(2)
    
    with p_col1:
        st.subheader("Standard Investigator")
        st.write("₹4,999 / month")
        st.write("• Full Vector RAG Search\n• Up to 100 Case Uploads\n• PDF Exporting")
        
    with p_col2:
        st.subheader("Agency Pro")
        st.write("₹12,999 / month")
        st.write("• Unlimited RAG Operations\n• Real-time Agentic Profiling\n• Priority Support")
        
    st.markdown("---")
    st.subheader("Manual UPI Payment Gateway")
    
    pay_col1, pay_col2 = st.columns([1, 1])
    with pay_col1:
        selected_plan = st.selectbox("Select Plan", ["Standard Investigator (₹4,999)", "Agency Pro (₹12,999)"])
        amount = "4999" if "4,999" in selected_plan else "12999"
        upi_id = "detectiveai@upi"
        
        qr_buf = generate_upi_qr(upi_id, "DetectiveAI", amount)
        if qr_buf:
            st.image(qr_buf, caption=f"Scan to Pay ₹{amount} via UPI", width=220)
        else:
            st.warning("Please install `segno` or `qrcode` + `Pillow` to display QR code images.")
            st.code(f"UPI ID: {upi_id}\nAmount: ₹{amount}")

    with pay_col2:
        st.write("### Submit Payment Details")
        utr = st.text_input("Transaction Reference / UTR Number")
        payer_name = st.text_input("Payer Name / Agency Name")
        
        if st.button("Submit Payment for Verification"):
            if utr and payer_name:
                st.session_state.payments.append({
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "payer": payer_name,
                    "plan": selected_plan,
                    "utr": utr,
                    "amount": amount,
                    "status": "Pending"
                })
                st.success("Payment details submitted successfully! Awaiting admin verification.")
            else:
                st.error("Please fill in all required payment details.")

# --- TAB 3: Contact & Security ---
with selected_tabs[2]:
    st.header("Security & Data Integrity")
    st.markdown(
        """
        * **Data Privacy:** Local vector indexes remain isolated to your deployment.
        * **Verification:** Payments are verified manually — we never store credit card or sensitive banking credentials directly.
        * **Support & Enquiries:** Contact the system administrator for technical integration support.
        """
    )

# --- TAB 4: Admin Dashboard (Conditional) ---
if st.session_state.is_admin:
    with selected_tabs[3]:
        st.header("Admin Dashboard — Payment Approvals")
        if not st.session_state.payments:
            st.info("No payment submissions found.")
        else:
            for idx, pay in enumerate(st.session_state.payments):
                with st.expander(f"UTR: {pay['utr']} — {pay['payer']} ({pay['status']})"):
                    st.write(f"**Date:** {pay['timestamp']}")
                    st.write(f"**Plan:** {pay['plan']}")
                    st.write(f"**Amount:** ₹{pay['amount']}")
                    
                    c1, c2 = st.columns(2)
                    if c1.button("Approve Upgrade", key=f"app_{idx}"):
                        pay['status'] = "Approved"
                        st.session_state.user_plan = pay['plan']
                        st.success(f"Approved {pay['payer']}! Plan updated.")
                        st.rerun()
                    if c2.button("Flag Issue / Reject", key=f"rej_{idx}"):
                        pay['status'] = "Rejected"
                        st.warning(f"Payment {pay['utr']} rejected.")
                        st.rerun()

    # --- TAB 5: Outreach & Leads (Conditional) ---
    with selected_tabs[4]:
        st.header("Cold Outreach & Agency Lead Pipeline")
        st.write("Manage enterprise agency leads and automated communication workflows.")
        st.text_input("Lead Agency Name")
        st.text_input("Target Email")
        if st.button("Send Profiling Demo Invitation"):
            st.success("Invitation dispatched successfully!") 
