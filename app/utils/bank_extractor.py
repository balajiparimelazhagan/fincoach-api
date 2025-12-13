"""
Bank Name and Account Number Extractor
Extracts bank names and account numbers from transaction emails/SMS.
"""
import re
from typing import Optional, Tuple


# Common Indian bank names and their variations
BANK_PATTERNS = {
    # Format: canonical_name: [list of patterns to match]
    "HDFC Bank": [
        r"HDFC\s*Bank",
        r"HDFC",
        r"hdfcbank",
    ],
    "ICICI Bank": [
        r"ICICI\s*Bank",
        r"ICICI",
        r"icicibank",
    ],
    "State Bank of India": [
        r"State\s*Bank\s*of\s*India",
        r"SBI",
        r"onlinesbi",
    ],
    "Axis Bank": [
        r"Axis\s*Bank",
        r"Axis",
        r"axisbank",
    ],
    "Kotak Mahindra Bank": [
        r"Kotak\s*Mahindra\s*Bank",
        r"Kotak",
        r"kotak",
    ],
    "Punjab National Bank": [
        r"Punjab\s*National\s*Bank",
        r"PNB",
        r"pnb",
    ],
    "Bank of Baroda": [
        r"Bank\s*of\s*Baroda",
        r"BOB",
        r"bankofbaroda",
    ],
    "Canara Bank": [
        r"Canara\s*Bank",
        r"Canara",
        r"canarabank",
    ],
    "IndusInd Bank": [
        r"IndusInd\s*Bank",
        r"IndusInd",
        r"indusind",
    ],
    "Yes Bank": [
        r"Yes\s*Bank",
        r"YesBank",
        r"yesbank",
    ],
    "IDFC First Bank": [
        r"IDFC\s*First\s*Bank",
        r"IDFC\s*Bank",
        r"IDFC",
        r"idfcfirstbank",
    ],
    "Federal Bank": [
        r"Federal\s*Bank",
        r"Federal",
        r"federalbank",
    ],
    "Union Bank of India": [
        r"Union\s*Bank\s*of\s*India",
        r"Union\s*Bank",
        r"unionbankofindia",
    ],
    "Bank of India": [
        r"Bank\s*of\s*India",
        r"BOI",
        r"bankofindia",
    ],
    "Central Bank of India": [
        r"Central\s*Bank\s*of\s*India",
        r"Central\s*Bank",
        r"centralbankofindia",
    ],
    "Indian Bank": [
        r"Indian\s*Bank",
        r"indianbank",
    ],
    "Indian Overseas Bank": [
        r"Indian\s*Overseas\s*Bank",
        r"IOB",
        r"iob",
    ],
    "UCO Bank": [
        r"UCO\s*Bank",
        r"UCO",
        r"ucobank",
    ],
    "Bank of Maharashtra": [
        r"Bank\s*of\s*Maharashtra",
        r"bankofmaharashtra",
    ],
    "Standard Chartered Bank": [
        r"Standard\s*Chartered\s*Bank",
        r"Standard\s*Chartered",
        r"SC\s*Bank",
        r"standardchartered",
    ],
    "Citibank": [
        r"Citibank",
        r"Citi\s*Bank",
        r"Citi",
    ],
    "HSBC": [
        r"HSBC",
        r"Hongkong\s*and\s*Shanghai\s*Banking\s*Corporation",
    ],
    "Deutsche Bank": [
        r"Deutsche\s*Bank",
        r"Deutsche",
    ],
    "RBL Bank": [
        r"RBL\s*Bank",
        r"RBL",
        r"rblbank",
    ],
    "South Indian Bank": [
        r"South\s*Indian\s*Bank",
        r"southindianbank",
    ],
    "Karnataka Bank": [
        r"Karnataka\s*Bank",
        r"karnatakabank",
    ],
    "Karur Vysya Bank": [
        r"Karur\s*Vysya\s*Bank",
        r"KVB",
        r"kvb",
    ],
    "Bandhan Bank": [
        r"Bandhan\s*Bank",
        r"Bandhan",
        r"bandhanbank",
    ],
    "IDBI Bank": [
        r"IDBI\s*Bank",
        r"IDBI",
        r"idbibank",
    ],
    "Paytm Payments Bank": [
        r"Paytm\s*Payments\s*Bank",
        r"Paytm",
        r"paytmbank",
    ],
}

# Patterns to extract account numbers (last 4 digits)
ACCOUNT_NUMBER_PATTERNS = [
    r"account\s+(?:\*+)?(\d{4})",  # "account 4319" or "account ***4319"
    r"a/c\s+(?:\*+)?(\d{4})",      # "a/c 4319" or "a/c ***4319"
    r"ac\s+(?:\*+)?(\d{4})",       # "ac 4319" or "ac ***4319"
    r"(?:\*+)(\d{4})",             # "***4319" (standalone)
    r"xx+(\d{4})",                 # "xxxx4319"
    r"card\s+(?:\*+)?(\d{4})",    # "card 4319" or "card ***4319"
]


def extract_bank_name_from_text(text: str) -> Optional[str]:
    """
    Extract bank name from email/SMS text.
    
    Args:
        text: Email body or SMS text
        
    Returns:
        Bank name if found, otherwise None
    """
    if not text:
        return None
    
    text_lower = text.lower()
    
    # Try to match bank patterns
    for bank_name, patterns in BANK_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return bank_name
    
    return None


def extract_bank_name_from_sender(sender_email: str) -> Optional[str]:
    """
    Extract bank name from sender email address.
    
    Args:
        sender_email: Sender's email address
        
    Returns:
        Bank name if found, otherwise None
    """
    if not sender_email:
        return None
    
    sender_lower = sender_email.lower()
    
    # Try to match bank patterns in email domain
    for bank_name, patterns in BANK_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, sender_lower, re.IGNORECASE):
                return bank_name
    
    return None


def extract_account_last_four(text: str) -> Optional[str]:
    """
    Extract last 4 digits of account number from text.
    Handles formats like:
    - account 4319
    - account ***4319
    - a/c 4319
    - ***4319
    
    Args:
        text: Email body or SMS text
        
    Returns:
        Last 4 digits of account number if found, otherwise None
    """
    if not text:
        return None
    
    # Try each pattern
    for pattern in ACCOUNT_NUMBER_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # Get the last 4 digits
            last_four = match.group(1)
            # Validate it's exactly 4 digits
            if len(last_four) == 4 and last_four.isdigit():
                return last_four
    
    return None


def extract_bank_and_account(text: str, sender_email: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract both bank name and account last 4 digits from text.
    
    Args:
        text: Email body or SMS text
        sender_email: Optional sender email address
        
    Returns:
        Tuple of (bank_name, account_last_four)
        Either or both can be None if not found
    """
    # Extract bank name from text
    bank_name = extract_bank_name_from_text(text)
    
    # If not found in text, try sender email
    if not bank_name and sender_email:
        bank_name = extract_bank_name_from_sender(sender_email)
    
    # Extract account number
    account_last_four = extract_account_last_four(text)
    
    # If bank name still not found, use a default
    if not bank_name and account_last_four:
        bank_name = "Unknown"
    
    return bank_name, account_last_four
