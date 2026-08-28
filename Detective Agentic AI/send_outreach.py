import time
import pandas as pd
import yagmail

# --- SENDER CONFIGURATION ---
SENDER_EMAIL = "your_email@gmail.com"
APP_PASSWORD = "your_16_digit_app_password"  # Google Account -> Security -> App Passwords

EMAIL_SUBJECT = "AI-Powered Case Profiling & Intelligence System for {agency_name}"
EMAIL_BODY = """
Hi {agency_name} Team,

I came across your agency while reviewing active private investigation firms operating in Delhi NCR.

We have developed Detective Agentic AI—a specialized intelligence & suspect-profiling platform built specifically for small-to-midsize private detective agencies:

1. Modus Operandi Matching: Instantly cross-reference suspect behavioral traits against a database of global and Indian criminal precedents using RAG vector search.
2. Executive PDF Reports: Generate professional, client-ready risk assessment reports in one click.
3. Rapid Legacy Ingestion: Upload your agency's historical case files (.json) directly into a private vector store.

We are currently offering a 14-day free pilot for select regional agencies to help accelerate background profiling productivity.

Would you be open to a brief 5-minute live demo link or quick call this week?

Best regards,
Aditya Srivastava
Lead Developer & AI Architect
[Your Phone Number / Portfolio Link]
"""

def launch_outreach_campaign():
    print("🚀 Initializing Cold Email Outreach Campaign...")
    
    try:
        yag = yagmail.SMTP(SENDER_EMAIL, APP_PASSWORD)
        df = pd.read_csv("agency_leads.csv")
    except Exception as e:
        print(f"❌ Initialization Error: {e}")
        return

    for idx, row in df.iterrows():
        agency = row["Agency_Name"]
        recipient = row["Contact_Email"]

        body = EMAIL_BODY.format(agency_name=agency)
        subject = EMAIL_SUBJECT.format(agency_name=agency)

        try:
            # Uncomment the line below when ready to send real emails:
            # yag.send(to=recipient, subject=subject, contents=body)
            print(f"📧 [PREVIEW/READY] Email queued for: {agency} ({recipient})")
        except Exception as e:
            print(f"❌ Could not send to {agency}: {e}")

        # Safe delay between emails to avoid spam filters
        time.sleep(5)

    print("\n✅ Outreach processing complete!")

if __name__ == "__main__":
    launch_outreach_campaign() 