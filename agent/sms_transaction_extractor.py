"""
SMS Transaction Extractor Agent for extracting transaction information from SMS messages.
Converts SMS content into structured transaction data using Google ADK Agent.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import json
import os
import re
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv
from google.adk.agents.llm_agent import Agent

from .regex_constants import (
    ACCOUNT_PATTERN,
    ALT_ACCOUNT_PATTERN,
    ALT_AMOUNT_PATTERN,
    ALT_REF_PATTERN,
    AMOUNT_PATTERN,
    BANK_PATTERN,
    BILL_PATTERN,
    CREDIT_PATTERN,
    DATE_PATTERN,
    DEBIT_PATTERN,
    REF_PATTERN,
    REFUND_PATTERN,
    TRANSFER_PATTERN,
    UPI_PATTERN,
)

load_dotenv()

DEFAULT_CATEGORIES = [
    "Groceries",
    "Transportation",
    "Utilities",
    "Entertainment",
    "Healthcare",
    "Shopping",
    "Dining",
    "Salary",
    "Loan Payment",
    "EMI",
    "Bonus",
    "Refund",
    "Bills",
    "Insurance",
    "Subscription",
    "UPI Transfer",
    "Other",
]

DATE_FORMATS: Tuple[str, ...] = (
    "%d-%m-%Y %H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
    "%d-%m-%y %H:%M:%S",
    "%d/%m/%y %H:%M:%S",
    "%d-%m-%Y %H:%M",
    "%d/%m/%Y %H:%M",
    "%d-%m-%y %H:%M",
    "%d/%m/%y %H:%M",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%d-%m-%y",
    "%d/%m/%y",
    "%d-%b-%y",  # 05-DEC-25
    "%d-%b-%Y",  # 05-DEC-2025
)


class TransactionType(Enum):
    """Enum for transaction types"""
    INCOME = "income"
    EXPENDITURE = "expense"
    REFUND = "refund"


@dataclass
class SmsTransaction:
    """Data class representing a parsed SMS transaction"""
    amount: float
    transaction_type: TransactionType
    date: str
    category: str
    description: Optional[str] = None
    transactor: Optional[str] = None
    transactor_source_id: Optional[str] = None
    confidence: float = 1.0
    sms_id: Optional[str] = None  # Unique SMS identifier from device
    sender: Optional[str] = None  # SMS sender (e.g., bank short code)
    bank_name: Optional[str] = None
    account_last_four: Optional[str] = None
    
    def to_dict(self):
        """Convert transaction to dictionary"""
        return {
            "amount": self.amount,
            "transaction_type": self.transaction_type.value,
            "date": self.date,
            "category": self.category,
            "description": self.description,
            "transactor": self.transactor,
            "transactor_source_id": self.transactor_source_id,
            "confidence": self.confidence,
            "sms_id": self.sms_id,
            "sender": self.sender,
            "bank_name": self.bank_name,
            "account_last_four": self.account_last_four,
        }


class SmsTransactionExtractorAgent:
    """SMS Transaction Extractor Agent using Google ADK"""

    def __init__(self):
        """Initialize the SMS transaction extractor agent"""
        self.categories = list(DEFAULT_CATEGORIES)
        self._categories_cache = ", ".join(self.categories)
        self._system_message = self._get_system_message()
        
        # Initialize account extractor for A2A coordination
        from agent.account_extractor import AccountExtractorAgent
        self.account_extractor = AccountExtractorAgent()
        
        self.agent = Agent(
            model="gemini-2.5-flash",
            name="sms_transaction_extractor_agent",
            description="Extracts transaction information from SMS messages",
            instruction=self._system_message,
        )

    def _get_system_message(self) -> str:
        """Create the reusable parsing instruction for SMS."""
        categories_str = self._categories_cache
        return f"""You are an expert transaction extractor for financial SMS messages from Indian banks.
Your task is to extract transaction information from SMS content.

Common SMS patterns to recognize:
1. Loan/EMI deductions: "INR X deducted from ... towards [Lender Name]"
2. Salary credits: "INR X deposited/credited ... for Salary"
3. Debits: "INR X debited from ..."
4. Credits: "INR X credited to ..."
5. UPI transactions
6. Bill payments

