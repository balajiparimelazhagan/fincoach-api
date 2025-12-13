"""
Transaction Extractor Agent for extracting transaction information from emails.
Converts email content into structured transaction data using Google ADK Agent.
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
)


class TransactionType(Enum):
    """Enum for transaction types"""
    INCOME = "income"
    EXPENDITURE = "expense"
    REFUND = "refund"


@dataclass
class Transaction:
    """Data class representing a parsed transaction"""
    amount: float
    transaction_type: TransactionType
    date: str
    category: str
    description: Optional[str] = None
    transactor: Optional[str] = None
    transactor_source_id: Optional[str] = None
    confidence: float = 1.0
    message_id: Optional[str] = None
    bank_name: Optional[str] = None
    account_last_four: Optional[str] = None
    
    # Keep source for backward compatibility (maps to transactor)
    @property
    def source(self) -> Optional[str]:
        return self.transactor

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
            "message_id": self.message_id,
            "bank_name": self.bank_name,
            "account_last_four": self.account_last_four,
        }


class TransactionExtractorAgent:
    """Transaction Extractor Agent using Google ADK"""

    def __init__(self):
        """Initialize the transaction extractor agent"""
        self.categories = list(DEFAULT_CATEGORIES)
        self._categories_cache = ", ".join(self.categories)
        self._system_message = self._get_system_message()      
        
        # Initialize account extractor for A2A coordination
        from agent.account_extractor import AccountExtractorAgent
        self.account_extractor = AccountExtractorAgent()
    
        self.agent = Agent(
            model="gemini-2.5-flash",
            name="transaction_extractor_agent",
            description="Extracts transaction information from email content",
            instruction=self._system_message,
        )

    def _get_system_message(self) -> str:
        """Create the reusable parsing instruction."""
        categories_str = self._categories_cache
        return f"""You are an expert transaction extractor for financial data. 
            Your task is to extract transaction information from email content.

            For each email, extract:
            1. Amount (numerical value)
            2. Transaction Type: CRITICAL - Determine the correct type:
               - 'refund' if this is a REVERSAL, REFUND, or CANCELLED transaction (money returned)
               - 'income' if money is being RECEIVED (credit, deposit, transfer in)
               - 'expense' if money is being SPENT (debit, payment, transfer out)
               Keywords for refund: reversal, reversed, refund, refunded, cancelled, cancellation, credited back
            3. Date and Time (in YYYY-MM-DD HH:MM:SS format, use current date and time if not found)
            4. Category (choose from: {categories_str})
            5. Description (brief description of the transaction)
            6. Transactor (who sent the money or who received it, name of transactor or bank or UPI ID)
            7. Transactor Source ID (transactor's UPI ID or bank ID or null if not available)

            Always return the response as a valid JSON object with these exact fields:
            {{
                "amount": <number>,
                "transaction_type": "<income|expense|refund>",
                "date": "<YYYY-MM-DD HH:MM:SS>",
                "category": "<category>",
                "description": "<description>",
                "transactor": "<transactor>",
                "transactor_source_id": "<transactor_source_id>"
            }}

            If any information is missing, make a reasonable inference based on the email content.
            Be precise with amounts and dates. For ambiguous cases, indicate confidence level."""

    def _refresh_system_message(self) -> None:
        """Refresh cached category string and parsing instruction."""
        self._categories_cache = ", ".join(self.categories)
        self._system_message = self._get_system_message()

    def parse_email(self, message_id: str, email_subject: str, email_body: str, sender_email: Optional[str] = None) -> Optional[Transaction]:
        """
        Parse an email and extract transaction information.

        Args:
            message_id: The Gmail message ID.
            email_subject: Subject line of the email
            email_body: Body content of the email
            sender_email: Optional sender email address for account extraction

        Returns:
            Transaction object with extracted information (including account info), or None if parsing fails
        """
        # Prepare the email content for the agent
        email_content = f"Subject: {email_subject}\n\nBody:\n{email_body}"

        try:
            # First try the LLM model if available
            response = self._query_model(email_content)
            transaction_data = self._extract_json_from_response(response)

            # If LLM didn't return structured JSON, fall back to regex parsing
            if not transaction_data:
                transaction_data = self._parse_with_regex(message_id, email_subject, email_body)

            if transaction_data:
                # Extract account information using A2A coordination
                account_info = self.account_extractor.extract_account_info(
                    message_text=email_body,
                    sender_email=sender_email,
                    sender_sms=None
                )
                
                # Add account info to transaction data
                transaction_data['bank_name'] = account_info.bank_name
                transaction_data['account_last_four'] = account_info.account_last_four
                
                # Create and return Transaction object
                return self._create_transaction(transaction_data, message_id)
        except Exception as e:
            print(f"Error parsing email: {e}")

        return None

    def _parse_with_regex(self, message_id: str, subject: str, body: str) -> Optional[Dict]:
        """Fallback parser using regexes to handle bank / UPI notification formats.

        Returns a dict with keys compatible with _create_transaction or None.
        """
        text = f"{subject}\n\n{body}"

        # Amount detection (handles Rs., INR, ₹ and numbers with commas)
        amount = None
        amt_match = AMOUNT_PATTERN.search(text)
        if not amt_match:
            # fallback to plain numbers with currency-like context
            amt_match = ALT_AMOUNT_PATTERN.search(text)
        if amt_match:
            try:
                amt_str = amt_match.group(1).replace(",", "")
                amount = float(amt_str)
            except Exception:
                amount = None

        # Date detection: dd-mm-yy or dd-mm-yyyy or dd/mm/yy with optional time
        date_str = None
        date_match = DATE_PATTERN.search(text)
        if date_match:
            raw = date_match.group(1)
            # normalize to YYYY-MM-DD HH:MM:SS
            for fmt in DATE_FORMATS:
                try:
                    dt = datetime.strptime(raw, fmt)
                    # two-digit years: assume 2000s
                    if dt.year < 100:
                        dt = dt.replace(year=dt.year + 2000)
                    date_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                    break
                except Exception:
                    continue

        # Transaction type: Check for refund first, then debit/credit
        trans_type = None
        if REFUND_PATTERN.search(text):
            trans_type = "refund"
        elif DEBIT_PATTERN.search(text):
            trans_type = "expense"
        elif CREDIT_PATTERN.search(text):
            trans_type = "income"

        # Source / bank name
        source = None
        bank_match = BANK_PATTERN.search(text)
        if bank_match:
            source = bank_match.group(1)

        # UPI / reference detection
        ref = None
        ref_match = REF_PATTERN.search(text)
        if not ref_match:
            ref_match = ALT_REF_PATTERN.search(text)
        if ref_match:
            ref = ref_match.group(1)

        # Account info
        acct_from = None
        acct_match = ACCOUNT_PATTERN.search(text)
        if acct_match:
            acct_from = acct_match.group(1)
        else:
            acct_match = ALT_ACCOUNT_PATTERN.search(text)
            if acct_match:
                acct_from = acct_match.group(1)

        # Category inference
        category = None
        if UPI_PATTERN.search(text):
            category = "UPI Transfer"
        elif TRANSFER_PATTERN.search(text):
            category = "Bank Transfer"
        elif BILL_PATTERN.search(text):
            category = "Bills"
        else:
            category = "Other"

        # Description
        desc_parts = []
        if ref:
            desc_parts.append(f"Ref {ref}")
        if acct_from:
            desc_parts.append(f"From acct {acct_from}")
        # include a short snippet
        snippet = re.sub(r"\s+", " ", text.strip())
        if len(snippet) > 120:
            snippet = snippet[:117] + "..."
        desc_parts.append(snippet)
        description = "; ".join(desc_parts) if desc_parts else None

        # Build result dict if at least amount and date or amount and type present
        result: Dict = {}
        if amount is not None:
            result["amount"] = amount
            result["transaction_type"] = trans_type or "expense"
            result["date"] = date_str or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            result["category"] = category or "Other"
            result["description"] = description
            result["transactor"] = source or ""
            result["transactor_source_id"] = ref or acct_from
            result["confidence"] = 0.8
            result["message_id"] = message_id
            return result

        return None

    def _query_model(self, email_content: str) -> str:
        """
        Query the Gemini model directly for email parsing.

        Args:
            email_content: The email content to parse

        Returns:
            The model's response as a string
        """
        try:
            from google.genai import Client
            client = Client()
            
            prompt = f"""{self._system_message}
                EMAIL TO PARSE:
                {email_content}"""
            
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            
            return response.text
        except Exception as e:
            print(f"Error querying model: {e}")
            return ""

    def _extract_json_from_response(self, response: str) -> Optional[dict]:
        """
        Extract JSON from agent response.

        Args:
            response: Response from the agent

        Returns:
            Parsed JSON dictionary or None
        """
        try:
            # Try to find JSON block in response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                return json.loads(json_str)
        except json.JSONDecodeError:
            pass

        return None

    def _create_transaction(self, data: dict, message_id: str) -> Optional[Transaction]:
        """
        Create a Transaction object from parsed data.

        Args:
            data: Dictionary with transaction information
            message_id: The Gmail message ID.

        Returns:
            Transaction object or None if required fields are missing
        """
        try:
            # Validate required fields
            required_fields = ["amount", "transaction_type", "date", "category"]
            if not all(field in data for field in required_fields):
                return None

            # Filter out zero-amount transactions
            if data.get("amount", 0) == 0:
                return None

            # Parse transaction type
            trans_type_str = data.get("transaction_type", "").lower()
            transaction_type = (
                TransactionType.INCOME
                if trans_type_str == "income"
                else TransactionType.EXPENDITURE
            )

            # Create transaction
            transaction = Transaction(
                amount=float(data.get("amount", 0)),
                transaction_type=transaction_type,
                date=data.get("date", ""),
                category=data.get("category", "Other"),
                description=data.get("description"),
                transactor=data.get("transactor") or data.get("source"),
                transactor_source_id=data.get("transactor_source_id"),
                confidence=float(data.get("confidence", 1.0)),
                message_id=message_id,
                bank_name=data.get("bank_name"),
                account_last_four=data.get("account_last_four"),
            )

            return transaction
        except (ValueError, KeyError) as e:
            print(f"Error creating transaction: {e}")
            return None
