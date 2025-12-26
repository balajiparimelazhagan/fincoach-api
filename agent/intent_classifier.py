"""
Intent Classifier Agent for determining email intent.
Uses Google ADK Agent to classify emails as transactional, promotional, or informational.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import json

from google.adk.agents.llm_agent import Agent


class EmailIntent(str, Enum):
    """Email intent types"""
    TRANSACTION = "transaction"  # Email contains actual transaction information
    PROMOTIONAL = "promotional"  # Marketing, offers, promotions
    INFORMATIONAL = "informational"  # Account updates, statements, reminders
    UNKNOWN = "unknown"  # Unable to determine intent


@dataclass
class IntentClassification:
    """Result of intent classification"""
    intent: EmailIntent
    confidence: float  # 0.0 to 1.0
    reasoning: str  # Why this classification was made
    should_extract: bool  # Whether to proceed with transaction extraction
    
    def to_dict(self):
        return {
            "intent": self.intent.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "should_extract": self.should_extract,
        }


class IntentClassifierAgent:
    """Agent that classifies email intent before transaction extraction"""
    
    def __init__(self):
        """Initialize the intent classifier agent"""
        self.agent = Agent(
            model="gemini-2.5-flash",
            name="intent_classifier_agent",
            description="Classifies email intent to determine if it contains actual transaction information",
            instruction=self._get_system_instruction(),
        )
    
    def _get_system_instruction(self) -> str:
        """Get the system instruction for intent classification"""
        return """You are an expert email intent classifier for financial emails.

Your task is to determine the PRIMARY intent of a financial email. Analyze the email content and classify it into one of these categories:

1. TRANSACTION: Email contains information about an ACTUAL completed financial transaction
   - Examples: Payment successful, money debited, money credited, transfer complete, refunds, reversals
   - Keywords: "debited", "credited", "paid", "transferred", "transaction successful", "reversal", "refund", "cancelled"
   - Must have: Specific amount and transaction completion status
   - IMPORTANT: Refunds and reversals are TRANSACTIONS, not promotional offers

2. PROMOTIONAL: Email is marketing/promotional content
   - Examples: Offers, cashback promotions, discount vouchers, festive deals
   - Keywords: "offer", "cashback", "voucher", "discount", "sale", "limited time"
   - Focus: Encouraging future purchases or usage

3. INFORMATIONAL: Email provides account information but no completed transaction
   - Examples: Account statements, payment reminders, account updates, due dates
   - Keywords: "statement", "reminder", "due", "update", "summary"
   - Focus: Account status or scheduled/pending actions

4. UNKNOWN: Cannot determine intent with confidence

CRITICAL RULES:
- **Focus on EMAIL BODY content, not just subject line**
- If email mentions a COMPLETED transaction with amount, classify as TRANSACTION
- If email is offering deals/promotions even with amounts, classify as PROMOTIONAL
- Payment reminders or due dates are INFORMATIONAL, not TRANSACTION
- Account balance updates without transactions are INFORMATIONAL
- Be strict: When in doubt between TRANSACTION and PROMOTIONAL, choose PROMOTIONAL

Respond ONLY with valid JSON in this exact format:
{
    "intent": "<transaction|promotional|informational|unknown>",
    "confidence": <0.0-1.0>,
    "reasoning": "<brief explanation>",
    "should_extract": <true|false>
}

Set should_extract to true ONLY for TRANSACTION intent with confidence > 0.7"""

    def classify_email(self, subject: str, body: str) -> IntentClassification:
        """
        Classify the intent of an email
        
        Args:
            subject: Email subject line
            body: Email body content
            
        Returns:
            IntentClassification with the determined intent
        """
        # Prepare email content for analysis
        email_content = f"""Subject: {subject}

Body:
{body}"""
        
        try:
            # Query the agent for intent classification using Google Generative AI
            from google.genai import Client
            client = Client()
            
            prompt = f"""{self._get_system_instruction()}

EMAIL TO CLASSIFY:
{email_content}"""
            
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            response_text = response.text.strip()
            
            # Try to parse JSON response
            # Remove markdown code blocks if present
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            
            result = json.loads(response_text.strip())
            
            # Validate and create classification
            intent_str = result.get("intent", "unknown").lower()
            try:
                intent = EmailIntent(intent_str)
            except ValueError:
                intent = EmailIntent.UNKNOWN
            
            confidence = float(result.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))  # Clamp to [0, 1]
            
            reasoning = result.get("reasoning", "No reasoning provided")
            should_extract = bool(result.get("should_extract", False))
            
            # Override should_extract if intent is not TRANSACTION
            if intent != EmailIntent.TRANSACTION:
                should_extract = False
            
            # Override should_extract if confidence is too low
            if confidence < 0.7:
                should_extract = False
            
            return IntentClassification(
                intent=intent,
                confidence=confidence,
                reasoning=reasoning,
                should_extract=should_extract,
            )
            
        except json.JSONDecodeError as e:
            # Failed to parse JSON, return unknown intent
            return IntentClassification(
                intent=EmailIntent.UNKNOWN,
                confidence=0.0,
                reasoning=f"Failed to parse agent response: {str(e)}",
                should_extract=False,
            )
        except Exception as e:
            # Any other error, return unknown intent
            return IntentClassification(
                intent=EmailIntent.UNKNOWN,
                confidence=0.0,
                reasoning=f"Error during classification: {str(e)}",
                should_extract=False,
            )
