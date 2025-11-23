"""
Email Parser Agent for extracting transaction information from emails.
Converts email content into structured transaction data using Google ADK Agent.
"""

from dataclasses import dataclass
from typing import Optional, List, Dict
from enum import Enum
from google.adk.agents.llm_agent import Agent
import json
import re
import os
from pathlib import Path
from datetime import datetime


class TransactionType(Enum):
    """Enum for transaction types"""
    INCOME = "income"
    EXPENDITURE = "expenditure"


@dataclass
class Transaction:
    """Data class representing a parsed transaction"""
    amount: float
    transaction_type: TransactionType
    date: str
    category: str
    description: Optional[str] = None
    source: Optional[str] = None
    confidence: float = 1.0
    message_id: Optional[str] = None

    def to_dict(self):
        """Convert transaction to dictionary"""
        return {
            "amount": self.amount,
            "transaction_type": self.transaction_type.value,
            "date": self.date,
            "category": self.category,
            "description": self.description,
            "source": self.source,
            "confidence": self.confidence,
            "message_id": self.message_id,
        }


class EmailParserAgent:
    """Email Parser Agent using Google ADK"""

    # Common transaction categories
    PREDEFINED_CATEGORIES = [
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

    def __init__(self):
        """Initialize the email parser agent"""
        # Load API key first
        api_key = self._load_api_key()
        
        # Set environment variable for google.genai to pick up
        if api_key:
            os.environ["GOOGLE_API_KEY"] = api_key
        
        try:
            from google.genai import Client
            # Client will use the GOOGLE_API_KEY environment variable
            self.client = Client()
            self.use_genai = True
        except Exception as e:
            print(f"Warning: Could not initialize Genai client: {e}")
            self.use_genai = False
        
        self.agent = Agent(
            model="gemini-2.5-flash",
            name="email_parser_agent",
            description="Extracts transaction information from email content",
            instruction=self._get_parsing_instruction(),
        )

    def _load_api_key(self) -> Optional[str]:
        """Load API key from .env file or environment variable"""
        # First try environment variable
        api_key = os.getenv("GOOGLE_API_KEY")
        if api_key:
            return api_key
        
        # Then try .env file in my_agent directory
        env_path = Path(__file__).parent / ".env"
        if env_path.exists():
            try:
                with open(env_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if line.startswith("GOOGLE_API_KEY="):
                            key = line.split("=", 1)[1].strip()
                            if key:
                                return key
            except Exception as e:
                print(f"Warning: Could not read .env file: {e}")
        
        return None

    def _get_parsing_instruction(self) -> str:
        """Generate the instruction for the agent"""
        categories_str = ", ".join(self.PREDEFINED_CATEGORIES)
        return f"""You are an expert email parser for financial transactions. 
Your task is to extract transaction information from email content.

For each email, extract:
1. Amount (numerical value)
2. Transaction Type (either 'income' or 'expenditure')
3. Date (in YYYY-MM-DD format, use current date if not found)
4. Category (choose from: {categories_str})
5. Description (brief description of the transaction)
6. Source (who sent the email or company name)

Always return the response as a valid JSON object with these exact fields:
{{
    "amount": <number>,
    "transaction_type": "<income or expenditure>",
    "date": "<YYYY-MM-DD>",
    "category": "<category>",
    "description": "<description>",
    "source": "<source>"
}}

If any information is missing, make a reasonable inference based on the email content.
Be precise with amounts and dates. For ambiguous cases, indicate confidence level."""

    def parse_email(self, message_id: str, email_subject: str, email_body: str) -> Optional[Transaction]:
        """
        Parse an email and extract transaction information.

        Args:
            message_id: The Gmail message ID.
            email_subject: Subject line of the email
            email_body: Body content of the email

        Returns:
            Transaction object with extracted information, or None if parsing fails
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
        amt_match = re.search(r"(?i)(?:Rs\.?|INR|₹)\s*([0-9][0-9,]*\.?[0-9]*)", text)
        if not amt_match:
            # fallback to plain numbers with currency-like context
            amt_match = re.search(r"([0-9][0-9,]*\.?[0-9]{0,2})\s*(?:INR|Rs|Rs\.|₹)", text, re.IGNORECASE)
        if amt_match:
            try:
                amt_str = amt_match.group(1).replace(",", "")
                amount = float(amt_str)
            except Exception:
                amount = None

        # Date detection: dd-mm-yy or dd-mm-yyyy or dd/mm/yy
        date_str = None
        date_match = re.search(r"(\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b)", text)
        if date_match:
            raw = date_match.group(1)
            # normalize to YYYY-MM-DD
            for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d-%m-%y", "%d/%m/%y"):
                try:
                    dt = datetime.strptime(raw, fmt)
                    # two-digit years: assume 2000s
                    if dt.year < 100:
                        dt = dt.replace(year=dt.year + 2000)
                    date_str = dt.strftime("%Y-%m-%d")
                    break
                except Exception:
                    continue

        # Transaction type: debit/credited keywords
        trans_type = None
        if re.search(r"\bdebited\b|\bdebit\b|\bwithdrawn\b", text, re.IGNORECASE):
            trans_type = "expenditure"
        elif re.search(r"\bcredited\b|\bdeposit(ed)?\b|\brefund\b", text, re.IGNORECASE):
            trans_type = "income"

        # Source / bank name
        source = None
        bank_match = re.search(r"(HDFC Bank|State Bank of India|SBI|ICICI Bank|Axis Bank|Kotak|Punjab National Bank)", text, re.IGNORECASE)
        if bank_match:
            source = bank_match.group(1)

        # UPI / reference detection
        ref = None
        ref_match = re.search(r"reference (?:number )?(?:is )?:?\s*(\d{6,})", text, re.IGNORECASE)
        if not ref_match:
            ref_match = re.search(r"UPI transaction reference number is\s*(\d+)", text, re.IGNORECASE)
        if ref_match:
            ref = ref_match.group(1)

        # Account info
        acct_from = None
        acct_match = re.search(r"from account\s*(\d{2,}\d*)", text, re.IGNORECASE)
        if acct_match:
            acct_from = acct_match.group(1)
        else:
            acct_match = re.search(r"acct(?:ount)?[:#]?\s*(\d{2,}\d*)", text, re.IGNORECASE)
            if acct_match:
                acct_from = acct_match.group(1)

        # Category inference
        category = None
        if re.search(r"\bUPI\b|UPI transaction|UPI ref|upi", text, re.IGNORECASE):
            category = "UPI Transfer"
        elif re.search(r"transfer to|transferred to|debited from account .* to account", text, re.IGNORECASE):
            category = "Bank Transfer"
        elif re.search(r"bill|due date|payment due|bill amount|electricity|water|gas|bill", text, re.IGNORECASE):
            category = "Bills"
        else:
            category = "Other"

        if category and category not in self.PREDEFINED_CATEGORIES:
            # add dynamically for clarity
            self.PREDEFINED_CATEGORIES.append(category)

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
            result["transaction_type"] = trans_type or "expenditure"
            result["date"] = date_str or datetime.now().strftime("%Y-%m-%d")
            result["category"] = category or "Other"
            result["description"] = description
            result["source"] = source or ""
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
            if not self.use_genai:
                print("Error: Genai client not initialized. Check your API key.")
                return ""
            
            full_prompt = f"""{self._get_parsing_instruction()}

EMAIL TO PARSE:
{email_content}"""
            
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=full_prompt,
            )
            
            return response.text
        except Exception as e:
            print(f"Error querying model: {e}")
            return ""

    def parse_emails_batch(self, emails: List[tuple]) -> List[Transaction]:
        """
        Parse multiple emails in batch.

        Args:
            emails: List of tuples (subject, body)

        Returns:
            List of parsed Transaction objects
        """
        transactions = []
        for subject, body in emails:
            transaction = self.parse_email(subject, body)
            if transaction:
                transactions.append(transaction)
        return transactions

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
                source=data.get("source"),
                confidence=float(data.get("confidence", 1.0)),
                message_id=message_id,
            )

            return transaction
        except (ValueError, KeyError) as e:
            print(f"Error creating transaction: {e}")
            return None

    def add_category(self, category: str) -> None:
        """Add a new category to the predefined list"""
        if category not in self.PREDEFINED_CATEGORIES:
            self.PREDEFINED_CATEGORIES.append(category)

    def get_categories(self) -> List[str]:
        """Get list of available categories"""
        return self.PREDEFINED_CATEGORIES.copy()
