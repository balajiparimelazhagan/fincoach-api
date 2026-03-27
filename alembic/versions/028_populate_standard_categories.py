"""populate standard categories

Revision ID: 028
Revises: 027
Create Date: 2026-01-13 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '028'
down_revision: Union[str, None] = '027'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Populate the categories table with standard categories"""

    # Fixed UUIDs kept in-sync with synthetic_data_builder.py CATEGORIES map.
    # Using fixed UUIDs means the seeder's ON CONFLICT (id) DO NOTHING prevents
    # duplicate rows when docker down -v + docker up causes both this migration
    # and the seeder to run against a fresh database.
    op.execute("""
        INSERT INTO categories (id, label, picture) VALUES
            ('b600dc65-ead3-4437-b898-50b05c63e93b', 'Housing',              'home-outline'),
            ('115953d1-34f7-41bb-afb8-8bbaf0388e24', 'Utilities',            'flash-outline'),
            ('2698e700-68b0-46ea-a812-f81547603d7e', 'Food',                 'fast-food-outline'),
            ('a0250e9f-99d5-44c3-933b-e23d4383fc57', 'Transport',            'car-outline'),
            ('e3b221b0-6ae0-4595-8f0e-2a512830834c', 'Shopping',             'cart-outline'),
            ('c3088928-1790-42f3-9338-b1bf58233166', 'Subscriptions',        'sync-circle-outline'),
            ('1c4fcdf9-f021-4776-a3c8-98e370abcfe0', 'Health',               'fitness-outline'),
            ('05174f56-9cae-49f9-a7b0-d215dd59e6ed', 'Entertainment',        'flower-outline'),
            ('2bcd61e5-f4e4-478d-9e85-9b4d73493545', 'Travel',               'airplane-outline'),
            ('f5ca67b9-d0cb-4d94-8c27-3bcaf6ebf313', 'Personal Care',        'person-outline'),
            ('6d7be686-7e95-4c23-98ff-5ffcc9eda78d', 'Education',            'school-outline'),
            ('cca72189-04e4-44a7-8cb7-3d3309643c62', 'Family','people-outline'),
            ('1f1cd1ad-0a98-46fe-bb92-2fded8ad35b5', 'Income',               'wallet-outline'),
            ('5a24168b-ad2e-4442-b17d-92ad45888138', 'Savings',              'archive-outline'),
            ('dddf8adb-9e78-4be2-a81e-2c9d6c713d91', 'Loans & EMIs',         'card-outline'),
            ('3759b79b-47f1-4a6b-92e7-5812027f6a19', 'Transfers',            'swap-horizontal-outline'),
            ('0c6c2036-78d1-4f7a-b2e8-f8e92a72c90d', 'Fees & Charges',       'receipt-outline'),
            ('f04d6902-8779-4080-9978-885d6b330fcc', 'Taxes',                'document-text-outline'),
            ('53dc38ac-e49b-4880-883e-ebf3402b4a81', 'Donations',            'heart-outline'),
            ('febae2ab-9e5f-4f94-bae5-e6013ac65432', 'Miscellaneous',        'ellipsis-horizontal-circle-outline')
        ON CONFLICT (id) DO NOTHING
    """)


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
