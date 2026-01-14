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
        """Generate fixed recurring transactions"""
        print("Generating fixed recurring transactions...")
        
        for month in range(months):
            base_date = start_date + timedelta(days=30 * month)
            
            # PNB Housing EMI - 5th of every month
            emi_date = base_date.replace(day=5)
            self.add_transaction(
                emi_date, 26200, "PNB Housing Finance Limited", "Loans",
                f"Home loan EMI for {emi_date.strftime('%B %Y')}",
                account="hdfc_savings_4319",
                source_id="HDFC7021807230034209"
            )
            
            # Netflix - 12th of every month
            netflix_date = base_date.replace(day=12)
            self.add_transaction(
                netflix_date, 840, "NETFLIX COM", "Subscriptions",
                "Netflix Premium monthly subscription",
                account="hdfc_credit_7420",
                source_id="netflixupi.payu@hdfcbank"
            )
            
            # Aura Silver SIP - 1st, 2nd, 3rd of each month (increasing pattern)
            aura_amounts = [100, 110, 121]  # Month 0, 1, 2 pattern
            base_amount = 100 + (month * 10)
            
            for day, increment in [(1, 0), (2, 10), (3, 21)]:
                aura_date = base_date.replace(day=day)
                amount = base_amount + increment
                self.add_transaction(
                    aura_date, amount, "AuraGold", "Savings",
                    f"Digital gold purchase - monthly SIP",
                    source_id="cf.auragoldapp@mairtel"
                )
            
            # Mutual Fund SIP - 3rd, 11th, 12th of month (increasing)
            mf_base = 1000 + (month * 100)
            for day, extra in [(3, 0), (11, 100), (12, 110)]:
                mf_date = base_date.replace(day=day)
                self.add_transaction(
                    mf_date, mf_base + extra, "Zerodha Broking Limited", "Savings",
                    f"Mutual fund SIP investment",
                    source_id="zerodha.rzpiccl.brk@validicici"
                )
    
    def generate_semi_monthly_income(self, start_date: datetime, months: int):
        """Generate semi-monthly recurring income"""
        print("Generating semi-monthly income...")
        
        for month in range(months):
            base_date = start_date + timedelta(days=30 * month)
            
            # Sabitha - Last day of month (₹16,500)
            last_day = (base_date.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
            self.add_transaction(
                last_day, 16500, "Mr Sabitha", "Income",
                "Rental income", tx_type="income",
                source_id="sabipari2674@oksbi"
            )
            
            # Swathi - 1st and last day of month (₹4,000-5,000)
            first_day = base_date.replace(day=1)
            amount1 = random.choice([4000, 4500, 5000])
            self.add_transaction(
                first_day, amount1, "Ms Swathi P", "Income",
                "Consulting payment", tx_type="income",
                source_id="swathipari155@oksbi"
            )
            
            last_day2 = last_day.replace(day=last_day.day - 1) if last_day.day > 1 else last_day
            amount2 = random.choice([4000, 4500, 5000])
            self.add_transaction(
                last_day2, amount2, "Ms Swathi P", "Income",
                "Consulting payment", tx_type="income",
                source_id="swathipari155@oksbi"
            )
    
    def generate_monthly_variable(self, start_date: datetime, months: int):
        """Generate monthly variable transactions"""
        print("Generating monthly variable transactions...")
        
        for month in range(months):
            base_date = start_date + timedelta(days=30 * month)
            
            # Sarath - 3 times a month (₹8,000-10,000)
            for day in [4, 6, 3]:
                sarath_date = base_date.replace(day=min(day, 28))
                amount = random.randint(8000, 10000)
                self.add_transaction(
                    sarath_date, amount, "SARATHKUMAR SENTHILKUMAR", "Transfers",
                    "Family support transfer", tx_type="expense",
                    source_id="sarath06112003@okaxis"
                )
            
            # Selvam - 8-9 times a month (₹2,200-10,000 - highly variable)
            for i in range(random.randint(8, 9)):
                day = random.randint(2, 28)
                selvam_date = base_date.replace(day=day)
                amount = random.choice([2200, 2400, 2500, 4200, 4300, 8200, 8300, 10000])
                self.add_transaction(
                    selvam_date, amount, "Mr S Stanislous", "Food",
                    "Restaurant/catering payment", tx_type="expense",
                    source_id="bharatpe.90059928185@fbpe"
                )
    
    def generate_utilities(self, start_date: datetime, months: int):
        """Generate utility bills"""
        print("Generating utility bills...")
        
        for month in range(months):
            base_date = start_date + timedelta(days=30 * month)
            
            # Indane Gas - 8th, 15th, 5th of month (₹1,400)
            for day in [8, 15, 5]:
                gas_date = base_date.replace(day=min(day, 28))
                self.add_transaction(
                    gas_date, 1400, "Indane Gas", "Utilities",
                    "LPG cylinder refill",
                    source_id="indanegas@paytm"
                )
            
            # Electricity Bill - 7th, 9th, 5th of month (₹800-1,800)
            for day in [7, 9, 5]:
                elec_date = base_date.replace(day=min(day, 28))
                amount = random.randint(800, 1800)
                self.add_transaction(
                    elec_date, amount, "BESCOM", "Utilities",
                    f"Electricity bill for {elec_date.strftime('%B %Y')}",
                    source_id="bescom.bill@paytm"
                )
    
    def generate_daily_expenses(self, start_date: datetime, months: int):
        """Generate realistic daily expenses"""
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
                ("Spotify", "spotify@paytm", 119, 119),
                ("Amazon Prime", "primevideo@paytm", 299, 299),
            ],
            "Health": [
                ("Apollo Pharmacy", "apollo@paytm", 100, 2000),
                ("Medplus", "medplus@paytm", 150, 1500),
                ("1mg", "1mg@paytm", 200, 2000),
                ("Cult.fit", "cultfit@paytm", 999, 2999),
            ],
        }
        
        for month in range(months):
            base_date = start_date + timedelta(days=30 * month)
            
            # Generate 150-170 random daily transactions per month
            num_transactions = random.randint(150, 170)
            
            for _ in range(num_transactions):
                day = random.randint(1, 28)
                hour = random.randint(8, 23)
                minute = random.randint(0, 59)
                
                tx_date = base_date.replace(day=day, hour=hour, minute=minute)
                
                # Choose category and merchant
                category = random.choices(
                    list(merchants.keys()),
                    weights=[35, 15, 20, 10, 10],  # Food 35%, Transport 15%, etc.
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
