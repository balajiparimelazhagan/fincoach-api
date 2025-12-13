"""
Account Extractor Agent for extracting bank account information from transaction messages.
Extracts bank name and account last 4 digits using Google ADK Agent with regex fallback.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Tuple
import json
import re
import logging

from dotenv import load_dotenv
from google.adk.agents.llm_agent import Agent

from .regex_constants import ACCOUNT_PATTERN, ALT_ACCOUNT_PATTERN

load_dotenv()

logger = logging.getLogger(__name__)

# Common Indian bank names and their variations for regex fallback
BANK_PATTERNS = {
    "HDFC Bank": [r"HDFC\s*Bank", r"HDFC", r"hdfcbank"],
    "ICICI Bank": [r"ICICI\s*Bank", r"ICICI", r"icicibank"],
    "State Bank of India": [r"State\s*Bank\s*of\s*India", r"SBI", r"onlinesbi"],
    "Axis Bank": [r"Axis\s*Bank", r"Axis", r"axisbank"],
    "Kotak Mahindra Bank": [r"Kotak\s*Mahindra\s*Bank", r"Kotak", r"kotak"],
    "Punjab National Bank": [r"Punjab\s*National\s*Bank", r"PNB", r"pnb"],
    "Bank of Baroda": [r"Bank\s*of\s*Baroda", r"BOB", r"bankofbaroda"],
    "Canara Bank": [r"Canara\s*Bank", r"Canara", r"canarabank"],
    "IndusInd Bank": [r"IndusInd\s*Bank", r"IndusInd", r"indusind"],
    "Yes Bank": [r"Yes\s*Bank", r"YesBank", r"yesbank"],
    "IDFC First Bank": [r"IDFC\s*First\s*Bank", r"IDFC\s*Bank", r"IDFC", r"idfcfirstbank"],
    "Federal Bank": [r"Federal\s*Bank", r"Federal", r"federalbank"],
    "Union Bank of India": [r"Union\s*Bank\s*of\s*India", r"Union\s*Bank", r"unionbankofindia"],
    "Bank of India": [r"Bank\s*of\s*India", r"BOI", r"bankofindia"],
    "Central Bank of India": [r"Central\s*Bank\s*of\s*India", r"Central\s*Bank", r"centralbankofindia"],
    "Indian Bank": [r"Indian\s*Bank", r"indianbank"],
    "Indian Overseas Bank": [r"Indian\s*Overseas\s*Bank", r"IOB", r"iob"],
    "UCO Bank": [r"UCO\s*Bank", r"UCO", r"ucobank"],
    "Bank of Maharashtra": [r"Bank\s*of\s*Maharashtra", r"bankofmaharashtra"],
    "Standard Chartered Bank": [r"Standard\s*Chartered\s*Bank", r"Standard\s*Chartered", r"SC\s*Bank", r"standardchartered"],
    "Citibank": [r"Citibank", r"Citi\s*Bank", r"Citi"],
    "HSBC": [r"HSBC", r"Hongkong\s*and\s*Shanghai\s*Banking\s*Corporation"],
    "Deutsche Bank": [r"Deutsche\s*Bank", r"Deutsche"],
    "RBL Bank": [r"RBL\s*Bank", r"RBL", r"rblbank"],
    "South Indian Bank": [r"South\s*Indian\s*Bank", r"southindianbank"],
    "Karnataka Bank": [r"Karnataka\s*Bank", r"karnatakabank"],
    "Karur Vysya Bank": [r"Karur\s*Vysya\s*Bank", r"KVB", r"kvb"],
    "Bandhan Bank": [r"Bandhan\s*Bank", r"Bandhan", r"bandhanbank"],
    "IDBI Bank": [r"IDBI\s*Bank", r"IDBI", r"idbibank"],
    "Paytm Payments Bank": [r"Paytm\s*Payments\s*Bank", r"Paytm", r"paytmbank"],
}

# Patterns to extract account numbers (last 4 digits)
ACCOUNT_NUMBER_PATTERNS = [
    r"account\s+(?:\*+)?(\d{4})",  # "account 4319" or "account ***4319"
    r"a/c\s+(?:\*+)?(\d{4})",      # "a/c 4319" or "a/c ***4319"
    r"ac\s+(?:\*+)?(\d{4})",       # "ac 4319" or "ac ***4319"
    r"(?:\*+)(\d{4})",             # "***4319" (standalone with context)
    r"xx+(\d{4})",                 # "xxxx4319" or "XX4319"
    r"card\s+(?:ending\s+)?(?:\*+)?(\d{4})",  # "card 4319" or "card ending 4319"
]


@dataclass
class AccountInfo:
    """Data class representing extracted account information"""
    bank_name: Optional[str] = None
    account_last_four: Optional[str] = None
    confidence: float = 1.0
    
    def to_dict(self):
        """Convert account info to dictionary"""
        return {
            "bank_name": self.bank_name,
            "account_last_four": self.account_last_four,
            "confidence": self.confidence,
        }


class AccountExtractorAgent:
    """Account Extractor Agent using Google ADK with regex fallback"""

    def __init__(self):
        """Initialize the account extractor agent"""
        self._system_message = self._get_system_message()
        
        try:
            self.agent = Agent(
                model="gemini-2.5-flash",
                name="account_extractor_agent",
                description="Extracts bank account information from transaction messages",
                instruction=self._system_message,
            )
            logger.info("Account Extractor Agent initialized with LLM model")
        except Exception as e:
            logger.warning(f"Failed to initialize LLM agent, will use regex fallback: {e}")
            self.agent = None

    def _get_system_message(self) -> str:
        """Create the system instruction for account extraction."""
        return """You are an expert at extracting bank account information from financial transaction messages (emails and SMS).

