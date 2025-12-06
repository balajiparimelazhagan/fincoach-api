"""
Message Processing Coordinator using Agent-to-Agent Communication.
Orchestrates intent classification and transaction extraction for both emails and SMS using Google ADK agents.
"""

from dataclasses import dataclass
from typing import Optional, Union
from datetime import datetime
import logging

from .intent_classifier import IntentClassifierAgent, IntentClassification, EmailIntent
from .transaction_extractor import TransactionExtractorAgent, Transaction
from .sms_transaction_extractor import SmsTransactionExtractorAgent, SmsTransaction

logger = logging.getLogger(__name__)


@dataclass
class EmailProcessingResult:
    """Result of email processing with A2A coordination"""
    intent_classification: IntentClassification
    transaction: Optional[Transaction]
    processed: bool
    skip_reason: Optional[str] = None
    
    def to_dict(self):
        result = {
            "intent": self.intent_classification.to_dict(),
            "processed": self.processed,
        }
        if self.transaction:
            result["transaction"] = self.transaction.to_dict()
        if self.skip_reason:
            result["skip_reason"] = self.skip_reason
        return result


@dataclass
class SmsProcessingResult:
    """Result of SMS processing with A2A coordination"""
    intent_classification: IntentClassification
    transaction: Optional[SmsTransaction]
    processed: bool
    skip_reason: Optional[str] = None
    
    def to_dict(self):
        result = {
            "intent": self.intent_classification.to_dict(),
            "processed": self.processed,
        }
        if self.transaction:
            result["transaction"] = self.transaction.to_dict()
        if self.skip_reason:
            result["skip_reason"] = self.skip_reason
        return result


class EmailProcessingCoordinator:
    """
    Coordinator that implements Agent-to-Agent (A2A) communication pattern for emails.
    
    Architecture:
    1. Intent Classifier Agent (first layer) - Determines email intent
    2. Transaction Extractor Agent (second layer) - Extracts transaction data
    
    Communication Flow:
    Intent Classifier -> Decision Logic -> Transaction Extractor
    
    This pattern ensures:
    - Promotional emails are filtered out before extraction
    - Only high-confidence transactional emails are processed
    - Clear separation of concerns between agents
    - Efficient processing with early rejection
    """
    
    def __init__(self):
        """Initialize the coordinator with both agents"""
        logger.info("Initializing Email Processing Coordinator with A2A communication")
        self.intent_classifier = IntentClassifierAgent()
        self.transaction_extractor = TransactionExtractorAgent()
        logger.info("Both agents initialized successfully")
    
    def process_email(
        self,
        message_id: str,
        subject: str,
        body: str,
    ) -> EmailProcessingResult:
        """
        Process email using A2A coordination pattern
        
        Step 1: Intent Classification (Agent 1)
        Step 2: Decision Logic (Coordinator)
        Step 3: Transaction Extraction (Agent 2) - only if approved
        
        Args:
            message_id: Unique email message ID
            subject: Email subject line
            body: Email body content
            
        Returns:
            EmailProcessingResult with classification and optional transaction
        """
        logger.info(f"[A2A] Processing email {message_id}")
        
        # STEP 1: Agent 1 - Intent Classification
        logger.info(f"[A2A] Step 1: Invoking Intent Classifier Agent")
        intent_classification = self.intent_classifier.classify_email(subject, body)
        
        logger.info(
            f"[A2A] Intent Classification: {intent_classification.intent.value} "
            f"(confidence: {intent_classification.confidence:.2f})"
        )
        logger.info(f"[A2A] Reasoning: {intent_classification.reasoning}")
        
        # STEP 2: Coordinator Decision Logic
        if not intent_classification.should_extract:
            skip_reason = self._get_skip_reason(intent_classification)
            logger.info(f"[A2A] Step 2: Skipping extraction - {skip_reason}")
            
            return EmailProcessingResult(
                intent_classification=intent_classification,
                transaction=None,
                processed=False,
                skip_reason=skip_reason,
            )
        
        # STEP 3: Agent 2 - Transaction Extraction
        logger.info(f"[A2A] Step 2: Approved for extraction, invoking Transaction Extractor Agent")
        
        try:
            transaction = self.transaction_extractor.parse_email(message_id, subject, body)
            
            if transaction:
                logger.info(
                    f"[A2A] Step 3: Successfully extracted transaction: "
                    f"{transaction.amount} {transaction.transaction_type}"
                )
                return EmailProcessingResult(
                    intent_classification=intent_classification,
                    transaction=transaction,
                    processed=True,
                )
            else:
                logger.warning(f"[A2A] Step 3: Transaction Extractor returned None")
                return EmailProcessingResult(
                    intent_classification=intent_classification,
                    transaction=None,
                    processed=False,
                    skip_reason="Transaction extraction failed",
                )
                
        except Exception as e:
            logger.error(f"[A2A] Step 3: Transaction extraction error: {str(e)}", exc_info=True)
            return EmailProcessingResult(
                intent_classification=intent_classification,
                transaction=None,
                processed=False,
                skip_reason=f"Extraction error: {str(e)}",
            )
    
    def _get_skip_reason(self, classification: IntentClassification) -> str:
        """Generate human-readable skip reason"""
        if classification.intent == EmailIntent.PROMOTIONAL:
            return f"Email is promotional/marketing content: {classification.reasoning}"
        elif classification.intent == EmailIntent.INFORMATIONAL:
            return f"Email is informational (no transaction): {classification.reasoning}"
        elif classification.intent == EmailIntent.UNKNOWN:
            return f"Unable to determine intent: {classification.reasoning}"
        elif classification.confidence < 0.7:
            return f"Low confidence ({classification.confidence:.2f}): {classification.reasoning}"
        else:
            return f"Should not extract: {classification.reasoning}"
    
    def classify_intent_only(self, subject: str, body: str) -> IntentClassification:
        """
        Only classify intent without extraction (for testing/analysis)
        
        Args:
            subject: Email subject line
            body: Email body content
            
        Returns:
            IntentClassification result
        """
        return self.intent_classifier.classify_email(subject, body)