For each SMS, extract:
1. Amount (numerical value, remove commas)
2. Transaction Type: CRITICAL - Determine the correct type:
   - 'expense' if money is being SPENT (debit, payment, transfer out, loan payment, EMI)
   - 'income' if money is being RECEIVED (credit, deposit, salary, transfer in)
   - 'refund' if this is a REVERSAL, REFUND, or CANCELLED transaction
3. Date and Time (in YYYY-MM-DD HH:MM:SS format, parse from SMS)
4. Category (choose from: {categories_str})
   - Use "Loan Payment" for EMI/loan deductions
   - Use "Salary" for salary credits
   - Use appropriate category based on transaction description
5. Description (brief description of the transaction, include purpose if mentioned)
6. Transactor (who sent the money or who received it - company name, bank name, or "Unknown")
7. Transactor Source ID (UMRN for loans, UPI ID, or account reference if available)

Always return the response as a valid JSON object with these exact fields:
{{
    "amount": <number>,
    "transaction_type": "<income|expense|refund>",
    "date": "<YYYY-MM-DD HH:MM:SS>",
    "category": "<category>",
    "description": "<description>",
    "transactor": "<transactor>",
    "transactor_source_id": "<transactor_source_id or null>"
}}

Examples:
1. Loan SMS: "INR 26,200.00 debited from HDFC Bank XX4319 on 05-DEC-25. Info: ACH D- TP ACH PNBHOUSINGFIN"
   → {{"amount": 26200, "transaction_type": "expense", "date": "2025-12-05 00:00:00", "category": "Loan Payment", "description": "Loan payment to PNB Housing Finance", "transactor": "PNB Housing Finance", "transactor_source_id": "HDFC7021807230034209"}}

2. Salary SMS: "INR 1,31,506.00 deposited in HDFC Bank A/c XX4319 on 28-NOV-25 for Salary NOV 2025"
   → {{"amount": 131506, "transaction_type": "income", "date": "2025-11-28 00:00:00", "category": "Salary", "description": "Salary for NOV 2025", "transactor": "Employer", "transactor_source_id": null}}

