"""
Synthetic Transaction Data Generator
Generates realistic transaction patterns for 6 months (Aug 2025 - Jan 2026)
"""


import uuid
import random
from datetime import datetime, timedelta
from typing import List, Dict, Tuple

# Constants from existing data
USER_ID = "6cb253ea-e4c8-4039-a0a1-ec6f7d6ffc40"
CURRENCY_ID = "7fb00987-3914-4305-8a01-c175b7cee768"  # INR

# Mock data for SQL generation
ACCOUNTS = {
    "hdfc_savings_4319": "de209d7f-926b-4757-8d4f-a083fb48fb33",
    "hdfc_credit_7420": "7fdc9472-cba7-4945-b3f9-3db48cb116fb",
    "hdfc_savings_7710": "320fc46e-170a-4607-a377-11ed800901e0",
    "hdfc_savings_6834": "9bd6fbd7-7f15-4e51-96f4-8662467d24d1",
}

CATEGORIES = {
    "Housing": "31a90d3c-d86c-4bf0-aa59-39e11416b774",
    "Utilities": "f390b3fa-0c5f-40d1-8749-b09c237335d5",
    "Food": "e4270e71-d112-4d45-9f08-83c8bfb2821c",
    "Transport": "593e57e7-4231-42c9-ba9e-0f71b1c18224",
    "Shopping": "f390b3fa-0c5f-40d1-8749-b09c237335d5",
    "Subscriptions": "abf8907b-ffcc-40c0-a904-39a8735dd3c8",
    "Health": "79cbaa9d-505d-4d5d-a064-aec1ef784dcf",
    "Entertainment": "c72d4594-a7d0-47ba-b5af-69a85a87e8cb",
    "Travel": "89e630d2-f23e-4e8f-b6d1-11dda8fdbb2e",
    "Income": "89e630d2-f23e-4e8f-b6d1-11dda8fdbb2e",
    "Savings": "89e630d2-f23e-4e8f-b6d1-11dda8fdbb2e",
    "Loans": "89e630d2-f23e-4e8f-b6d1-11dda8fdbb2e",
    "Transfers": "89e630d2-f23e-4e8f-b6d1-11dda8fdbb2e",
}

# ======================
# REALISM HELPERS
# ======================

def drift_day(base_day: int) -> int:
    """Human-like date drift"""
    drift = random.choice([-2, -1, 0, 0, 1, 2])
    return max(1, min(28, base_day + drift))


def sticky_amount(base: float, volatility=0.12, round_to=10) -> float:
    """Amount sticks close to base, not linear growth"""
    change = random.uniform(-volatility, volatility)
    val = base * (1 + change)
    return round(val / round_to) * round_to


def gaussian_tx_count(mean=45, std=15, min_val=15, max_val=90) -> int:
    """Human-like transaction density"""
    return int(max(min(random.gauss(mean, std), max_val), min_val))


MONTH_MULTIPLIER = {
    8: 1.0,    # Aug
    9: 0.9,
    10: 1.3,   # Diwali
    11: 1.1,
    12: 1.4,   # Year end
    1: 0.8,
}


def realistic_electricity():
    """Price-shaped electricity amounts"""
    return random.choices(
        [850, 1100, 1350, 1600, 1850],
        weights=[0.15, 0.3, 0.3, 0.2, 0.05]
    )[0]