class SmsProcessingCoordinator:
    """
    Coordinator that implements Agent-to-Agent (A2A) communication pattern for SMS.
    
    Architecture:
    1. Intent Classifier Agent (first layer) - Determines SMS intent
    2. SMS Transaction Extractor Agent (second layer) - Extracts transaction data
    
    Communication Flow:
    Intent Classifier -> Decision Logic -> SMS Transaction Extractor
    
    This pattern ensures:
    - Promotional SMS are filtered out before extraction
    - Only high-confidence transactional SMS are processed
    - Clear separation of concerns between agents
    - Efficient processing with early rejection
    """
    
    def __init__(self):
        """Initialize the coordinator with both agents"""
        logger.info("Initializing SMS Processing Coordinator with A2A communication")
        self.intent_classifier = IntentClassifierAgent()
        self.sms_extractor = SmsTransactionExtractorAgent()
        logger.info("Both agents initialized successfully")
    
    def process_sms(
        self,
        sms_id: str,
        sms_body: str,
        sender: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> SmsProcessingResult:
        """
        Process SMS using A2A coordination pattern
        
        Step 1: Intent Classification (Agent 1)
        Step 2: Decision Logic (Coordinator)
        Step 3: Transaction Extraction (Agent 2) - only if approved
        
        Args:
            sms_id: Unique SMS identifier
            sms_body: SMS message body
            sender: SMS sender (e.g., bank short code)
            timestamp: SMS received timestamp
            
        Returns:
            SmsProcessingResult with classification and optional transaction
        """
        logger.info(f"[A2A-SMS] Processing SMS {sms_id}")
        
        # STEP 1: Agent 1 - Intent Classification
        # For SMS, we use "SMS" as subject and body is the message
        logger.info(f"[A2A-SMS] Step 1: Invoking Intent Classifier Agent")
        intent_classification = self.intent_classifier.classify_email(
            subject=f"SMS from {sender or 'Unknown'}", 
            body=sms_body
        )
        
        logger.info(
            f"[A2A-SMS] Intent Classification: {intent_classification.intent.value} "
            f"(confidence: {intent_classification.confidence:.2f})"
        )
        logger.info(f"[A2A-SMS] Reasoning: {intent_classification.reasoning}")
        
        # STEP 2: Coordinator Decision Logic
        if not intent_classification.should_extract:
            skip_reason = self._get_skip_reason(intent_classification)
            logger.info(f"[A2A-SMS] Step 2: Skipping extraction - {skip_reason}")
            
            return SmsProcessingResult(
                intent_classification=intent_classification,
                transaction=None,
                processed=False,
                skip_reason=skip_reason,
            )
        
        # STEP 3: Agent 2 - SMS Transaction Extraction
        logger.info(f"[A2A-SMS] Step 2: Approved for extraction, invoking SMS Transaction Extractor Agent")
        
        try:
            transaction = self.sms_extractor.parse_sms(
                sms_id=sms_id,
                sms_body=sms_body,
                sender=sender,
                timestamp=timestamp
            )
            
            if transaction:
                logger.info(
                    f"[A2A-SMS] Step 3: Successfully extracted transaction: "
                    f"{transaction.amount} {transaction.transaction_type}"
                )
                return SmsProcessingResult(
                    intent_classification=intent_classification,
                    transaction=transaction,
                    processed=True,
                )
            else:
                logger.warning(f"[A2A-SMS] Step 3: SMS Transaction Extractor returned None")
                return SmsProcessingResult(
                    intent_classification=intent_classification,
                    transaction=None,
                    processed=False,
                    skip_reason="Transaction extraction failed",
                )
                
        except Exception as e:
            logger.error(f"[A2A-SMS] Step 3: Transaction extraction error: {str(e)}", exc_info=True)
            return SmsProcessingResult(
                intent_classification=intent_classification,
                transaction=None,
                processed=False,
                skip_reason=f"Extraction error: {str(e)}",
            )
    
    def _get_skip_reason(self, classification: IntentClassification) -> str:
        """Generate human-readable skip reason"""
        if classification.intent == EmailIntent.PROMOTIONAL:
            return f"SMS is promotional/marketing content: {classification.reasoning}"
        elif classification.intent == EmailIntent.INFORMATIONAL:
            return f"SMS is informational (no transaction): {classification.reasoning}"
        elif classification.intent == EmailIntent.UNKNOWN:
            return f"Unable to determine intent: {classification.reasoning}"
        elif classification.confidence < 0.7:
            return f"Low confidence ({classification.confidence:.2f}): {classification.reasoning}"
        else:
            return f"Should not extract: {classification.reasoning}"
    
    def classify_intent_only(self, sms_body: str, sender: Optional[str] = None) -> IntentClassification:
        """
        Only classify intent without extraction (for testing/analysis)
        
        Args:
            sms_body: SMS message body
            sender: SMS sender
            
        Returns:
            IntentClassification result
        """
        return self.intent_classifier.classify_email(
            subject=f"SMS from {sender or 'Unknown'}", 
            body=sms_body
        )