Be precise with amounts and dates. Extract all relevant information from the SMS."""

    def _refresh_system_message(self) -> None:
        """Refresh cached category string and parsing instruction."""
        self._categories_cache = ", ".join(self.categories)
        self._system_message = self._get_system_message()

    def parse_sms(
        self, 
        sms_id: str, 
        sms_body: str,
        sender: Optional[str] = None,
        timestamp: Optional[datetime] = None
    ) -> Optional[SmsTransaction]:
        """
        Parse an SMS and extract transaction information.

        Args:
            sms_id: Unique SMS identifier from device
            sms_body: Body content of the SMS
            sender: SMS sender (e.g., bank short code like "HDFCBK")
            timestamp: SMS received timestamp

        Returns:
            SmsTransaction object with extracted information (including account info), or None if parsing fails
        """
        try:
            # First try the LLM model
            response = self._query_model(sms_body, sender, timestamp)
            transaction_data = self._extract_json_from_response(response)

            # If LLM didn't return structured JSON, fall back to regex parsing
            if not transaction_data:
                transaction_data = self._parse_with_regex(sms_body, sender, timestamp)

            if transaction_data:
                # Extract account information using A2A coordination
                account_info = self.account_extractor.extract_account_info(
                    message_text=sms_body,
                    sender_email=None,
                    sender_sms=sender
                )
                
                # Add account info to transaction data
                transaction_data['bank_name'] = account_info.bank_name
                transaction_data['account_last_four'] = account_info.account_last_four
                
                # Create and return SmsTransaction object
                return self._create_transaction(transaction_data, sms_id, sender)
        except Exception as e:
            print(f"Error parsing SMS: {e}")

        return None

    def _query_model(
        self, 
        sms_body: str, 
        sender: Optional[str] = None,
        timestamp: Optional[datetime] = None
    ) -> str:
        """Query the LLM model for transaction extraction"""
        try:
            # Prepare context
            context = f"SMS Body: {sms_body}"
            if sender:
                context += f"\nSender: {sender}"
            if timestamp:
                context += f"\nReceived: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
            
            # Query the agent
            response = self.agent.query(context)
            return response.text if hasattr(response, 'text') else str(response)
        except Exception as e:
            print(f"Model query error: {e}")
            return ""

    def _extract_json_from_response(self, response: str) -> Optional[Dict]:
        """Extract JSON from LLM response"""
        try:
            # Try to find JSON in the response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                return json.loads(json_str)
        except json.JSONDecodeError:
            pass
        return None

    def _parse_with_regex(
        self, 
        sms_body: str, 
        sender: Optional[str] = None,
        timestamp: Optional[datetime] = None
    ) -> Optional[Dict]:
        """Fallback parser using regexes for Indian bank SMS patterns"""
        text = sms_body

        # Amount detection (handles Rs., INR, ₹ and numbers with commas)
        amount = None
        amt_match = AMOUNT_PATTERN.search(text)
        if not amt_match:
            amt_match = ALT_AMOUNT_PATTERN.search(text)
        if amt_match:
            try:
                amt_str = amt_match.group(1).replace(",", "")
                amount = float(amt_str)
            except Exception:
                amount = None

        if not amount:
            return None  # SMS without amount is not a transaction

        # Date detection
        date_str = None
        date_match = DATE_PATTERN.search(text)
        if date_match:
            raw = date_match.group(1)
            for fmt in DATE_FORMATS:
                try:
                    dt = datetime.strptime(raw, fmt)
                    # Handle two-digit years
                    if dt.year < 100:
                        dt = dt.replace(year=dt.year + 2000)
                    date_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                    break
                except Exception:
                    continue
        
        # Use SMS timestamp if date not found in text
        if not date_str and timestamp:
            date_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
        elif not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Transaction type detection
        trans_type = None
        if REFUND_PATTERN.search(text):
            trans_type = "refund"
        elif DEBIT_PATTERN.search(text):
            trans_type = "expense"
        elif CREDIT_PATTERN.search(text):
            trans_type = "income"
        else:
            # Default based on keywords
            if any(word in text.lower() for word in ["deducted", "payment", "paid", "debited"]):
                trans_type = "expense"
            elif any(word in text.lower() for word in ["deposited", "credited", "received", "salary"]):
                trans_type = "income"

        if not trans_type:
            trans_type = "expense"  # Default assumption

        # Determine category
        category = "Other"
        text_lower = text.lower()
        
        if "salary" in text_lower:
            category = "Salary"
        elif any(word in text_lower for word in ["loan", "emi", "housing", "finance"]):
            category = "Loan Payment"
        elif any(word in text_lower for word in ["upi", "transfer"]):
            category = "UPI Transfer"
        elif any(word in text_lower for word in ["bill", "electricity", "water", "gas"]):
            category = "Bills"
        elif "refund" in text_lower:
            category = "Refund"

        # Extract transactor
        transactor = None
        transactor_source_id = None
        
        # Look for company/lender names
        if "housing" in text_lower and "finance" in text_lower:
            transactor = "PNB Housing Finance"
        elif sender:
            transactor = sender
        
        # Extract UMRN or reference
        ref_match = REF_PATTERN.search(text) or ALT_REF_PATTERN.search(text)
        if ref_match:
            transactor_source_id = ref_match.group(1)
        
        # Extract account number for source_id if available
        if not transactor_source_id:
            acc_match = ACCOUNT_PATTERN.search(text) or ALT_ACCOUNT_PATTERN.search(text)
            if acc_match:
                transactor_source_id = acc_match.group(1)

        # Create description
        description = text[:100].strip()  # First 100 chars as description

        return {
            "amount": amount,
            "transaction_type": trans_type,
            "date": date_str,
            "category": category,
            "description": description,
            "transactor": transactor or "Unknown",
            "transactor_source_id": transactor_source_id,
        }

    def _create_transaction(
        self, 
        data: Dict, 
        sms_id: str,
        sender: Optional[str] = None
    ) -> Optional[SmsTransaction]:
        """Create SmsTransaction object from parsed data"""
        try:
            return SmsTransaction(
                amount=float(data["amount"]),
                transaction_type=TransactionType(data["transaction_type"]),
                date=data["date"],
                category=data["category"],
                description=data.get("description"),
                transactor=data.get("transactor"),
                transactor_source_id=data.get("transactor_source_id"),
                confidence=data.get("confidence", 0.85),  # Lower confidence for SMS
                sms_id=sms_id,
                sender=sender,
                bank_name=data.get("bank_name"),
                account_last_four=data.get("account_last_four"),
            )
        except (KeyError, ValueError) as e:
            print(f"Error creating transaction: {e}")
            return None

    def update_categories(self, new_categories: List[str]) -> None:
        """Update the list of available categories"""
        self.categories = new_categories
        self._refresh_system_message()
