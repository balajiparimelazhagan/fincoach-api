"""
Transaction serialization utilities.
"""
from typing import Dict, Any, Optional

from app.models.transaction import Transaction


def serialize_transaction(transaction: Transaction) -> Dict[str, Any]:
    """
    Serialize a Transaction model to a dictionary for API responses.
    
    Args:
        transaction: Transaction model instance with loaded relationships
        
    Returns:
        Dictionary representation of the transaction
    """
    return {
        "id": transaction.id,
        "amount": int(transaction.amount) if transaction.amount is not None else None,
        "transaction_id": transaction.transaction_id,
        "type": transaction.type,
        "date": transaction.date.isoformat() if transaction.date else None,
        "transactor_id": transaction.transactor_id,
        "transactor": _serialize_transactor(transaction.transactor) if transaction.transactor else None,
        "category_id": transaction.category_id,
        "category": _serialize_category(transaction.category) if transaction.category else None,
        "description": transaction.description,
        "confidence": transaction.confidence,
        "currency_id": transaction.currency_id,
        "user_id": transaction.user_id,
        "message_id": transaction.message_id,
        "account_id": transaction.account_id,
        "account": _serialize_account(transaction.account) if transaction.account else None,
    }


def _serialize_transactor(transactor) -> Dict[str, Any]:
    """Serialize transactor information."""
    return {
        "id": transactor.id,
        "name": transactor.name,
        "picture": transactor.picture,
        "label": transactor.label,
        "source_id": getattr(transactor, 'source_id', None),
    }


def _serialize_category(category) -> Dict[str, Any]:
    """Serialize category information."""
    return {
        "id": category.id,
        "label": category.label,
        "picture": category.picture,
    }


def _serialize_account(account) -> Dict[str, Any]:
    """Serialize account information."""
    return {
        "id": account.id,
        "account_last_four": account.account_last_four,
        "bank_name": account.bank_name,
        "type": account.type.value,
    }
