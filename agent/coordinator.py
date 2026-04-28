"""
Message Processing Coordinator.
Orchestrates transaction extraction for both emails and SMS.
Intent detection is handled internally by each extractor.
"""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime
import logging

from .intent_classifier import IntentClassification
from .transaction_extractor import TransactionExtractorAgent, Transaction
from .sms_transaction_extractor import SmsTransactionExtractorAgent, SmsTransaction

logger = logging.getLogger(__name__)


@dataclass
class EmailProcessingResult:
    """Result of email processing"""
    transaction: Optional[Transaction]
    processed: bool
    skip_reason: Optional[str] = None
    intent_classification: Optional[IntentClassification] = None

    def to_dict(self):
        result = {"processed": self.processed}
        if self.intent_classification:
            result["intent"] = self.intent_classification.to_dict()
        if self.transaction:
            result["transaction"] = self.transaction.to_dict()
        if self.skip_reason:
            result["skip_reason"] = self.skip_reason
        return result


@dataclass
class SmsProcessingResult:
    """Result of SMS processing"""
    transaction: Optional[SmsTransaction]
    processed: bool
    skip_reason: Optional[str] = None
    intent_classification: Optional[IntentClassification] = None

    def to_dict(self):
        result = {"processed": self.processed}
        if self.intent_classification:
            result["intent"] = self.intent_classification.to_dict()
        if self.transaction:
            result["transaction"] = self.transaction.to_dict()
        if self.skip_reason:
            result["skip_reason"] = self.skip_reason
        return result


class EmailProcessingCoordinator:
    """
    Coordinator for email processing.

    The transaction extractor handles intent detection internally — if the email
    is promotional, informational, or not a completed transaction, the extractor
    returns None and the coordinator marks it as skipped.
    """

    def __init__(self):
        logger.info("Initializing Email Processing Coordinator")
        self.transaction_extractor = TransactionExtractorAgent()
        logger.info("Email Processing Coordinator initialized")

    def process_email(
        self,
        message_id: str,
        subject: str,
        body: str,
        sender_email: Optional[str] = None,
        email_date: Optional[datetime] = None,
    ) -> EmailProcessingResult:
        """
        Process an email and extract transaction data if present.

        Args:
            message_id: Unique email message ID
            subject: Email subject line
            body: Email body content
            sender_email: Optional sender email for account extraction

        Returns:
            EmailProcessingResult with transaction and processing status
        """
        logger.info(f"Processing email {message_id}")

        try:
            transaction = self.transaction_extractor.parse_email(
                message_id, subject, body, sender_email
            )

            if transaction:
                logger.info(
                    f"Extracted transaction: {transaction.amount} {transaction.transaction_type}"
                )
                if transaction.bank_name or transaction.account_last_four:
                    logger.info(
                        f"Account info: {transaction.bank_name or 'Unknown'} "
                        f"- {transaction.account_last_four or 'N/A'}"
                    )
                return EmailProcessingResult(
                    transaction=transaction,
                    processed=True,
                )
            else:
                logger.info(f"Skipped email {message_id}: not a transaction or extraction returned None")
                return EmailProcessingResult(
                    transaction=None,
                    processed=False,
                    skip_reason="Not a transaction email",
                )

        except Exception as e:
            logger.error(f"Error processing email {message_id}: {str(e)}", exc_info=True)
            return EmailProcessingResult(
                transaction=None,
                processed=False,
                skip_reason=f"Extraction error: {str(e)}",
            )


class SmsProcessingCoordinator:
    """
    Coordinator for SMS processing.

    The SMS transaction extractor handles intent detection internally — if the SMS
    is promotional, an OTP, or not a completed transaction, the extractor returns
    None and the coordinator marks it as skipped.
    """

    def __init__(self):
        logger.info("Initializing SMS Processing Coordinator")
        self.sms_extractor = SmsTransactionExtractorAgent()
        logger.info("SMS Processing Coordinator initialized")

    def process_sms(
        self,
        sms_id: str,
        sms_body: str,
        sender: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> SmsProcessingResult:
        """
        Process an SMS and extract transaction data if present.

        Args:
            sms_id: Unique SMS identifier
            sms_body: SMS message body
            sender: SMS sender (e.g., bank short code)
            timestamp: SMS received timestamp

        Returns:
            SmsProcessingResult with transaction and processing status
        """
        logger.info(f"Processing SMS {sms_id}")

        try:
            transaction = self.sms_extractor.parse_sms(
                sms_id=sms_id,
                sms_body=sms_body,
                sender=sender,
                timestamp=timestamp,
            )

            if transaction:
                logger.info(
                    f"Extracted transaction: {transaction.amount} {transaction.transaction_type}"
                )
                if transaction.bank_name or transaction.account_last_four:
                    logger.info(
                        f"Account info: {transaction.bank_name or 'Unknown'} "
                        f"- {transaction.account_last_four or 'N/A'}"
                    )
                return SmsProcessingResult(
                    transaction=transaction,
                    processed=True,
                )
            else:
                logger.info(f"Skipped SMS {sms_id}: not a transaction or extraction returned None")
                return SmsProcessingResult(
                    transaction=None,
                    processed=False,
                    skip_reason="Not a transaction SMS",
                )

        except Exception as e:
            logger.error(f"Error processing SMS {sms_id}: {str(e)}", exc_info=True)
            return SmsProcessingResult(
                transaction=None,
                processed=False,
                skip_reason=f"Extraction error: {str(e)}",
            )
