"""add description to categories

Revision ID: 029
Revises: 028
Create Date: 2026-01-13 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '029'
down_revision: Union[str, None] = '028'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add description column to categories table and populate with category guidelines"""
    
    # Add description column
    op.add_column('categories', sa.Column('description', sa.Text(), nullable=True))
    
    # Update descriptions for each category
    category_descriptions = {
        'Housing': 'rent, mortgage, property tax, maintenance',
        'Utilities': 'electricity, water, gas, internet bills',
        'Food': 'groceries, restaurants, food delivery',
        'Transport': 'fuel, taxi, public transport',
        'Shopping': 'retail, online shopping, clothing',
        'Subscriptions': 'Netflix, Spotify, recurring services',
        'Health': 'hospital, medicine, gym, fitness',
        'Entertainment': 'movies, games, sports events',
        'Travel': 'flights, hotels, vacation',
        'Personal Care': 'salon, spa, grooming',
        'Education': 'school, courses, books',
        'Family & Relationships': 'gifts, celebrations',
        'Income': 'salary, freelance, refunds',
        'Savings': 'deposits, FD, mutual funds, SIP, stocks, investments',
        'Loans & EMIs': 'loan payments, credit card',
        'Transfers': 'UPI, NEFT, bank transfers',
        'Fees & Charges': 'bank fees, penalties',
        'Taxes': 'income tax, GST',
        'Donations': 'charity, religious donations',
        'Miscellaneous': "anything that doesn't fit above",
    }
    
    # Get connection for parameterized queries
    connection = op.get_bind()
    
    for category, description in category_descriptions.items():
        connection.execute(
            sa.text("UPDATE categories SET description = :desc WHERE label = :cat"),
            {"desc": description, "cat": category}
        )


def downgrade() -> None:
    """Remove description column from categories table"""
    op.drop_column('categories', 'description')