class TransactionGenerator:
    def __init__(self):
        self.transactions = []
        self.transactors = []
        self.transactor_map = {}
        
    def generate_transactor(self, name: str, source_id: str = None) -> str:
        """Generate or get existing transactor UUID"""
        if name in self.transactor_map:
            return self.transactor_map[name]
        
        transactor_id = str(uuid.uuid4())
        self.transactor_map[name] = transactor_id
        self.transactors.append({
            "id": transactor_id,
            "name": name,
            "source_id": source_id,
        })
        return transactor_id
    
    def add_transaction(self, date: datetime, amount: float, transactor_name: str,
                       category: str, description: str, tx_type: str = "expense",
                       account: str = "hdfc_savings_4319", source_id: str = None):
        """Add a transaction"""
        transactor_id = self.generate_transactor(transactor_name, source_id)
        
        self.transactions.append({
            "id": str(uuid.uuid4()),
            "amount": amount,
            "type": tx_type,
            "date": date.strftime("%Y-%m-%d %H:%M:%S.000 +0530"),
            "transactor_id": transactor_id,
            "category_id": CATEGORIES.get(category, CATEGORIES["Food"]),
            "description": description,
            "confidence": 1.0,
            "account_id": ACCOUNTS[account],
        })
    
    def generate_fixed_recurring(self, start_date: datetime, months: int):
        """Generate fixed recurring transactions (realistic)"""
        print("Generating fixed recurring transactions...")

        # --- PNB Housing EMI ---
        base_emi = 26200
        for m in range(months):
            month_date = (start_date + timedelta(days=30 * m))
            tx_date = month_date.replace(day=drift_day(5))

            self.add_transaction(
                tx_date,
                sticky_amount(base_emi, 0.01, 100),
                "PNB Housing Finance Limited",
                "Loans",
                f"Home loan EMI - {tx_date.strftime('%b %Y')}",
                account="hdfc_savings_4319",
                source_id="HDFC7021807230034209"
            )

        # --- Netflix ---
        base_netflix = 840
        for m in range(months):
            month_date = (start_date + timedelta(days=30 * m))
            tx_date = month_date.replace(day=drift_day(12))

            self.add_transaction(
                tx_date,
                base_netflix,
                "NETFLIX COM",
                "Subscriptions",
                "Netflix monthly subscription",
                account="hdfc_credit_7420",
                source_id="netflixupi.payu@hdfcbank"
            )

            # retry once in a while
            if random.random() < 0.07:
                self.add_transaction(
                    tx_date + timedelta(days=1),
                    base_netflix,
                    "NETFLIX COM",
                    "Subscriptions",
                    "Netflix retry charge",
                    account="hdfc_credit_7420",
                    source_id="netflixupi.payu@hdfcbank"
                )

        # --- Spotify ---
        base_spotify = 119
        for m in range(months):
            month_date = (start_date + timedelta(days=30 * m))
            tx_date = month_date.replace(day=drift_day(1))

            self.add_transaction(
                tx_date,
                base_spotify,
                "Spotify",
                "Subscriptions",
                "Spotify monthly subscription",
                account="hdfc_savings_4319",
                source_id="spotify@paytm"
            )

        # --- Amazon Prime ---
        base_prime = 299
        for m in range(months):
            month_date = (start_date + timedelta(days=30 * m))
            tx_date = month_date.replace(day=drift_day(18))

            self.add_transaction(
                tx_date,
                base_prime,
                "Amazon Prime",
                "Subscriptions",
                "Amazon Prime monthly subscription",
                account="hdfc_credit_7420",
                source_id="primevideo@paytm"
            )

        # --- Google Play ---
        base_gplay = 650
        for m in range(months):
            month_date = (start_date + timedelta(days=30 * m))
            tx_date = month_date.replace(day=drift_day(28))

            self.add_transaction(
                tx_date,
                base_gplay,
                "Google Play",
                "Subscriptions",
                "Google Play subscription",
                account="hdfc_savings_4319",
                source_id="googleplay@paytm"
            )

        # --- Digital Gold SIP ---
        base_gold = 100
        for m in range(months):
            month_date = (start_date + timedelta(days=30 * m))
            tx_date = month_date.replace(day=drift_day(6))

            self.add_transaction(
                tx_date,
                sticky_amount(base_gold, 0.15, 1),
                "AuraGold",
                "Savings",
                "Digital gold SIP",
                source_id="cf.auragoldapp@mairtel"
            )

        # --- Mutual Fund SIP ---
        base_mf = 1000
        for m in range(months):
            month_date = (start_date + timedelta(days=30 * m))
            tx_date = month_date.replace(day=drift_day(3))

            self.add_transaction(
                tx_date,
                sticky_amount(base_mf, 0.12, 50),
                "Zerodha Broking Limited",
                "Savings",
                "Mutual fund SIP",
                source_id="zerodha.rzpiccl.brk@validicici"
            )
    
    def generate_semi_monthly_income(self, start_date: datetime, months: int):
        """Generate semi-monthly recurring income with proper intervals"""
        print("Generating semi-monthly income...")
        
        # Mr Sabitha - Last day of every month (₹16,500 rental income)
        current_date = start_date
        for month in range(months):
            # Get last day of current month
            if current_date.month == 12:
                last_day = current_date.replace(year=current_date.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                last_day = current_date.replace(month=current_date.month + 1, day=1) - timedelta(days=1)
            
            self.add_transaction(
                last_day, 16500, "Mr Sabitha", "Income",
                "Rental income", tx_type="income",
                source_id="sabipari2674@oksbi"
            )
            
            # Move to next month
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
        
        # Niraimathi - Monthly on 5th and 31st (salary + bonus pattern)
        current_date = start_date.replace(day=5)
        for month in range(months):
            self.add_transaction(
                current_date, 30000, "NIRAIMATHI SANKARASUBRAMANIYAN", "Income",
                "Monthly salary", tx_type="income",
                source_id="niraimathi@okaxis"
            )
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
    
    def generate_monthly_variable(self, start_date: datetime, months: int):
        """Generate monthly variable transactions with realistic patterns"""
        print("Generating monthly variable transactions...")
        
        # Family support - 6th of every month (variable amount)
        current_date = start_date.replace(day=6)
        for month in range(months):
            amount = random.randint(8000, 10000)
            self.add_transaction(
                current_date, amount, "SARATHKUMAR SENTHILKUMAR", "Transfers",
                "Family support transfer", tx_type="expense",
                source_id="sarath06112003@okaxis"
            )
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
    
    def generate_utilities(self, start_date: datetime, months: int):
        """Generate utility bills with realistic monthly patterns"""
        print("Generating utility bills...")
        
        # Indane Gas - 15th of every month (₹1,400 fixed with drift)
        for month in range(months):
            month_date = (start_date + timedelta(days=30 * month))
            tx_date = month_date.replace(day=drift_day(15))
            
            self.add_transaction(
                tx_date, 1400, "Indane Gas", "Utilities",
                "LPG cylinder refill",
                source_id="indanegas@paytm"
            )
        
        # Electricity Bill - 7th of every month (realistic distribution with seasonal scaling)
        for month in range(months):
            month_date = (start_date + timedelta(days=30 * month))
            tx_date = month_date.replace(day=drift_day(7))
            
            amount = int(realistic_electricity() * MONTH_MULTIPLIER.get(tx_date.month, 1.0))
            self.add_transaction(
                tx_date, amount, "BESCOM", "Utilities",
                f"Electricity bill for {tx_date.strftime('%B %Y')}",
                source_id="bescom.bill@paytm"
            )
        
        # Google Workspace - 4th of every month (₹2,262.43 fixed with drift)
        for month in range(months):
            month_date = (start_date + timedelta(days=30 * month))
            tx_date = month_date.replace(day=drift_day(4))
            
            self.add_transaction(
                tx_date, 2262.43, "GOOGLEWORKSP", "Subscriptions",
                "Google Workspace monthly subscription",
                account="hdfc_credit_7420",
                source_id="googleworkspace@paytm"
            )
    
    def generate_monthly_healthcare(self, start_date: datetime, months: int):
        """Generate monthly healthcare expenses (pharmacies, fitness)"""
        print("Generating monthly healthcare...")
        
        # Apollo Pharmacy - 10th of every month (variable amount)
        current_date = start_date.replace(day=10)
        for month in range(months):
            amount = random.randint(500, 2000)
            self.add_transaction(
                current_date, amount, "Apollo Pharmacy", "Health",
                "Monthly medicine purchase",
                source_id="apollo@paytm"
            )
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
        
        # Medplus - 22nd of every month (variable amount)
        current_date = start_date.replace(day=22)
        for month in range(months):
            amount = random.randint(400, 1500)
            self.add_transaction(
                current_date, amount, "Medplus", "Health",
                "Monthly pharmacy purchase",
                source_id="medplus@paytm"
            )
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
        
        # 1mg - 25th of every month (variable amount)
        current_date = start_date.replace(day=25)
        for month in range(months):
            amount = random.randint(300, 1800)
            self.add_transaction(
                current_date, amount, "1mg", "Health",
                "Monthly medicine order",
                source_id="1mg@paytm"
            )
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
        
        # Cult.fit - 1st of every month (fitness subscription)
        current_date = start_date.replace(day=1)
        for month in range(months):
            amount = random.choice([1020, 1499, 2672])  # Different plans
            self.add_transaction(
                current_date, amount, "Cult.fit", "Health",
                "Fitness subscription",
                source_id="cultfit@paytm"
            )
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
    
    def generate_daily_expenses(self, start_date: datetime, months: int):
        """Generate realistic daily expenses with human behaviour"""
        print("Generating daily expenses...")
        
        merchants = {
            "Food": [
                ("Swiggy", "swiggy@paytm", 150, 800),
                ("Zomato", "zomato@paytm", 150, 800),
                ("McDonald's", "mcdonalds@paytm", 200, 600),
                ("KFC", "kfc@paytm", 250, 700),
                ("Domino's Pizza", "dominos@paytm", 300, 1000),
                ("Starbucks", "starbucks@paytm", 200, 500),
                ("Big Bazaar", "bigbazaar@paytm", 500, 3000),
                ("DMart", "dmart@paytm", 800, 4000),
            ],
            "Transport": [
                ("Uber", "uber@paytm", 80, 400),
                ("Ola", "ola@paytm", 80, 400),
                ("HP Petrol Pump", "hp@paytm", 300, 1000),
                ("Indian Oil", "iocl@paytm", 300, 1000),
                ("FastTag", "fastag@paytm", 100, 500),
            ],
            "Shopping": [
                ("Amazon", "amazon@paytm", 200, 5000),
                ("Flipkart", "flipkart@paytm", 200, 5000),
                ("Myntra", "myntra@paytm", 500, 3000),
                ("Reliance Digital", "reliancedigital@paytm", 1000, 10000),
            ],
            "Entertainment": [
                ("BookMyShow", "bookmyshow@paytm", 200, 800),
                ("PVR Cinemas", "pvr@paytm", 300, 1200),
            ],
        }
        
        for month in range(months):
            base_date = start_date + timedelta(days=30 * month)
            
            # Gaussian distribution of transactions per month
            num_transactions = gaussian_tx_count()
            month_multiplier = MONTH_MULTIPLIER.get(base_date.month, 1.0)
            
            for _ in range(num_transactions):
                day = random.randint(1, 28)
                hour = random.randint(8, 23)
                minute = random.randint(0, 59)
                
                tx_date = base_date.replace(day=day, hour=hour, minute=minute)
                
                # Choose category and merchant
                category = random.choices(
                    list(merchants.keys()),
                    weights=[40, 20, 30, 10],
                )[0]
                
                merchant_data = random.choice(merchants[category])
                merchant_name, source_id, min_amt, max_amt = merchant_data
                
                amount = int(random.randint(int(min_amt * 0.9), int(max_amt * 1.1)) * month_multiplier)
                
                # 80% primary account, 15% credit card, 5% other
                account_choice = random.choices(
                    ["hdfc_savings_4319", "hdfc_credit_7420", "hdfc_savings_7710"],
                    weights=[80, 15, 5]
                )[0]
                
                self.add_transaction(
                    tx_date, amount, merchant_name, category,
                    f"Payment to {merchant_name}",
                    account=account_choice,
                    source_id=source_id
                )
                
                # Duplicate spend behaviour (same-day retries)
                if random.random() < 0.08:
                    self.add_transaction(
                        tx_date + timedelta(minutes=random.randint(15, 90)),
                        amount + random.randint(-50, 100),
                        merchant_name,
                        category,
                        f"Payment to {merchant_name}",
                        account=account_choice,
                        source_id=source_id
                    )
    
    def generate_seasonal_patterns(self, start_date: datetime, months: int):
        """Generate seasonal expenses (Diwali, Christmas, etc.)"""
        print("Generating seasonal patterns...")
        
        # October - Diwali shopping
        if 10 - start_date.month in range(months):
            diwali_date = start_date.replace(month=10, day=20)
            
            # Heavy shopping
            for i in range(10):
                self.add_transaction(
                    diwali_date + timedelta(days=i),
                    random.randint(2000, 10000),
                    random.choice(["Amazon", "Flipkart", "Saravana Stores"]),
                    "Shopping",
                    "Diwali shopping",
                    account="hdfc_credit_7420"
                )
            
            # Gifts and donations
            for i in range(5):
                self.add_transaction(
                    diwali_date + timedelta(days=i),
                    random.randint(1000, 5000),
                    "Diwali Gifts",
                    "Transfers",
                    "Diwali gift to family/friends",
                )
        
        # December - Christmas and New Year
        if 12 - start_date.month in range(months):
            xmas_date = start_date.replace(month=12, day=24)
            
            for i in range(7):
                self.add_transaction(
                    xmas_date + timedelta(days=i),
                    random.randint(1000, 5000),
                    random.choice(["Malls", "Restaurants", "Hotels"]),
                    random.choice(["Food", "Shopping", "Entertainment"]),
                    "Year-end celebration",
                    account="hdfc_credit_7420"
                )
    
    def generate_all(self):
        """Generate all transaction types"""
        start_date = datetime(2025, 8, 1)
        months = 6
        
        self.generate_fixed_recurring(start_date, months)
        self.generate_semi_monthly_income(start_date, months)
        self.generate_monthly_variable(start_date, months)
        self.generate_utilities(start_date, months)
        self.generate_monthly_healthcare(start_date, months)
        self.generate_daily_expenses(start_date, months)
        self.generate_seasonal_patterns(start_date, months)
        
        print(f"\nGenerated {len(self.transactions)} transactions")
        print(f"Generated {len(self.transactors)} new transactors")
    
    def export_sql(self, filename: str):
        """Export as SQL INSERT statements"""
        mock_accounts = [
            {"id": "de209d7f-926b-4757-8d4f-a083fb48fb33", "last_four": "4319", "bank": "HDFC Bank", "type": "savings"},
            {"id": "7fdc9472-cba7-4945-b3f9-3db48cb116fb", "last_four": "7420", "bank": "HDFC Bank", "type": "credit"},
            {"id": "320fc46e-170a-4607-a377-11ed800901e0", "last_four": "7710", "bank": "HDFC Bank", "type": "savings"},
            {"id": "9bd6fbd7-7f15-4e51-96f4-8662467d24d1", "last_four": "6834", "bank": "HDFC Bank", "type": "savings"},
        ]
        mock_categories = {
            "Housing": "31a90d3c-d86c-4bf0-aa59-39e11416b774",
            "Utilities": "f390b3fa-0c5f-40d1-8749-b09c237335d5",
            "Food": "e4270e71-d112-4d45-9f08-83c8bfb2821c",
            "Transport": "593e57e7-4231-42c9-ba9e-0f71b1c18224",
            "Shopping": "f390b3fa-0c5f-40d1-8749-b09c237335d5",
            "Subscriptions": "abf8907b-ffcc-40c0-a904-39a8735dd3c8",
            "Health": "79cbaa9d-505d-4d5d-a064-aec1ef784dcf",
            "Entertainment": "c72d4594-a7d0-47ba-b5af-69a85a87e8cb",
            "Travel": "89e630d2-f23e-4e8f-b6d1-11dda8fdbb2e",
            "Income": "89e630d2-f23e-4e8f-b6d1-11dda8fdbb2e",
            "Savings": "89e630d2-f23e-4e8f-b6d1-11dda8fdbb2e",
            "Loans": "89e630d2-f23e-4e8f-b6d1-11dda8fdbb2e",
            "Transfers": "89e630d2-f23e-4e8f-b6d1-11dda8fdbb2e",
        }
        with open(filename, 'w') as f:
            f.write("-- Synthetic Transaction Data\n")
            f.write("-- Generated for 6 months (Aug 2025 - Jan 2026)\n\n")

            # Insert mock accounts
            f.write("-- Insert Accounts\n")
            for acc in mock_accounts:
                f.write(f"INSERT INTO accounts (id, user_id, account_last_four, bank_name, type) VALUES ('{acc['id']}', '{USER_ID}', '{acc['last_four']}', '{acc['bank']}', '{acc['type']}') ON CONFLICT (id) DO NOTHING;\n")

            # Insert mock categories
            f.write("\n-- Insert Categories\n")
            for label, cat_id in mock_categories.items():
                f.write(f"INSERT INTO categories (id, label) VALUES ('{cat_id}', '{label}') ON CONFLICT (id) DO NOTHING;\n")

            # Transactors
            f.write("\n-- Insert Transactors\n")
            for t in self.transactors:
                source_id = f"'{t['source_id']}'" if t['source_id'] else "NULL"
                # Escape single quotes in name
                name = t['name'].replace("'", "''")
                f.write(f"INSERT INTO transactors (id, name, user_id, source_id, picture, label) VALUES "
                       f"('{t['id']}', '{name}', '{USER_ID}', {source_id}, NULL, NULL) "
                       f"ON CONFLICT (id) DO NOTHING;\n")

            f.write("\n-- Insert Transactions\n")
            for tx in self.transactions:
                # Escape single quotes in description
                description = tx['description'].replace("'", "''")
                f.write(
                    f"INSERT INTO transactions (id, amount, transaction_id, type, date, "
                    f"transactor_id, category_id, description, confidence, currency_id, "
                    f"user_id, message_id, account_id) VALUES "
                    f"('{tx['id']}', {tx['amount']}, NULL, '{tx['type']}', '{tx['date']}', "
                    f"'{tx['transactor_id']}', '{tx['category_id']}', '{description}', "
                    f"{tx['confidence']}, '{CURRENCY_ID}', '{USER_ID}', NULL, '{tx['account_id']}');\n"
                )
    
    def export_csv(self, trans_file: str, transactor_file: str):
        """Export as CSV files"""
        import csv
        
        # Transactions CSV
        with open(trans_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'id', 'amount', 'transaction_id', 'type', 'date', 'transactor_id',
                'category_id', 'description', 'confidence', 'currency_id', 'user_id',
                'message_id', 'account_id'
            ])
            writer.writeheader()
            for tx in self.transactions:
                row = tx.copy()
                row['transaction_id'] = None
                row['currency_id'] = CURRENCY_ID
                row['user_id'] = USER_ID
                row['message_id'] = None
                writer.writerow(row)
        
        # Transactors CSV
        with open(transactor_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'id', 'name', 'user_id', 'source_id', 'picture', 'label'
            ])
            writer.writeheader()
            for t in self.transactors:
                row = t.copy()
                row['user_id'] = USER_ID
                row['picture'] = None
                row['label'] = None
                writer.writerow(row)


if __name__ == "__main__":
    generator = TransactionGenerator()
    generator.generate_all()
    
    # Export to files
    generator.export_sql("/Users/balaji/Desktop/synthetic_transactions.sql")
    generator.export_csv(
        "/Users/balaji/Desktop/synthetic_transactions.csv",
        "/Users/balaji/Desktop/synthetic_transactors.csv"
    )
    
    print("\n✅ Files generated:")
    print("  - synthetic_transactions.sql")
    print("  - synthetic_transactions.csv")
    print("  - synthetic_transactors.csv")
