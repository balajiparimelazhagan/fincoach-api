import psycopg2
from datetime import datetime, timedelta
import uuid
import os
from scripts.synthetic_data_generator import TransactionGenerator, ACCOUNTS as FIXED_ACCOUNTS, CATEGORIES as FIXED_CATEGORIES
import random

# ======================
# CONFIG
# ======================
DB_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres:root@localhost:5434/postgres')
TEST_USER_EMAIL = "user@roobai.ai"

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

# ======================
# DB HELPERS
# ======================
def get_connection():
    return psycopg2.connect(DB_URL)

def get_or_create_user(cur, email: str) -> str:
    cur.execute("""
        SELECT id FROM users WHERE email = %s LIMIT 1
    """, (email,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("""
        INSERT INTO users (email, google_id, created_at, updated_at)
        VALUES (%s, %s, NOW(), NOW())
        RETURNING id
    """, (email, f"test-{email}"))
    return cur.fetchone()[0]

def get_or_create_account(cur, user_id: str, name: str, account_type: str, last_four: str) -> str:
    cur.execute("""
        SELECT id FROM accounts WHERE user_id = %s AND account_last_four = %s LIMIT 1
    """, (user_id, last_four))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("""
        INSERT INTO accounts (user_id, bank_name, account_last_four, type)
        VALUES (%s, %s, %s, %s)
        RETURNING id
    """, (user_id, name, last_four, account_type))
    return cur.fetchone()[0]

def get_or_create_transactor(cur, user_id: str, name: str) -> str:
    cur.execute("""
        SELECT id FROM transactors WHERE user_id = %s AND name = %s LIMIT 1
    """, (user_id, name))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("""
        INSERT INTO transactors (user_id, name)
        VALUES (%s, %s)
        RETURNING id
    """, (user_id, name))
    return cur.fetchone()[0]

def fetch_categories(cur) -> dict:
    cur.execute("SELECT id, label FROM categories")
    return {row[1]: row[0] for row in cur.fetchall()}

def insert_transaction(cur, transactor_id: str, account_id: str, category_id: str, amount: float, tx_type: str, description: str, date: datetime, user_id: str):
    cur.execute("""
        INSERT INTO transactions (transactor_id, account_id, category_id, amount, type, description, date, user_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (transactor_id, account_id, category_id, amount, tx_type, description, date, user_id))

# ======================
# SYNTHETIC DATA GENERATION
# ======================
# ======================
# SYNTHETIC DATA GENERATION
# ======================
class DBSyntheticDataGenerator:
    def __init__(self, cur, user_id: str, accounts: dict, categories: dict):
        self.cur = cur
        self.user_id = user_id
        self.accounts = accounts  # dict of name -> id
        self.categories = categories  # dict of label -> id
        self.transactor_cache = {}

    def get_or_create_transactor(self, name: str, source_id: str = None) -> str:
        """Get or create transactor and cache it"""
        if name in self.transactor_cache:
            return self.transactor_cache[name]
        
        transactor_id = get_or_create_transactor(self.cur, self.user_id, name)
        self.transactor_cache[name] = transactor_id
        return transactor_id

    def add_transaction(self, date: datetime, amount: float, transactor_name: str,
                       category: str, description: str, tx_type: str = "debit",
                       account: str = "Checking Account", source_id: str = None):
        """Add a transaction to the database"""
        transactor_id = self.get_or_create_transactor(transactor_name, source_id)
        account_id = self.accounts[account]
        category_id = self.categories.get(category, self.categories.get("Food"))
        
        insert_transaction(self.cur, transactor_id, account_id, category_id, 
                          amount, tx_type, description, date, self.user_id)

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
                "Housing",
                f"Home loan EMI - {tx_date.strftime('%b %Y')}",
                tx_type="debit",
                account="Checking Account"
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
                tx_type="debit",
                account="Credit Card"
            )

            # retry once in a while
            if random.random() < 0.07:
                self.add_transaction(
                    tx_date + timedelta(days=1),
                    base_netflix,
                    "NETFLIX COM",
                    "Subscriptions",
                    "Netflix retry charge",
                    tx_type="debit",
                    account="Credit Card"
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
                tx_type="debit",
                account="Checking Account"
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
                tx_type="debit",
                account="Credit Card"
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
                tx_type="debit",
                account="Checking Account"
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
                tx_type="debit",
                account="Checking Account"
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
                tx_type="debit",
                account="Checking Account"
            )

    def generate_semi_monthly_income(self, start_date: datetime, months: int):
        """Generate semi-monthly recurring income"""
        print("Generating semi-monthly income...")

        # Mr Sabitha - Last day of every month (rental income)
        current_date = start_date
        for month in range(months):
            if current_date.month == 12:
                last_day = current_date.replace(year=current_date.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                last_day = current_date.replace(month=current_date.month + 1, day=1) - timedelta(days=1)
            
            self.add_transaction(
                last_day, 16500, "Mr Sabitha", "Income",
                "Rental income", tx_type="credit",
                account="Checking Account"
            )
            
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
        
        # Niraimathi - Monthly salary
        current_date = start_date.replace(day=5)
        for month in range(months):
            self.add_transaction(
                current_date, 30000, "NIRAIMATHI SANKARASUBRAMANIYAN", "Income",
                "Monthly salary", tx_type="credit",
                account="Checking Account"
            )
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)

    def generate_monthly_variable(self, start_date: datetime, months: int):
        """Generate monthly variable transactions"""
        print("Generating monthly variable transactions...")

        # Family support
        current_date = start_date.replace(day=6)
        for month in range(months):
            amount = random.randint(8000, 10000)
            self.add_transaction(
                current_date, amount, "SARATHKUMAR SENTHILKUMAR", "Transfers",
                "Family support transfer", tx_type="debit",
                account="Checking Account"
            )
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)

    def generate_utilities(self, start_date: datetime, months: int):
        """Generate utility bills"""
        print("Generating utility bills...")

        # Indane Gas
        for month in range(months):
            month_date = (start_date + timedelta(days=30 * month))
            tx_date = month_date.replace(day=drift_day(15))
            
            self.add_transaction(
                tx_date, 1400, "Indane Gas", "Utilities",
                "LPG cylinder refill",
                tx_type="debit",
                account="Checking Account"
            )
        
        # Electricity Bill
        for month in range(months):
            month_date = (start_date + timedelta(days=30 * month))
            tx_date = month_date.replace(day=drift_day(7))
            
            amount = int(realistic_electricity() * MONTH_MULTIPLIER.get(tx_date.month, 1.0))
            self.add_transaction(
                tx_date, amount, "BESCOM", "Utilities",
                f"Electricity bill for {tx_date.strftime('%B %Y')}",
                tx_type="debit",
                account="Checking Account"
            )
        
        # Google Workspace
        for month in range(months):
            month_date = (start_date + timedelta(days=30 * month))
            tx_date = month_date.replace(day=drift_day(4))
            
            self.add_transaction(
                tx_date, 2262.43, "GOOGLEWORKSP", "Subscriptions",
                "Google Workspace monthly subscription",
                tx_type="debit",
                account="Credit Card"
            )

    def generate_monthly_healthcare(self, start_date: datetime, months: int):
        """Generate monthly healthcare expenses"""
        print("Generating monthly healthcare...")

        # Apollo Pharmacy
        current_date = start_date.replace(day=10)
        for month in range(months):
            amount = random.randint(500, 2000)
            self.add_transaction(
                current_date, amount, "Apollo Pharmacy", "Health",
                "Monthly medicine purchase",
                tx_type="debit",
                account="Checking Account"
            )
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
        
        # Medplus
        current_date = start_date.replace(day=22)
        for month in range(months):
            amount = random.randint(400, 1500)
            self.add_transaction(
                current_date, amount, "Medplus", "Health",
                "Monthly pharmacy purchase",
                tx_type="debit",
                account="Checking Account"
            )
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
        
        # 1mg
        current_date = start_date.replace(day=25)
        for month in range(months):
            amount = random.randint(300, 1800)
            self.add_transaction(
                current_date, amount, "1mg", "Health",
                "Monthly medicine order",
                tx_type="debit",
                account="Checking Account"
            )
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
        
        # Cult.fit
        current_date = start_date.replace(day=1)
        for month in range(months):
            amount = random.choice([1020, 1499, 2672])
            self.add_transaction(
                current_date, amount, "Cult.fit", "Health",
                "Fitness subscription",
                tx_type="debit",
                account="Checking Account"
            )
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)

    def generate_daily_expenses(self, start_date: datetime, months: int):
        """Generate realistic daily expenses"""
        print("Generating daily expenses...")

        merchants = {
            "Food": [
                ("Swiggy", 150, 800),
                ("Zomato", 150, 800),
                ("McDonald's", 200, 600),
                ("KFC", 250, 700),
                ("Domino's Pizza", 300, 1000),
                ("Starbucks", 200, 500),
                ("Big Bazaar", 500, 3000),
                ("DMart", 800, 4000),
            ],
            "Transport": [
                ("Uber", 80, 400),
                ("Ola", 80, 400),
                ("HP Petrol Pump", 300, 1000),
                ("Indian Oil", 300, 1000),
                ("FastTag", 100, 500),
            ],
            "Shopping": [
                ("Amazon", 200, 5000),
                ("Flipkart", 200, 5000),
                ("Myntra", 500, 3000),
                ("Reliance Digital", 1000, 10000),
            ],
            "Entertainment": [
                ("BookMyShow", 200, 800),
                ("PVR Cinemas", 300, 1200),
            ],
        }
        
        for month in range(months):
            base_date = start_date + timedelta(days=30 * month)
            num_transactions = gaussian_tx_count()
            month_multiplier = MONTH_MULTIPLIER.get(base_date.month, 1.0)
            
            for _ in range(num_transactions):
                day = random.randint(1, 28)
                hour = random.randint(8, 23)
                minute = random.randint(0, 59)
                
                tx_date = base_date.replace(day=day, hour=hour, minute=minute)
                
                category = random.choices(
                    list(merchants.keys()),
                    weights=[40, 20, 30, 10],
                )[0]
                
                merchant_data = random.choice(merchants[category])
                merchant_name, min_amt, max_amt = merchant_data
                
                amount = int(random.randint(int(min_amt * 0.9), int(max_amt * 1.1)) * month_multiplier)
                
                account_choice = random.choices(
                    ["Checking Account", "Credit Card", "Savings Account"],
                    weights=[80, 15, 5]
                )[0]
                
                self.add_transaction(
                    tx_date, amount, merchant_name, category,
                    f"Payment to {merchant_name}",
                    tx_type="debit",
                    account=account_choice
                )
                
                # Duplicate spend behaviour
                if random.random() < 0.08:
                    self.add_transaction(
                        tx_date + timedelta(minutes=random.randint(15, 90)),
                        amount + random.randint(-50, 100),
                        merchant_name,
                        category,
                        f"Payment to {merchant_name}",
                        tx_type="debit",
                        account=account_choice
                    )

    def generate_seasonal_patterns(self, start_date: datetime, months: int):
        """Generate seasonal expenses"""
        print("Generating seasonal patterns...")

        # October - Diwali shopping
        if 10 - start_date.month in range(months):
            diwali_date = start_date.replace(month=10, day=20)
            
            for i in range(10):
                self.add_transaction(
                    diwali_date + timedelta(days=i),
                    random.randint(2000, 10000),
                    random.choice(["Amazon", "Flipkart", "Saravana Stores"]),
                    "Shopping",
                    "Diwali shopping",
                    tx_type="debit",
                    account="Credit Card"
                )
            
            for i in range(5):
                self.add_transaction(
                    diwali_date + timedelta(days=i),
                    random.randint(1000, 5000),
                    "Diwali Gifts",
                    "Transfers",
                    "Diwali gift to family/friends",
                    tx_type="debit",
                    account="Checking Account"
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
                    tx_type="debit",
                    account="Credit Card"
                )

    def generate_all(self, start_date: datetime | None = None, months: int = 6):
        if start_date is None:
            now = datetime.now()
            current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            # Go back (months - 1) months to get the start
            for _ in range(months - 1):
                if current_month_start.month == 1:
                    current_month_start = current_month_start.replace(year=current_month_start.year - 1, month=12)
                else:
                    current_month_start = current_month_start.replace(month=current_month_start.month - 1)
            start_date = current_month_start

        self.generate_fixed_recurring(start_date, months)
        self.generate_semi_monthly_income(start_date, months)
        self.generate_monthly_variable(start_date, months)
        self.generate_utilities(start_date, months)
        self.generate_monthly_healthcare(start_date, months)
        self.generate_daily_expenses(start_date, months)
        self.generate_seasonal_patterns(start_date, months)

# ======================
# MAIN
# ======================
def main(conn=None):
    if conn is None:
        conn = get_connection()
        close_conn = True
    else:
        close_conn = False
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            print("Creating user...")
            user_id = get_or_create_user(cur, TEST_USER_EMAIL)
            print(f"User ID: {user_id}")
            
            # Ensure fixed accounts exist (use the same ids as the generator)
            print("Ensuring fixed accounts exist...")
            accounts = {}
            for key, acct_id in FIXED_ACCOUNTS.items():
                # derive simple fields from the key
                parts = key.split("_")
                last_four = parts[-1]
                bank_name = parts[0].upper()
                acct_type = "credit" if "credit" in key else "savings" if "savings" in key else "current"

                # insert using explicit id if missing
                cur.execute("SELECT id FROM accounts WHERE id = %s", (acct_id,))
                if not cur.fetchone():
                    cur.execute(
                        """
                        INSERT INTO accounts (id, user_id, account_last_four, bank_name, type)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (acct_id, user_id, last_four, bank_name, acct_type),
                    )
                accounts[key] = acct_id
            print(f"Accounts created/verified: {accounts}")
            
            # Fetch categories
            print("Fetching categories...")
            categories = fetch_categories(cur)
            print(f"Categories count: {len(categories)}")
            
            # Generate synthetic data
            # Generate synthetic transactions via the original generator logic
            print("Generating synthetic data using shared generator...")
            generator = TransactionGenerator()
            generator.generate_all()

            # insert transactors and transactions from the generator into DB
            inv_cat = {v: k for k, v in FIXED_CATEGORIES.items()}
            # map generator transactor ids back to their names
            id_to_name = {t["id"]: t["name"] for t in generator.transactors}
            for tx in generator.transactions:
                # translate category id to label then to actual db id
                label = inv_cat.get(tx["category_id"], None)
                if label is None:
                    continue
                db_cat_id = categories.get(label)
                if db_cat_id is None:
                    continue

                # lookup transactor name and ensure it exists
                name = id_to_name.get(tx["transactor_id"])
                transactor_id = get_or_create_transactor(cur, user_id, name)

                # insert transaction record
                insert_transaction(
                    cur,
                    transactor_id,
                    tx["account_id"],
                    db_cat_id,
                    float(tx["amount"]),
                    tx["type"],
                    tx["description"],
                    datetime.strptime(tx["date"], "%Y-%m-%d %H:%M:%S.000 +0530"),
                    user_id,
                )
            
        conn.commit()
        print(f"✅ Synthetic data created for {TEST_USER_EMAIL}")
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
        raise
    finally:
        if close_conn:
            conn.close()

if __name__ == "__main__":
    main()
