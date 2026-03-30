"""
Synthetic Data Builder
Generates realistic transaction patterns for a configurable window (default: 6 months back from today)
and exports them to .sql / .csv files for manual import.

Usage:
    python synthetic_data_builder.py [--months N] [--out-dir /path/to/dir]
"""

import argparse
import csv
import os
import random
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

# ─────────────────────────────────────────────
# Reference data  (kept in-sync with the DB seed)
# ─────────────────────────────────────────────

USER_ID = "f62c3d4e-8373-4de5-9aa8-57facebdb001"
CURRENCY_ID = "e3f9d656-5c09-46ae-ac17-0592bcca4ddc"  # INR

ACCOUNTS = {
    "hdfc_savings_4319": "4513d259-02bc-4647-91f6-2754e3d3e4a7",
    "hdfc_savings_7710": "af2a508e-1f2f-4f78-bc1c-63d7ed429834",
    "hdfc_savings_6834": "9b67a4d8-e3f2-43ac-9aba-8166cacc0439",
    "icici_credit_4000": "592f36e6-af54-44b4-9f46-5dd94f938702",
    "hdfc_savings_1879": "0b188467-0125-4cd5-8daf-8a6997183391",
    "hdfc_credit_7420":  "fce48cfc-829f-424d-998d-814a9d2d56de",
    "hdfc_savings_6216": "ff2a842a-69b2-4580-a2db-8fdc827db722",
    "hdfc_savings_2383": "17b95b77-9a27-4af9-906e-3b475cd037ad",
}

CATEGORIES = {
    "Housing":              "b600dc65-ead3-4437-b898-50b05c63e93b",
    "Utilities":            "115953d1-34f7-41bb-afb8-8bbaf0388e24",
    "Food":                 "2698e700-68b0-46ea-a812-f81547603d7e",
    "Transport":            "a0250e9f-99d5-44c3-933b-e23d4383fc57",
    "Shopping":             "e3b221b0-6ae0-4595-8f0e-2a512830834c",
    "Subscriptions":        "c3088928-1790-42f3-9338-b1bf58233166",
    "Health":               "1c4fcdf9-f021-4776-a3c8-98e370abcfe0",
    "Entertainment":        "05174f56-9cae-49f9-a7b0-d215dd59e6ed",
    "Travel":               "2bcd61e5-f4e4-478d-9e85-9b4d73493545",
    "Personal Care":        "f5ca67b9-d0cb-4d94-8c27-3bcaf6ebf313",
    "Education":            "6d7be686-7e95-4c23-98ff-5ffcc9eda78d",
    "Family":                 "cca72189-04e4-44a7-8cb7-3d3309643c62",
    "Income":               "1f1cd1ad-0a98-46fe-bb92-2fded8ad35b5",
    "Savings":              "5a24168b-ad2e-4442-b17d-92ad45888138",
    "Loans & EMIs":         "dddf8adb-9e78-4be2-a81e-2c9d6c713d91",
    "Loans":                "dddf8adb-9e78-4be2-a81e-2c9d6c713d91",
    "Transfers":            "3759b79b-47f1-4a6b-92e7-5812027f6a19",
    "Fees & Charges":       "0c6c2036-78d1-4f7a-b2e8-f8e92a72c90d",
    "Taxes":                "f04d6902-8779-4080-9978-885d6b330fcc",
    "Donations":            "53dc38ac-e49b-4880-883e-ebf3402b4a81",
    "Miscellaneous":        "febae2ab-9e5f-4f94-bae5-e6013ac65432",
}

# ─────────────────────────────────────────────
# Realism helpers  (also imported by synthetic_data_seeder.py)
# ─────────────────────────────────────────────

def drift_day(base_day: int, spread: int = 2) -> int:
    """Human-like date drift around a base day."""
    drift = random.choice([-spread, -(spread - 1), 0, 0, spread - 1, spread])
    return max(1, min(28, base_day + drift))


def sticky_amount(base: float, volatility: float = 0.12, round_to: int = 10) -> float:
    """Amount stays close to base with slight random variation."""
    change = random.uniform(-volatility, volatility)
    val = base * (1 + change)
    return round(val / round_to) * round_to


