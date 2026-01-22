"""
Synthetic Transaction Data Generator
Generates realistic transaction patterns for 6 months (Aug 2025 - Jan 2026)
"""

import uuid
import random
from datetime import datetime, timedelta
from typing import List, Dict, Tuple

# Constants from existing data
USER_ID = "0b5b6f4e-a12e-4272-9064-83c2efdbb3e3"
CURRENCY_ID = "3f60058b-1a06-4281-8b55-9c75e8175392"  # INR

# Accounts (mainly use first 2)
ACCOUNTS = {
    "hdfc_savings_4319": "de209d7f-926b-4757-8d4f-a083fb48fb33",  # Primary
    "hdfc_credit_7420": "7fdc9472-cba7-4945-b3f9-3db48cb116fb",   # Secondary
    "hdfc_savings_7710": "320fc46e-170a-4607-a377-11ed800901e0",  # Occasional
    "hdfc_savings_6834": "9bd6fbd7-7f15-4e51-96f4-8662467d24d1",  # Rare
}

# Categories (from your 20 standard categories)
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
        """Generate fixed recurring transactions with REALISTIC monthly intervals"""
        print("Generating fixed recurring transactions...")
        
        # PNB Housing EMI - 5th of every month (perfect monthly pattern)
        current_date = start_date.replace(day=5)
        for month in range(months):
            self.add_transaction(
                current_date, 26200, "PNB Housing Finance Limited", "Loans",
                f"Home loan EMI for {current_date.strftime('%B %Y')}",
                account="hdfc_savings_4319",
                source_id="HDFC7021807230034209"
            )
            # Next month same day (28-31 days interval)
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
        
        # Netflix - 12th of every month (perfect monthly subscription)
        current_date = start_date.replace(day=12)
        for month in range(months):
            self.add_transaction(
                current_date, 840, "NETFLIX COM", "Subscriptions",
                "Netflix Premium monthly subscription",
                account="hdfc_credit_7420",
                source_id="netflixupi.payu@hdfcbank"
            )
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
        
        # Spotify - 1st of every month (perfect fixed monthly)
        current_date = start_date.replace(day=1)
        for month in range(months):
            self.add_transaction(
                current_date, 119, "Spotify", "Subscriptions",
                "Spotify Premium monthly subscription",
                account="hdfc_savings_4319",
                source_id="spotify@paytm"
            )
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
        
        # Amazon Prime - 18th of every month (fixed monthly)
        current_date = start_date.replace(day=18)
        for month in range(months):
            self.add_transaction(
                current_date, 299, "Amazon Prime", "Subscriptions",
                "Amazon Prime monthly subscription",
                account="hdfc_credit_7420",
                source_id="primevideo@paytm"
            )
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
        
        # Google Play - 28th of every month (fixed monthly)
        current_date = start_date.replace(day=28)
        for month in range(months):
            self.add_transaction(
                current_date, 650, "Google Play", "Subscriptions",
                "Google Play subscription",
                account="hdfc_savings_4319",
                source_id="googleplay@paytm"
            )
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
        
        # Digital Gold SIP - 6th of every month (variable amount monthly)
        current_date = start_date.replace(day=6)
        base_amount = 100
        for month in range(months):
            amount = base_amount + (month * 10)  # Gradually increasing
            self.add_transaction(
                current_date, amount, "AuraGold", "Savings",
                f"Digital gold purchase - monthly SIP",
                source_id="cf.auragoldapp@mairtel"
            )
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
        
        # Mutual Fund SIP - 3rd of every month (variable amount monthly)
        current_date = start_date.replace(day=3)
        base_mf = 1000
        for month in range(months):
            amount = base_mf + (month * 100)  # Gradually increasing
            self.add_transaction(
                current_date, amount, "Zerodha Broking Limited", "Savings",
                f"Mutual fund SIP investment",
                source_id="zerodha.rzpiccl.brk@validicici"
            )
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
    
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
        
        # Indane Gas - 15th of every month (₹1,400 fixed)
        current_date = start_date.replace(day=15)
        for month in range(months):
            self.add_transaction(
                current_date, 1400, "Indane Gas", "Utilities",
                "LPG cylinder refill",
                source_id="indanegas@paytm"
            )
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
        
        # Electricity Bill - 7th of every month (₹800-1,800 variable)
        current_date = start_date.replace(day=7)
        for month in range(months):
            amount = random.randint(800, 1800)
            self.add_transaction(
                current_date, amount, "BESCOM", "Utilities",
                f"Electricity bill for {current_date.strftime('%B %Y')}",
                source_id="bescom.bill@paytm"
            )
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
        
        # Google Workspace - 4th of every month (₹2,262.43 fixed)
        current_date = start_date.replace(day=4)
        for month in range(months):
            self.add_transaction(
                current_date, 2262.43, "GOOGLEWORKSP", "Subscriptions",
                "Google Workspace monthly subscription",
                account="hdfc_credit_7420",
                source_id="googleworkspace@paytm"
            )
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
    
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
        """Generate realistic daily expenses (excludes monthly subscriptions)"""
        print("Generating daily expenses...")
        
        # NOTE: Monthly subscriptions (Spotify, Netflix, Amazon Prime, pharmacies) 
        # are generated separately to ensure proper monthly intervals
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
            
            # Generate 50-70 random daily transactions per month (reduced from 150-170)
            # This keeps focus on recurring patterns
            num_transactions = random.randint(50, 70)
            
            for _ in range(num_transactions):
                day = random.randint(1, 28)
                hour = random.randint(8, 23)
                minute = random.randint(0, 59)
                
                tx_date = base_date.replace(day=day, hour=hour, minute=minute)
                
                # Choose category and merchant
                category = random.choices(
                    list(merchants.keys()),
                    weights=[40, 20, 30, 10],  # Food 40%, Transport 20%, Shopping 30%, Entertainment 10%
                )[0]
                
                merchant_data = random.choice(merchants[category])
                merchant_name, source_id, min_amt, max_amt = merchant_data
                
                amount = random.randint(min_amt, max_amt)
                
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
        with open(filename, 'w') as f:
            f.write("-- Synthetic Transaction Data\n")
            f.write("-- Generated for 6 months (Aug 2025 - Jan 2026)\n\n")
            
            # Transactors
            f.write("-- Insert Transactors\n")
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