Your task is to extract:
1. Bank Name - The full name of the bank (e.g., "HDFC Bank", "ICICI Bank", "State Bank of India")
2. Account Last Four Digits - The last 4 digits of the account or card number

Common patterns you'll see:
- "account 4319" or "account ***4319"
- "a/c XX4319" or "A/c **7890"
- "card ending 5678" or "card xxxx5678"
- Bank names in text: "HDFC Bank", "SBI", "Axis Bank"
- Bank names in sender: "alerts@hdfcbank.com", "HDFCBK"

Always return the response as a valid JSON object with these exact fields:
{
    "bank_name": "<full bank name or null>",
    "account_last_four": "<4 digits or null>"
}

Examples:

1. Input: "Dear Customer, Rs.293.00 has been debited from account 4319 ... HDFC Bank"
   Output: {"bank_name": "HDFC Bank", "account_last_four": "4319"}

2. Input: "Your account ***4319 has been debited with Rs.500.00"
   Sender: "alerts@icicibank.com"
   Output: {"bank_name": "ICICI Bank", "account_last_four": "4319"}

3. Input: "INR 1500.00 debited from a/c **7890 on 12-Dec-25. -State Bank of India"
   Output: {"bank_name": "State Bank of India", "account_last_four": "7890"}

4. Input: "Rs 750 spent on card ending xxxx5678 at Amazon. -Axis Bank"
   Output: {"bank_name": "Axis Bank", "account_last_four": "5678"}

