"""populate currencies table

Revision ID: 004
Revises: 003
Create Date: 2025-01-27 00:00:00.000000

"""
from typing import Sequence, Union
import httpx
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def fetch_currencies_data():
    """
    Fetch countries and currencies data from REST Countries API.
    Returns a list of tuples: (currency_name, currency_code, country_name)
    """
    try:
        # Fetch all countries data
        with httpx.Client() as client:
            response = client.get('https://restcountries.com/v3.1/all?fields=name,currencies')
            response.raise_for_status()
            countries_data = response.json()
        
        currencies_list = []
        seen_currencies = set()  # To avoid duplicates
        
        for country in countries_data:
            country_name = country.get('name', {}).get('common', 'Unknown')
            currencies = country.get('currencies', {})
            
            # Some countries have multiple currencies
            for currency_code, currency_info in currencies.items():
                currency_name = currency_info.get('name', currency_code)
                
                # Create a unique key to avoid duplicates
                currency_key = (currency_code, currency_name)
                if currency_key not in seen_currencies:
                    seen_currencies.add(currency_key)
                    currencies_list.append((currency_name, currency_code, country_name))
        
        return currencies_list
    except Exception as e:
        print(f"Error fetching currencies data: {e}")
        # Return some common currencies as fallback
        return [
            ('US Dollar', 'USD', 'United States'),
            ('Euro', 'EUR', 'European Union'),
            ('British Pound', 'GBP', 'United Kingdom'),
            ('Japanese Yen', 'JPY', 'Japan'),
            ('Canadian Dollar', 'CAD', 'Canada'),
            ('Australian Dollar', 'AUD', 'Australia'),
            ('Swiss Franc', 'CHF', 'Switzerland'),
            ('Chinese Yuan', 'CNY', 'China'),
            ('Indian Rupee', 'INR', 'India'),
            ('Brazilian Real', 'BRL', 'Brazil'),
        ]


def upgrade() -> None:
    # Fetch currencies data
    currencies_data = fetch_currencies_data()
    
    # Create a connection to insert data
    connection = op.get_bind()
    
    # Insert currencies data
    for currency_name, currency_code, country_name in currencies_data:
        connection.execute(
            sa.text("""
                INSERT INTO currencies (name, value, country)
                VALUES (:name, :value, :country)
            """),
            {
                'name': currency_name,
                'value': currency_code,
                'country': country_name
            }
        )


def downgrade() -> None:
    # Remove all currencies data
    connection = op.get_bind()
    connection.execute(sa.text("DELETE FROM currencies"))