def gaussian_tx_count(mean: int = 45, std: int = 15,
                      min_val: int = 15, max_val: int = 90) -> int:
    """Human-like transaction density per month."""
    return int(max(min_val, min(max_val, random.gauss(mean, std))))


MONTH_MULTIPLIER = {
    8: 1.0,   # Aug
    9: 0.9,
    10: 1.3,  # Diwali
    11: 1.1,
    12: 1.4,  # Year-end
    1: 0.8,
}


def realistic_electricity() -> int:
    """Electricity bill with a realistic price distribution."""
    return random.choices(
        [850, 1100, 1350, 1600, 1850],
        weights=[0.15, 0.30, 0.30, 0.20, 0.05],
    )[0]


# ─────────────────────────────────────────────
# Generator
# ─────────────────────────────────────────────

class TransactionGenerator:
    def __init__(self) -> None:
        self.transactions: list = []
        self.transactors: list = []
        self.transactor_map: dict = {}

    # ── helpers ──────────────────────────────

    def _get_or_create_transactor(self, name: str, source_id: Optional[str] = None) -> str:
        if name in self.transactor_map:
            return self.transactor_map[name]
        tid = str(uuid.uuid4())
        self.transactor_map[name] = tid
        self.transactors.append({"id": tid, "name": name, "source_id": source_id})
        return tid

    # Keep old name for backward-compat
    generate_transactor = _get_or_create_transactor

    def add_transaction(
        self,
        date: datetime,
        amount: float,
        transactor_name: str,
        category: Optional[str],
        description: str,
        tx_type: str = "expense",
        account: str = "hdfc_savings_4319",
        source_id: Optional[str] = None,
    ) -> None:
        tid = self._get_or_create_transactor(transactor_name, source_id)
        cat_id = CATEGORIES.get(category) if category else None
        self.transactions.append({
            "id": str(uuid.uuid4()),
            "amount": amount,
            "type": tx_type,
            "date": date.strftime("%Y-%m-%d %H:%M:%S.000 +0530"),
            "transactor_id": tid,
            "category_id": cat_id,
            "description": description,
            "confidence": 1.0,
            "account_id": ACCOUNTS[account],
        })

    # ── generators ───────────────────────────

    def generate_fixed_recurring(self, start_date: datetime, months: int) -> None:
        """EMIs and fixed subscriptions."""
        print("Generating fixed recurring transactions...")

        # Home loan EMI — PNB Housing
        for m in range(months):
            d = (start_date + timedelta(days=30 * m)).replace(day=drift_day(5))
            self.add_transaction(d, sticky_amount(26200, 0.01, 100),
                                 "PNB Housing Finance Limited", "Loans & EMIs",
                                 f"Home loan EMI - {d.strftime('%b %Y')}",
                                 account="hdfc_savings_4319",
                                 source_id="HDFC7021807230034209")

        # Netflix
        for m in range(months):
            d = (start_date + timedelta(days=30 * m)).replace(day=drift_day(12))
            self.add_transaction(d, 840, "NETFLIX COM", "Subscriptions",
                                 "Netflix monthly subscription",
                                 account="hdfc_credit_7420",
                                 source_id="netflixupi.payu@hdfcbank")
            if random.random() < 0.07:
                self.add_transaction(d + timedelta(days=1), 840, "NETFLIX COM",
                                     "Subscriptions", "Netflix retry charge",
                                     account="hdfc_credit_7420",
                                     source_id="netflixupi.payu@hdfcbank")

        # Spotify
        for m in range(months):
            d = (start_date + timedelta(days=30 * m)).replace(day=drift_day(1))
            self.add_transaction(d, 119, "Spotify", "Subscriptions",
                                 "Spotify monthly subscription",
                                 source_id="spotify@paytm")

        # Amazon Prime
        for m in range(months):
            d = (start_date + timedelta(days=30 * m)).replace(day=drift_day(18))
            self.add_transaction(d, 299, "Amazon Prime", "Subscriptions",
                                 "Amazon Prime monthly subscription",
                                 account="hdfc_credit_7420",
                                 source_id="primevideo@paytm")

        # Google Play
        for m in range(months):
            d = (start_date + timedelta(days=30 * m)).replace(day=drift_day(28))
            self.add_transaction(d, 650, "Google Play", "Subscriptions",
                                 "Google Play subscription",
                                 source_id="googleplay@paytm")

        # Digital Gold SIP
        for m in range(months):
            d = (start_date + timedelta(days=30 * m)).replace(day=drift_day(6))
            self.add_transaction(d, sticky_amount(100, 0.15, 1),
                                 "AuraGold Digital SIP", "Savings",
                                 "Digital gold SIP",
                                 source_id="cf.auragoldapp@mairtel")

        # Mutual Fund SIP — Zerodha
        for m in range(months):
            d = (start_date + timedelta(days=30 * m)).replace(day=drift_day(3))
            self.add_transaction(d, sticky_amount(1000, 0.12, 50),
                                 "Zerodha Broking Limited", "Savings",
                                 "Mutual fund SIP",
                                 source_id="zerodha.rzpiccl.brk@validicici")

    def generate_insurance(self, start_date: datetime, months: int) -> None:
        """Annual and quarterly insurance premiums (for Portfolio page)."""
        print("Generating insurance transactions...")

        # Each entry: (name, category, description, payment_months, day, amount, account, source)
        schedules = [
            # LIC — annual, October
            ("LIC India", "Loans & EMIs", "LIC annual life insurance premium",
             [10], 15, 46800, "hdfc_savings_4319", "licindiaapp@paytm"),
            # Star Health — annual, November
            ("Star Health Insurance", "Health", "Star Health annual family floater premium",
             [11], 20, 22500, "hdfc_savings_4319", "starhealth@paytm"),
            # HDFC Life — quarterly (Oct, Jan)
            ("HDFC Life Insurance", "Loans & EMIs", "HDFC Life quarterly premium",
             [10, 1], 10, 9200, "hdfc_savings_4319", "hdfclife@paytm"),
        ]

        for m in range(months):
            month_date = start_date + timedelta(days=30 * m)
            for name, cat, desc, pay_months, day, amount, account, source in schedules:
                if month_date.month in pay_months:
                    self.add_transaction(
                        month_date.replace(day=day), amount, name, cat, desc,
                        account=account, source_id=source,
                    )

    def generate_semi_monthly_income(self, start_date: datetime, months: int) -> None:
        """Salary and rental income — monthly."""
        print("Generating semi-monthly income...")

        # Rental income — last day of each month
        cur = start_date
        for _ in range(months):
            if cur.month == 12:
                last = cur.replace(year=cur.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                last = cur.replace(month=cur.month + 1, day=1) - timedelta(days=1)
            self.add_transaction(last, 16500, "Mr Sabitha", "Income",
                                 "Rental income", tx_type="income",
                                 source_id="sabipari2674@oksbi")
            cur = last.replace(day=1) if cur.month == 12 else cur.replace(month=cur.month + 1)

        # Salary — 5th of each month
        cur = start_date.replace(day=5)
        for _ in range(months):
            self.add_transaction(cur, 30000, "NIRAIMATHI SANKARASUBRAMANIYAN", "Income",
                                 "Monthly salary", tx_type="income",
                                 source_id="niraimathi@okaxis")
            if cur.month == 12:
                cur = cur.replace(year=cur.year + 1, month=1)
            else:
                cur = cur.replace(month=cur.month + 1)

    def generate_monthly_variable(self, start_date: datetime, months: int) -> None:
        """Family support transfer — 6th of each month."""
        print("Generating monthly variable transactions...")
        cur = start_date.replace(day=6)
        for _ in range(months):
            self.add_transaction(cur, random.randint(8000, 10000),
                                 "SARATHKUMAR SENTHILKUMAR", "Transfers",
                                 "Family support transfer",
                                 source_id="sarath06112003@okaxis")
            if cur.month == 12:
                cur = cur.replace(year=cur.year + 1, month=1)
            else:
                cur = cur.replace(month=cur.month + 1)

    def generate_utilities(self, start_date: datetime, months: int) -> None:
        """LPG, electricity, Google Workspace."""
        print("Generating utility bills...")

        # Indane Gas — ~15th
        for m in range(months):
            d = (start_date + timedelta(days=30 * m)).replace(day=drift_day(15))
            self.add_transaction(d, 1400, "Indane Gas", "Utilities",
                                 "LPG cylinder refill",
                                 source_id="indanegas@paytm")

        # BESCOM electricity — ~7th (seasonal amounts)
        for m in range(months):
            d = (start_date + timedelta(days=30 * m)).replace(day=drift_day(7))
            amt = int(realistic_electricity() * MONTH_MULTIPLIER.get(d.month, 1.0))
            self.add_transaction(d, amt, "BESCOM", "Utilities",
                                 f"Electricity bill for {d.strftime('%B %Y')}",
                                 source_id="bescom.bill@paytm")

        # Google Workspace — ~4th
        for m in range(months):
            d = (start_date + timedelta(days=30 * m)).replace(day=drift_day(4))
            self.add_transaction(d, 2262.43, "GOOGLEWORKSP", "Subscriptions",
                                 "Google Workspace monthly subscription",
                                 account="hdfc_credit_7420",
                                 source_id="googleworkspace@paytm")

    def generate_monthly_healthcare(self, start_date: datetime, months: int) -> None:
        """Regular pharmacy and fitness expenses."""
        print("Generating monthly healthcare...")

        schedules = [
            ("Apollo Pharmacy", 10, 500, 2000, "apollo@paytm", "Monthly medicine purchase"),
            ("Medplus",         22, 400, 1500, "medplus@paytm", "Monthly pharmacy purchase"),
            ("1mg",             25, 300, 1800, "1mg@paytm",     "Monthly medicine order"),
            ("Cult.fit",         1, 1020, 2672, "cultfit@paytm", "Fitness subscription"),
        ]

        for name, base_day, lo, hi, source, desc in schedules:
            cur = start_date.replace(day=base_day)
            for _ in range(months):
                amt = random.choice([1020, 1499, 2672]) if name == "Cult.fit" else random.randint(lo, hi)
                self.add_transaction(cur, amt, name, "Health", desc, source_id=source)
                if cur.month == 12:
                    cur = cur.replace(year=cur.year + 1, month=1)
                else:
                    cur = cur.replace(month=cur.month + 1)

    def generate_credit_card_bills(self, start_date: datetime, months: int) -> None:
        """Monthly credit card bill payments (for CreditCardWidget)."""
        print("Generating credit card bills...")

        # HDFC Credit Card bill — ~15th
        for m in range(months):
            d = (start_date + timedelta(days=30 * m)).replace(day=drift_day(15))
            amt = random.randint(8000, 25000)
            self.add_transaction(d, amt, "HDFC Credit Card", "Fees & Charges",
                                 f"HDFC credit card bill - {d.strftime('%b %Y')}",
                                 account="hdfc_savings_4319",
                                 source_id="hdfccc@hdfcbank")

        # ICICI Credit Card bill — ~5th
        for m in range(months):
            d = (start_date + timedelta(days=30 * m)).replace(day=drift_day(5))
            amt = random.randint(3000, 12000)
            self.add_transaction(d, amt, "ICICI Credit Card", "Fees & Charges",
                                 f"ICICI credit card bill - {d.strftime('%b %Y')}",
                                 account="hdfc_savings_4319",
                                 source_id="icicicc@icicibank")

    def generate_daily_expenses(self, start_date: datetime, months: int) -> None:
        """Randomised daily spend across food, transport, shopping, etc."""
        print("Generating daily expenses...")

        merchants = {
            "Food": [
                ("Swiggy",       "swiggy@paytm",       150,  800),
                ("Zomato",       "zomato@paytm",       150,  800),
                ("McDonald's",   "mcdonalds@paytm",    200,  600),
                ("KFC",          "kfc@paytm",          250,  700),
                ("Domino's Pizza","dominos@paytm",     300, 1000),
                ("Starbucks",    "starbucks@paytm",    200,  500),
                ("Big Bazaar",   "bigbazaar@paytm",    500, 3000),
                ("DMart",        "dmart@paytm",        800, 4000),
            ],
            "Transport": [
                ("Uber",           "uber@paytm",      80,  400),
                ("Ola",            "ola@paytm",       80,  400),
                ("HP Petrol Pump", "hp@paytm",       300, 1000),
                ("Indian Oil",     "iocl@paytm",     300, 1000),
                ("FastTag",        "fastag@paytm",   100,  500),
            ],
            "Shopping": [
                ("Amazon",           "amazon@paytm",          200,  5000),
                ("Flipkart",         "flipkart@paytm",        200,  5000),
                ("Myntra",           "myntra@paytm",          500,  3000),
                ("Reliance Digital", "reliancedigital@paytm", 1000, 10000),
            ],
            "Entertainment": [
                ("BookMyShow",  "bookmyshow@paytm", 200,  800),
                ("PVR Cinemas", "pvr@paytm",        300, 1200),
            ],
            "Personal Care": [
                ("Nykaa",       "nykaa@paytm",      200, 2000),
                ("Lakme Salon", "lakme@paytm",      300, 1800),
                ("Health & Glow","healthglow@paytm", 200, 1500),
            ],
            "Education": [
                ("Udemy",        "udemy@paytm",      500, 3000),
                ("Coursera",     "coursera@paytm",   800, 4000),
                ("Books & More", "books@paytm",      200, 1000),
            ],
        }

        for month in range(months):
            base_date = start_date + timedelta(days=30 * month)
            n = gaussian_tx_count()
            multiplier = MONTH_MULTIPLIER.get(base_date.month, 1.0)

            for _ in range(n):
                day  = random.randint(1, 28)
                hour = random.randint(8, 23)
                minute = random.randint(0, 59)
                tx_date = base_date.replace(day=day, hour=hour, minute=minute)

                category = random.choices(
                    list(merchants.keys()),
                    weights=[38, 18, 28, 8, 5, 3],
                )[0]
                name, source, lo, hi = random.choice(merchants[category])
                amount = int(random.randint(int(lo * 0.9), int(hi * 1.1)) * multiplier)

                account = random.choices(
                    ["hdfc_savings_4319", "hdfc_credit_7420", "hdfc_savings_7710"],
                    weights=[80, 15, 5],
                )[0]
                self.add_transaction(tx_date, amount, name, category,
                                     f"Payment to {name}",
                                     account=account, source_id=source)

                # Occasional same-day duplicate (retry behaviour)
                if random.random() < 0.08:
                    self.add_transaction(
                        tx_date + timedelta(minutes=random.randint(15, 90)),
                        amount + random.randint(-50, 100),
                        name, category, f"Payment to {name}",
                        account=account, source_id=source,
                    )

    def generate_seasonal_patterns(self, start_date: datetime, months: int) -> None:
        """Diwali and year-end seasonal spikes."""
        print("Generating seasonal patterns...")

        for m in range(months):
            d = start_date + timedelta(days=30 * m)

            # October: Diwali
            if d.month == 10:
                base = d.replace(day=20)
                for i in range(10):
                    self.add_transaction(
                        base + timedelta(days=i),
                        random.randint(2000, 10000),
                        random.choice(["Amazon", "Flipkart", "Saravana Stores"]),
                        "Shopping", "Diwali shopping",
                        account="hdfc_credit_7420",
                    )
                for i in range(5):
                    self.add_transaction(
                        base + timedelta(days=i),
                        random.randint(1000, 5000),
                        "Diwali Gifts", "Transfers",
                        "Diwali gift to family/friends",
                    )

            # December: Christmas & New Year
            if d.month == 12:
                base = d.replace(day=24)
                for i in range(7):
                    self.add_transaction(
                        base + timedelta(days=i % 7),
                        random.randint(1000, 5000),
                        random.choice(["Malls", "Restaurants", "Hotels"]),
                        random.choice(["Food", "Shopping", "Entertainment"]),
                        "Year-end celebration",
                        account="hdfc_credit_7420",
                    )

    def generate_uncategorised_large(self, start_date: datetime, months: int) -> None:
        """A handful of recent large expense transactions with no category.

        These feed the UncategorisedTransactionWidget (expense, amount >= ₹5 000, no category).
        Placed in the last two months of the window so they appear in 'recent transactions'.
        """
        print("Generating uncategorised large transactions...")

        recent_base = start_date + timedelta(days=30 * max(0, months - 2))
        entries = [
            (3,  "NEFT/UPI large transfer",         15000, "HDFC NEFT Transfer",    "hdfc_savings_4319"),
            (10, "Unknown UPI payment",              8500,  "PhonePe UPI",           "hdfc_savings_4319"),
            (18, "ATM cash withdrawal",              10000, "ATM Withdrawal",        "hdfc_savings_4319"),
            (22, "Online transfer — untagged",       7500,  "Untagged UPI Transfer", "hdfc_savings_4319"),
            (27, "Bulk payment — vendor",            12000, "Vendor Payment NEFT",   "hdfc_savings_4319"),
        ]

        for day, desc, amount, name, account in entries:
            safe_day = min(day, 28)
            tx_date = recent_base.replace(day=safe_day, hour=random.randint(9, 21),
                                          minute=random.randint(0, 59))
            tid = self._get_or_create_transactor(name)
            self.transactions.append({
                "id": str(uuid.uuid4()),
                "amount": amount,
                "type": "expense",
                "date": tx_date.strftime("%Y-%m-%d %H:%M:%S.000 +0530"),
                "transactor_id": tid,
                "category_id": None,   # intentionally uncategorised
                "description": desc,
                "confidence": 1.0,
                "account_id": ACCOUNTS[account],
            })

    # ── orchestration ────────────────────────

    def generate_all(self, start_date: Optional[datetime] = None,
                     months: int = 6) -> None:
        """Generate all transaction types.

        If *start_date* is None, transactions are generated backwards from the
        current month for *months* months.
        """
        if start_date is None:
            cur = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            for _ in range(months - 1):
                if cur.month == 1:
                    cur = cur.replace(year=cur.year - 1, month=12)
                else:
                    cur = cur.replace(month=cur.month - 1)
            start_date = cur

        self.generate_fixed_recurring(start_date, months)
        self.generate_insurance(start_date, months)
        self.generate_semi_monthly_income(start_date, months)
        self.generate_monthly_variable(start_date, months)
        self.generate_utilities(start_date, months)
        self.generate_monthly_healthcare(start_date, months)
        self.generate_credit_card_bills(start_date, months)
        self.generate_daily_expenses(start_date, months)
        self.generate_seasonal_patterns(start_date, months)
        self.generate_uncategorised_large(start_date, months)

        print(f"\nGenerated {len(self.transactions)} transactions "
              f"across {len(self.transactors)} transactors")

    # ── export ───────────────────────────────

    def export_sql(self, filename: str) -> None:
        """Write SQL INSERT statements for all generated data."""
        mock_accounts = [
            {"id": "4513d259-02bc-4647-91f6-2754e3d3e4a7", "last_four": "4319", "bank": "HDFC Bank",  "type": "savings"},
            {"id": "af2a508e-1f2f-4f78-bc1c-63d7ed429834", "last_four": "7710", "bank": "HDFC Bank",  "type": "savings"},
            {"id": "9b67a4d8-e3f2-43ac-9aba-8166cacc0439", "last_four": "6834", "bank": "HDFC Bank",  "type": "savings"},
            {"id": "592f36e6-af54-44b4-9f46-5dd94f938702", "last_four": "4000", "bank": "ICICI Bank", "type": "credit"},
            {"id": "0b188467-0125-4cd5-8daf-8a6997183391", "last_four": "1879", "bank": "HDFC Bank",  "type": "savings"},
            {"id": "fce48cfc-829f-424d-998d-814a9d2d56de", "last_four": "7420", "bank": "HDFC Bank",  "type": "credit"},
            {"id": "ff2a842a-69b2-4580-a2db-8fdc827db722", "last_four": "6216", "bank": "HDFC Bank",  "type": "savings"},
            {"id": "17b95b77-9a27-4af9-906e-3b475cd037ad", "last_four": "2383", "bank": "HDFC Bank",  "type": "savings"},
        ]

        with open(filename, "w") as f:
            f.write("-- Synthetic Transaction Data\n")
            f.write(f"-- Generated on {datetime.now().strftime('%Y-%m-%d')}\n\n")

            # Accounts
            f.write("-- Accounts\n")
            for acc in mock_accounts:
                f.write(
                    f"INSERT INTO accounts (id, user_id, account_last_four, bank_name, type) "
                    f"VALUES ('{acc['id']}', '{USER_ID}', '{acc['last_four']}', "
                    f"'{acc['bank']}', '{acc['type']}') ON CONFLICT (id) DO NOTHING;\n"
                )

            # Categories
            f.write("\n-- Categories\n")
            seen = set()
            for label, cat_id in CATEGORIES.items():
                if cat_id not in seen:
                    seen.add(cat_id)
                    f.write(
                        f"INSERT INTO categories (id, label) VALUES ('{cat_id}', '{label}') "
                        f"ON CONFLICT (id) DO NOTHING;\n"
                    )

            # Transactors
            f.write("\n-- Transactors\n")
            for t in self.transactors:
                src = f"'{t['source_id']}'" if t["source_id"] else "NULL"
                name = t["name"].replace("'", "''")
                f.write(
                    f"INSERT INTO transactors (id, name, user_id, source_id, picture, label) "
                    f"VALUES ('{t['id']}', '{name}', '{USER_ID}', {src}, NULL, NULL) "
                    f"ON CONFLICT (id) DO NOTHING;\n"
                )

            # Transactions
            f.write("\n-- Transactions\n")
            for tx in self.transactions:
                desc = tx["description"].replace("'", "''")
                cat  = f"'{tx['category_id']}'" if tx["category_id"] else "NULL"
                f.write(
                    f"INSERT INTO transactions "
                    f"(id, amount, transaction_id, type, date, transactor_id, "
                    f"category_id, description, confidence, currency_id, user_id, "
                    f"message_id, account_id) VALUES "
                    f"('{tx['id']}', {tx['amount']}, NULL, '{tx['type']}', "
                    f"'{tx['date']}', '{tx['transactor_id']}', {cat}, "
                    f"'{desc}', {tx['confidence']}, '{CURRENCY_ID}', "
                    f"'{USER_ID}', NULL, '{tx['account_id']}');\n"
                )

    def export_csv(self, trans_file: str, transactor_file: str) -> None:
        """Write CSV files for transactions and transactors."""
        with open(trans_file, "w", newline="") as f:
            fieldnames = ["id", "amount", "transaction_id", "type", "date",
                          "transactor_id", "category_id", "description",
                          "confidence", "currency_id", "user_id", "message_id", "account_id"]
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for tx in self.transactions:
                row = tx.copy()
                row["transaction_id"] = None
                row["currency_id"]    = CURRENCY_ID
                row["user_id"]        = USER_ID
                row["message_id"]     = None
                w.writerow(row)

        with open(transactor_file, "w", newline="") as f:
            fieldnames = ["id", "name", "user_id", "source_id", "picture", "label"]
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for t in self.transactors:
                w.writerow({**t, "user_id": USER_ID, "picture": None, "label": None})


# ─────────────────────────────────────────────
# CLI entry-point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate synthetic FinCoach transaction data")
    parser.add_argument("--months", type=int, default=6, help="Number of months to generate (default: 6)")
    parser.add_argument("--out-dir", default=".", help="Output directory for generated files (default: current dir)")
    args = parser.parse_args()

    out = args.out_dir
    os.makedirs(out, exist_ok=True)

    g = TransactionGenerator()
    g.generate_all(months=args.months)

    sql_path  = os.path.join(out, "synthetic_transactions.sql")
    csv_tx    = os.path.join(out, "synthetic_transactions.csv")
    csv_tr    = os.path.join(out, "synthetic_transactors.csv")

    g.export_sql(sql_path)
    g.export_csv(csv_tx, csv_tr)

    print(f"\n✅ Files written to {out}/")
    print(f"   {sql_path}")
    print(f"   {csv_tx}")
    print(f"   {csv_tr}")