Guidelines:
- Extract the FULL official bank name when possible (e.g., "HDFC Bank" not "HDFC")
- Account last four should be exactly 4 digits
- If bank name is not found in message text, check sender information
- If information is missing, return null for that field
- Be precise and extract only what's clearly present in the message"""

    def extract_account_info(
        self,
        message_text: str,
        sender_email: Optional[str] = None,
        sender_sms: Optional[str] = None
    ) -> AccountInfo:
        """
        Extract bank account information from message text.

        Args:
            message_text: Email body or SMS text
            sender_email: Optional sender email address
            sender_sms: Optional SMS sender short code

        Returns:
            AccountInfo object with extracted bank name and account last 4 digits
        """
        try:
            # First try the LLM model if available
            if self.agent:
                response = self._query_model(message_text, sender_email, sender_sms)
                account_data = self._extract_json_from_response(response)
                
                if account_data and (account_data.get("bank_name") or account_data.get("account_last_four")):
                    return AccountInfo(
                        bank_name=account_data.get("bank_name"),
                        account_last_four=account_data.get("account_last_four"),
                        confidence=0.95  # High confidence for LLM extraction
                    )
            
            # Fall back to regex parsing
            logger.info("Using regex fallback for account extraction")
            return self._extract_with_regex(message_text, sender_email, sender_sms)
            
        except Exception as e:
            logger.error(f"Error extracting account info: {e}", exc_info=True)
            # Return empty account info on error
            return AccountInfo(confidence=0.0)

    def _query_model(
        self,
        message_text: str,
        sender_email: Optional[str] = None,
        sender_sms: Optional[str] = None
    ) -> str:
        """Query the LLM model for account extraction"""
        try:
            from google.genai import Client
            client = Client()
            
            # Prepare context with all available information
            context = f"Message: {message_text}"
            
            if sender_email:
                context += f"\nSender Email: {sender_email}"
            
            if sender_sms:
                context += f"\nSMS Sender: {sender_sms}"
            
            # Query the model directly
            prompt = f"""{self._system_message}
                
                TRANSACTION MESSAGE TO ANALYZE:
                {context}"""
            
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            
            return response.text
        except Exception as e:
            logger.warning(f"Model query error: {e}")
            return ""

    def _extract_json_from_response(self, response: str) -> Optional[Dict]:
        """Extract JSON from LLM response"""
        try:
            # Try to find JSON in the response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                data = json.loads(json_str)
                # Validate the structure
                if isinstance(data, dict):
                    return data
        except json.JSONDecodeError as e:
            logger.debug(f"JSON decode error: {e}")
        except Exception as e:
            logger.debug(f"Error extracting JSON: {e}")
        return None

    def _extract_with_regex(
        self,
        message_text: str,
        sender_email: Optional[str] = None,
        sender_sms: Optional[str] = None
    ) -> AccountInfo:
        """Fallback extraction using regex patterns"""
        bank_name = self._extract_bank_name(message_text, sender_email, sender_sms)
        account_last_four = self._extract_account_last_four(message_text)
        
        # Lower confidence for regex-based extraction
        confidence = 0.7 if (bank_name or account_last_four) else 0.0
        
        return AccountInfo(
            bank_name=bank_name,
            account_last_four=account_last_four,
            confidence=confidence
        )

    def _extract_bank_name(
        self,
        text: str,
        sender_email: Optional[str] = None,
        sender_sms: Optional[str] = None
    ) -> Optional[str]:
        """Extract bank name from text and sender information"""
        if not text:
            return None
        
        text_lower = text.lower()
        
        # Try to match bank patterns in message text
        for bank_name, patterns in BANK_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    return bank_name
        
        # Try sender email
        if sender_email:
            sender_lower = sender_email.lower()
            for bank_name, patterns in BANK_PATTERNS.items():
                for pattern in patterns:
                    if re.search(pattern, sender_lower, re.IGNORECASE):
                        return bank_name
        
        # Try SMS sender
        if sender_sms:
            sender_lower = sender_sms.lower()
            for bank_name, patterns in BANK_PATTERNS.items():
                for pattern in patterns:
                    if re.search(pattern, sender_lower, re.IGNORECASE):
                        return bank_name
        
        return None

    def _extract_account_last_four(self, text: str) -> Optional[str]:
        """Extract last 4 digits of account number from text"""
        if not text:
            return None
        
        # Try each pattern
        for pattern in ACCOUNT_NUMBER_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # Get the captured digits
                last_four = match.group(1)
                # Validate it's exactly 4 digits
                if len(last_four) == 4 and last_four.isdigit():
                    return last_four
        
        return None
