"""populate standard categories

Revision ID: 028
Revises: 027
Create Date: 2026-01-13 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
from sqlalchemy.dialects import postgresql
import uuid

# revision identifiers, used by Alembic.
revision: str = '028'
down_revision: Union[str, None] = '027'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Populate the categories table with standard categories"""
    
    # Define the categories table structure for bulk insert
    categories_table = table('categories',
        column('id', postgresql.UUID),
        column('label', sa.String),
        column('picture', sa.String)
    )
    
    # Standard categories with icons
    categories = [
        # Expense Categories
        {'id': str(uuid.uuid4()), 'label': 'Housing', 'picture': 'home-outline'},
        {'id': str(uuid.uuid4()), 'label': 'Utilities', 'picture': 'flash-outline'},
        {'id': str(uuid.uuid4()), 'label': 'Food', 'picture': 'fast-food-outline'},
        {'id': str(uuid.uuid4()), 'label': 'Transport', 'picture': 'car-outline'},
        {'id': str(uuid.uuid4()), 'label': 'Shopping', 'picture': 'cart-outline'},
        {'id': str(uuid.uuid4()), 'label': 'Subscriptions', 'picture': 'sync-circle-outline'},
        {'id': str(uuid.uuid4()), 'label': 'Health', 'picture': 'fitness-outline'},
        {'id': str(uuid.uuid4()), 'label': 'Entertainment', 'picture': 'flower-outline'},
        {'id': str(uuid.uuid4()), 'label': 'Travel', 'picture': 'airplane-outline'},
        {'id': str(uuid.uuid4()), 'label': 'Personal Care', 'picture': 'person-outline'},
        {'id': str(uuid.uuid4()), 'label': 'Education', 'picture': 'school-outline'},
        {'id': str(uuid.uuid4()), 'label': 'Family & Relationships', 'picture': 'people-outline'},
        
        # Income & Financial Categories
        {'id': str(uuid.uuid4()), 'label': 'Income', 'picture': 'wallet-outline'},
        {'id': str(uuid.uuid4()), 'label': 'Savings', 'picture': 'archive-outline'},
        {'id': str(uuid.uuid4()), 'label': 'Loans & EMIs', 'picture': 'card-outline'},
        {'id': str(uuid.uuid4()), 'label': 'Transfers', 'picture': 'swap-horizontal-outline'},
        
        # Other Categories
        {'id': str(uuid.uuid4()), 'label': 'Fees & Charges', 'picture': 'receipt-outline'},
        {'id': str(uuid.uuid4()), 'label': 'Taxes', 'picture': 'document-text-outline'},
        {'id': str(uuid.uuid4()), 'label': 'Donations', 'picture': 'heart-outline'},
        {'id': str(uuid.uuid4()), 'label': 'Miscellaneous', 'picture': 'ellipsis-horizontal-circle-outline'},
    ]
    
    # Insert all categories
    op.bulk_insert(categories_table, categories)


def downgrade() -> None:
    """Remove the standard categories"""
    op.execute("""
        DELETE FROM categories 
        WHERE label IN (
            'Housing', 'Utilities', 'Food', 'Transport', 'Shopping', 
            'Subscriptions', 'Health', 'Entertainment', 'Travel', 
            'Personal Care', 'Education', 'Family & Relationships',
            'Income', 'Savings', 'Loans & EMIs', 'Transfers',
            'Fees & Charges', 'Taxes', 'Donations', 'Miscellaneous'
        )
    """)
