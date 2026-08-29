import os
import json
import re
import time
from typing import Tuple, List, Dict, Any

# File Paths
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
PAYMENTS_FILE = os.path.join(DATA_DIR, "payments.json")

# Status Constants
STATUS_PENDING = "PENDING"
STATUS_APPROVED = "APPROVED"
STATUS_PARTIAL = "PARTIAL"
STATUS_TOPUP_DONE = "TOPUP_DONE"
STATUS_FLAGGED = "FLAGGED"
STATUS_INVALID_UTR = "INVALID_UTR"


def _ensure_data_dir():
    """Ensures that the data directory exists."""
    os.makedirs(DATA_DIR, exist_ok=True)


def load_payments() -> List[Dict[str, Any]]:
    """Loads payment records from JSON file."""
    _ensure_data_dir()
    if not os.path.exists(PAYMENTS_FILE):
        return []
    try:
        with open(PAYMENTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_payments(payments: List[Dict[str, Any]]):
    """Saves payment records to JSON file."""
    _ensure_data_dir()
    with open(PAYMENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(payments, f, indent=2, ensure_ascii=False)


def validate_utr_format(utr: str) -> bool:
    """
    Validates Indian standard UPI UTR / RRN numbers.
    Standard UTR numbers are strictly 12 digits.
    """
    cleaned_utr = utr.strip()
    return bool(re.match(r"^\d{12}$", cleaned_utr))


def submit_payment(
    plan: str,
    required_amount: float,
    amount_paid: float,
    evals: Any,
    utr: str
) -> Tuple[str, str, float]:
    """
    Submits and processes a payment proof:
    1. Validates UTR structure (returns error if fake/invalid format).
    2. Checks for duplicate UTR submissions.
    3. Calculates remaining deficit balance.
    4. Auto-approves if full payment is reached.
    """
    utr_clean = utr.strip()

    # Step 1: Validate UTR format
    if not validate_utr_format(utr_clean):
        return (
            STATUS_INVALID_UTR,
            "❌ Invalid UTR ID! Bank transaction reference numbers must be exactly 12 numerical digits.",
            required_amount
        )

    payments = load_payments()

    # Step 2: Check for duplicate UTR submissions
    for pmt in payments:
        if pmt.get("utr") == utr_clean:
            return STATUS_FLAGGED, "⚠️ This UTR ID has already been submitted and processed.", 0.0

    # Step 3: Calculate balance
    remaining = max(0.0, required_amount - amount_paid)

    if amount_paid >= required_amount:
        status = STATUS_APPROVED
        msg = f"🎉 Congratulations! Payment of ₹{amount_paid:,.0f} verified. Your plan '{plan}' is now fully active with {evals} evaluations!"
    else:
        status = STATUS_PARTIAL
        msg = f"⚠️ Partial Payment Detected: Plan price is ₹{required_amount:,.0f}, but you paid ₹{amount_paid:,.0f}. Please pay the remaining ₹{remaining:,.0f} to unlock your evaluations."

    new_record = {
        "utr": utr_clean,
        "plan": plan,
        "required_amount": required_amount,
        "amount_paid": amount_paid,
        "remaining_balance": remaining,
        "evals": evals,
        "status": status,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "topup_utrs": []
    }

    payments.append(new_record)
    save_payments(payments)
    return status, msg, remaining


def submit_topup(topup_utr: str, parent_utr: str, topup_amount: float) -> Tuple[str, str, float]:
    """
    Processes a top-up payment for an incomplete payment balance:
    Deducts new amount from remaining balance and auto-approves when remaining == 0.
    """
    topup_utr_clean = topup_utr.strip()

    if not validate_utr_format(topup_utr_clean):
        return (
            STATUS_INVALID_UTR,
            "❌ Invalid Top-Up UTR ID! Must be a valid 12-digit bank reference number.",
            0.0
        )

    payments = load_payments()

    for pmt in payments:
        if pmt.get("utr") == parent_utr:
            if "topup_utrs" not in pmt:
                pmt["topup_utrs"] = []

            if topup_utr_clean in pmt["topup_utrs"] or topup_utr_clean == parent_utr:
                return STATUS_FLAGGED, "⚠️ This top-up UTR has already been submitted.", pmt.get("remaining_balance", 0.0)

            # Update totals
            pmt["topup_utrs"].append(topup_utr_clean)
            pmt["amount_paid"] += topup_amount
            new_remaining = max(0.0, pmt["required_amount"] - pmt["amount_paid"])
            pmt["remaining_balance"] = new_remaining

            if new_remaining == 0.0:
                pmt["status"] = STATUS_APPROVED
                msg = f"🎉 Congratulations! Top-up of ₹{topup_amount:,.0f} completed your payment. Your '{pmt['plan']}' plan is unlocked!"
            else:
                pmt["status"] = STATUS_PARTIAL
                msg = f"⚠️ Top-up of ₹{topup_amount:,.0f} received. Remaining balance: ₹{new_remaining:,.0f}. Please pay the rest to unlock."

            save_payments(payments)
            return pmt["status"], msg, new_remaining

    return STATUS_FLAGGED, "❌ Original payment record not found.", 0.0


def approve_payment(utr: str) -> bool:
    """Manually approves a payment record from the admin panel."""
    payments = load_payments()
    for pmt in payments:
        if pmt.get("utr") == utr:
            pmt["status"] = STATUS_APPROVED
            pmt["remaining_balance"] = 0.0
            save_payments(payments)
            return True
    return False


def flag_partial(utr: str) -> bool:
    """Flags a payment record as partial/incomplete."""
    payments = load_payments()
    for pmt in payments:
        if pmt.get("utr") == utr:
            pmt["status"] = STATUS_PARTIAL
            save_payments(payments)
            return True
    return False


def get_pending_payments() -> List[Dict[str, Any]]:
    """Returns all payment submissions awaiting review or completion."""
    payments = load_payments()
    return [p for p in payments if p.get("status") in [STATUS_PENDING, STATUS_PARTIAL, STATUS_TOPUP_DONE]]


def get_partial_by_utr(utr: str) -> Dict[str, Any]:
    """Retrieves a specific partial payment record by UTR."""
    payments = load_payments()
    for p in payments:
        if p.get("utr") == utr and p.get("status") in [STATUS_PARTIAL, STATUS_TOPUP_DONE]:
            return p
    return {} 
