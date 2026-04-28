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
    account_type: str = "savings"
    
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
            "account_type": self.account_type,
        }


class TransactionExtractorAgent:
    """Transaction Extractor Agent using Google ADK"""

    def __init__(self, db_session=None):
        """Initialize the transaction extractor agent
        
        Args:
            db_session: Optional database session for fetching dynamic categories
        """
        # Import CategoryMapper to get standard categories
        from app.utils.category_mapper import category_mapper
        
        self.category_mapper = category_mapper
        self.categories = self.category_mapper.get_all_categories()
        self._categories_cache = ", ".join(self.categories)
        self._db_session = db_session
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

    def _get_system_message(self, category_guidelines: Optional[str] = None) -> str:
        """Create the reusable parsing instruction.

        Args:
            category_guidelines: Optional pre-formatted category guidelines from database
        """
        categories_str = self._categories_cache

        # Use provided guidelines or fall back to default
        if not category_guidelines:
            category_guidelines = """- Housing: rent, mortgage, property tax, maintenance
               - Utilities: electricity, water, gas, internet bills
               - Food: groceries, restaurants, food delivery
               - Transport: fuel, taxi, public transport
               - Shopping: retail, online shopping, clothing
               - Subscriptions: Netflix, Spotify, recurring services
               - Health: hospital, medicine, gym, fitness
               - Entertainment: movies, games, sports events
               - Travel: flights, hotels, vacation
               - Personal Care: salon, spa, grooming
               - Education: school, courses, books
               - Family & Relationships: gifts, celebrations
               - Income: salary, freelance, refunds
               - Savings: deposits, FD, mutual funds, SIP, stocks, investments
               - Loans & EMIs: loan payments, credit card
               - Transfers: UPI, NEFT, bank transfers
               - Fees & Charges: bank fees, penalties
               - Taxes: income tax, GST
               - Donations: charity, religious donations
               - Miscellaneous: anything that doesn't fit above"""

        return f"""You are an expert transaction extractor for financial data.

STEP 1 — INTENT CHECK:
First decide if this email describes a COMPLETED financial transaction.
Return ONLY {{"is_transaction": false}} if the email is any of these:
- Promotional or marketing content (offers, cashback deals, discounts, vouchers)
- A payment reminder or upcoming due date notification
- An account statement or balance summary
- An informational update with no completed transaction
- OTP or verification messages

STEP 2 — EXTRACTION:
Only if this IS a completed transaction, extract the details and return:

{{
    "is_transaction": true,
    "amount": <number>,
    "transaction_type": "<income|expense|refund>",
    "date": "<YYYY-MM-DD HH:MM:SS>",
    "category": "<category>",
    "description": "<description>",
    "transactor": "<transactor>",
    "transactor_source_id": "<transactor_source_id>"
}}

Transaction type rules:
- 'refund' if this is a REVERSAL, REFUND, or CANCELLED transaction (money returned)
- 'income' if money is being RECEIVED (credit, deposit, transfer in)
- 'expense' if money is being SPENT (debit, payment, transfer out)
Keywords for refund: reversal, reversed, refund, refunded, cancelled, cancellation, credited back

Date: extract the transaction date from the email body. Indian bank emails use formats like
"on 20-04-26" (DD-MM-YY), "20-04-2026" (DD-MM-YYYY), or "20/04/2026". Two-digit years mean 2000s
(26 → 2026). Return YYYY-MM-DD HH:MM:SS. If no time is given use 00:00:00. If no date found return null.

Category — choose EXACTLY ONE from this list:
{categories_str}

Category Guidelines:
{category_guidelines}

Transactor: who sent the money or who received it (name, bank, or UPI ID).
Transactor Source ID: UPI ID or bank reference ID, or null if not available.

IMPORTANT: The category field MUST be one of the exact category names from the list above.
If any information is missing, make a reasonable inference based on the email content."""

    async def refresh_categories_from_db(self, db) -> None:
        """Refresh categories and guidelines from database.
        
        Args:
            db: Database session
        """
        self._categories_cache = ", ".join(self.categories)
        category_guidelines = await self.category_mapper.get_category_guidelines_text(db)
        self._system_message = self._get_system_message(category_guidelines)
        self.agent.instruction = self._system_message

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

            # Check if LLM explicitly identified this as a non-transaction email
            if transaction_data and not transaction_data.get("is_transaction", True):
                return None

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
                transaction_data['account_type'] = account_info.account_type
                
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
            date_str = self._normalize_date(date_match.group(1))

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

        # Category inference using standard categories
        category = None
        if UPI_PATTERN.search(text):
            category = "Transfers"  # Map UPI Transfer to standard category
        elif TRANSFER_PATTERN.search(text):
            category = "Transfers"  # Map Bank Transfer to standard category
        elif BILL_PATTERN.search(text):
            category = "Fees & Charges"  # Map Bills to standard category
        else:
            category = "Miscellaneous"  # Map Other to standard category

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
            if not date_str:
                return None  # reject: no reliable date found
            result["date"] = date_str
            result["category"] = category or "Miscellaneous"
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

    _PARSE_FORMATS: Tuple[str, ...] = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d-%m-%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%d/%m/%Y %H:%M",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d-%m-%y %H:%M:%S",
        "%d/%m/%y %H:%M:%S",
        "%d-%m-%y",
        "%d/%m/%y",
    )

    def _normalize_date(self, date_str: str) -> Optional[str]:
        """Parse any recognisable date string and return YYYY-MM-DD HH:MM:SS, or None."""
        if not date_str or str(date_str).lower() in ("null", "none", ""):
            return None
        for fmt in self._PARSE_FORMATS:
            try:
                dt = datetime.strptime(str(date_str).strip(), fmt)
                if dt.year < 100:
                    dt = dt.replace(year=dt.year + 2000)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
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

            # Parse transaction type - check category for Refund as well
            trans_type_str = data.get("transaction_type", "").lower()
            category = data.get("category", "Miscellaneous")
            
            # Validate category to standard categories
            validated_category = self.category_mapper.validate_category(category)
            
            # If category is "Income" or indicates refund, adjust transaction type
            if validated_category == "Income" or trans_type_str == "refund":
                transaction_type = TransactionType.REFUND if trans_type_str == "refund" else TransactionType.INCOME
            elif trans_type_str == "income":
                transaction_type = TransactionType.INCOME
            else:
                transaction_type = TransactionType.EXPENDITURE

            # Normalize date — reject transaction if date cannot be parsed
            normalized_date = self._normalize_date(data.get("date"))
            if not normalized_date:
                print(f"Skipping transaction: unparseable date {data.get('date')!r}")
                return None

            # Create transaction
            transaction = Transaction(
                amount=float(data.get("amount", 0)),
                transaction_type=transaction_type,
                date=normalized_date,
                category=validated_category,  # Use validated category
                description=data.get("description"),
                transactor=data.get("transactor") or data.get("source"),
                transactor_source_id=data.get("transactor_source_id"),
                confidence=float(data.get("confidence", 1.0)),
                message_id=message_id,
                bank_name=data.get("bank_name"),
                account_last_four=data.get("account_last_four"),
                account_type=data.get("account_type", "savings"),
            )

            return transaction
        except (ValueError, KeyError) as e:
            print(f"Error creating transaction: {e}")
            return None
