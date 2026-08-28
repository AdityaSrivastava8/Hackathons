"""
agent/billing.py
UTR Reference ID & Amount Validation Engine with Partial Payment Recovery
"""

import json
import os
import re
import time
from typing import Dict, List, Tuple

DATA_DIR      = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
PAYMENTS_FILE = os.path.join(DATA_DIR, "payments.json")

# ── Payment status constants ───────────────────────────────────────────────────
STATUS_PENDING     = "Pending Verification"
STATUS_APPROVED    = "Approved"
STATUS_PARTIAL     = "Partial Payment - Action Required"
STATUS_FLAGGED     = "Flagged"
STATUS_TOPUP_DONE  = "Top-Up Submitted"


def _load_raw() -> List[Dict]:
    if not os.path.exists(PAYMENTS_FILE):
        return []
    try:
        with open(PAYMENTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_raw(payments: List[Dict]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PAYMENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(payments, f, indent=2, ensure_ascii=False)


# ── Core validation function ───────────────────────────────────────────────────

def verify_payment_reference(
    utr: str,
    amount_paid: float,
    required_amount: float,
    plan: str,
    evals,
    existing_payments: List[Dict],
) -> Tuple[str, str, float]:
    """
    Validate a UPI UTR submission.

    Returns (status, message, remaining_balance).

    Step A — Format & uniqueness:
        UTR must be 8–22 alphanumeric chars and not already used.
    Step B — Exact match:
        amount_paid == required_amount  →  STATUS_APPROVED
    Step C — Underpayment:
        amount_paid < required_amount   →  STATUS_PARTIAL
    Step D — Overpayment (unlikely but handled):
        amount_paid > required_amount   →  STATUS_APPROVED (excess ignored)
    """
    utr = utr.strip()

    # Step A — Format check
    if not re.match(r"^[A-Za-z0-9]{8,22}$", utr):
        return (
            STATUS_FLAGGED,
            "❌ Invalid UTR format. A valid UPI UTR is 8–22 alphanumeric characters.",
            0.0,
        )

    # Step A — Uniqueness check (ignore top-up entries which share base UTR)
    used_utrs = {p.get("utr", "") for p in existing_payments if p.get("utr")}
    if utr in used_utrs:
        return (
            STATUS_FLAGGED,
            f"❌ UTR `{utr}` has already been submitted. Each transaction can only be used once.",
            0.0,
        )

    remaining = max(0.0, required_amount - amount_paid)

    # Step B / D — Exact or overpayment
    if amount_paid >= required_amount:
        return STATUS_APPROVED, "✅ Payment verified. Full amount received.", 0.0

    # Step C — Underpayment
    return (
        STATUS_PARTIAL,
        (
            f"⚠️ Partial payment detected. "
            f"You paid ₹{amount_paid:,.0f} out of ₹{required_amount:,.0f}. "
            f"Remaining balance: ₹{remaining:,.0f}."
        ),
        remaining,
    )


def submit_payment(
    plan: str,
    required_amount: float,
    amount_paid: float,
    evals,
    utr: str,
) -> Tuple[str, str, float]:
    """
    Full submission pipeline: validate then persist to payments.json.
    Returns (status, message, remaining_balance).
    """
    existing = _load_raw()
    status, message, remaining = verify_payment_reference(
        utr, amount_paid, required_amount, plan, evals, existing
    )

    record = {
        "plan":             plan,
        "required_amount":  required_amount,
        "amount_paid":      amount_paid,
        "remaining_balance": remaining,
        "evals":            evals,
        "utr":              utr.strip(),
        "status":           status,
        "timestamp":        time.strftime("%Y-%m-%d %H:%M:%S"),
        "topup_utrs":       [],   # list of subsequent top-up UTR submissions
    }
    existing.append(record)
    _save_raw(existing)
    return status, message, remaining


def submit_topup(utr_topup: str, original_utr: str) -> Tuple[str, str]:
    """
    Record a top-up UTR for a previously partial payment.
    Returns (new_status, message).
    """
    utr_topup = utr_topup.strip()
    existing  = _load_raw()

    # Validate format
    if not re.match(r"^[A-Za-z0-9]{8,22}$", utr_topup):
        return STATUS_PARTIAL, "❌ Invalid top-up UTR format."

    # Prevent reuse
    all_utrs = {p.get("utr", "") for p in existing}
    all_topups = {t for p in existing for t in p.get("topup_utrs", [])}
    if utr_topup in all_utrs or utr_topup in all_topups:
        return STATUS_PARTIAL, "❌ This UTR has already been used."

    for p in existing:
        if p.get("utr") == original_utr:
            p["topup_utrs"].append(utr_topup)
            p["status"] = STATUS_TOPUP_DONE
            break

    _save_raw(existing)
    return STATUS_TOPUP_DONE, "✅ Top-up submitted! Admin will verify and unlock your quota."


def approve_payment(utr: str) -> bool:
    """Admin action: mark a record as Approved and return True if found."""
    existing = _load_raw()
    found = False
    for p in existing:
        if p.get("utr") == utr:
            p["status"] = STATUS_APPROVED
            found = True
    if found:
        _save_raw(existing)
    return found


def flag_partial(utr: str) -> bool:
    """Admin action: explicitly flag as partial (prompts user for top-up)."""
    existing = _load_raw()
    found = False
    for p in existing:
        if p.get("utr") == utr:
            p["status"] = STATUS_PARTIAL
            found = True
    if found:
        _save_raw(existing)
    return found


def get_pending_payments() -> List[Dict]:
    """Return all payments not yet approved."""
    return [
        p for p in _load_raw()
        if p.get("status") not in (STATUS_APPROVED,)
    ]


def get_partial_by_utr(utr: str) -> Dict:
    """Return a single partial-payment record by its UTR."""
    for p in _load_raw():
        if p.get("utr") == utr and p.get("status") == STATUS_PARTIAL:
            return p
    return {}
