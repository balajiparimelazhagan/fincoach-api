import re

AMOUNT_PATTERN = re.compile(r"(?:Rs\.?|INR|₹)\s*([0-9][0-9,]*\.?[0-9]*)", re.IGNORECASE)
ALT_AMOUNT_PATTERN = re.compile(
    r"([0-9][0-9,]*\.?[0-9]{0,2})\s*(?:INR|Rs|Rs\.|₹)", re.IGNORECASE
)
DATE_PATTERN = re.compile(r"(\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b)")
DEBIT_PATTERN = re.compile(r"\bdebited\b|\bdebit\b|\bwithdrawn\b", re.IGNORECASE)
CREDIT_PATTERN = re.compile(r"\bcredited\b|\bdeposit(?:ed)?\b|\brefund\b", re.IGNORECASE)
BANK_PATTERN = re.compile(
    r"(HDFC Bank|State Bank of India|SBI|ICICI Bank|Axis Bank|Kotak|Punjab National Bank)",
    re.IGNORECASE,
)
UPI_PATTERN = re.compile(r"\bUPI\b|UPI transaction|UPI ref|upi", re.IGNORECASE)
TRANSFER_PATTERN = re.compile(
    r"transfer to|transferred to|debited from account .* to account", re.IGNORECASE
)
BILL_PATTERN = re.compile(
    r"bill|due date|payment due|bill amount|electricity|water|gas|bill", re.IGNORECASE
)
REF_PATTERN = re.compile(r"reference (?:number )?(?:is )?:?\s*(\d{6,})", re.IGNORECASE)
ALT_REF_PATTERN = re.compile(
    r"UPI transaction reference number is\s*(\d+)", re.IGNORECASE
)
ACCOUNT_PATTERN = re.compile(r"from account\s*(\d{2,}\d*)", re.IGNORECASE)
ALT_ACCOUNT_PATTERN = re.compile(r"acct(?:ount)?[:#]?\s*(\d{2,}\d*)", re.IGNORECASE)

