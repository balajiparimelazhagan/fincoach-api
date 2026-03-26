"""
Synthetic data seeder — loads a complete realistic dataset into the dev/staging database.

Inserts:
  • User, accounts, categories
  • Transactions (6 months of realistic history)
  • Recurring patterns + streaks + obligations  (powers Portfolio, BillsCalendar, Dashboard widgets)
  • User preferences                            (all dashboard toggles on)

Usage:
    python -m scripts.synthetic_data_seeder
    DATABASE_URL=postgresql://... python -m scripts.synthetic_data_seeder
"""

import os
import random
import uuid
from datetime import datetime, timedelta
from typing import Optional

import psycopg2

from scripts.synthetic_data_builder import (
    ACCOUNTS as FIXED_ACCOUNTS,
    CATEGORIES as FIXED_CATEGORIES,
    TransactionGenerator,
    drift_day,
    sticky_amount,
    gaussian_tx_count,
    MONTH_MULTIPLIER,
    realistic_electricity,
)

# ─────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────

DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:root@localhost:5434/postgres",
)
TEST_USER_EMAIL = "user@roobai.ai"

# ─────────────────────────────────────────────────────────────
# Recurring-pattern definitions
#
# Each entry drives:
#   1. A recurring_patterns row
#   2. A recurring_pattern_streaks row
#   3. pattern_obligations rows (FULFILLED ← past, EXPECTED ← future)
#   4. pattern_transactions rows (links actual txns to the pattern)
# ─────────────────────────────────────────────────────────────

RECURRING_PATTERN_CONFIGS: dict = {
    # ── Expense: EMIs & subscriptions ──────────────────────────
    "PNB Housing Finance Limited": {
        "direction": "expense", "pattern_type": "MONTHLY", "interval_days": 30,
        "amount_behavior": "FIXED",    "confidence": 0.97,
        "base_day": 5,  "base_amount": 26200, "tolerance_days": 3,
    },
    "NETFLIX COM": {
        "direction": "expense", "pattern_type": "MONTHLY", "interval_days": 30,
        "amount_behavior": "FIXED",    "confidence": 0.95,
        "base_day": 12, "base_amount": 840,   "tolerance_days": 3,
    },
    "Spotify": {
        "direction": "expense", "pattern_type": "MONTHLY", "interval_days": 30,
        "amount_behavior": "FIXED",    "confidence": 0.98,
        "base_day": 1,  "base_amount": 119,   "tolerance_days": 3,
    },
    "Amazon Prime": {
        "direction": "expense", "pattern_type": "MONTHLY", "interval_days": 30,
        "amount_behavior": "FIXED",    "confidence": 0.98,
        "base_day": 18, "base_amount": 299,   "tolerance_days": 3,
    },
    "Google Play": {
        "direction": "expense", "pattern_type": "MONTHLY", "interval_days": 30,
        "amount_behavior": "FIXED",    "confidence": 0.94,
        "base_day": 28, "base_amount": 650,   "tolerance_days": 3,
    },
    "GOOGLEWORKSP": {
        "direction": "expense", "pattern_type": "MONTHLY", "interval_days": 30,
        "amount_behavior": "FIXED",    "confidence": 0.97,
        "base_day": 4,  "base_amount": 2262,  "tolerance_days": 3,
    },
    # ── Expense: Utilities ───────────────────────────────────
    "BESCOM": {
        "direction": "expense", "pattern_type": "MONTHLY", "interval_days": 30,
        "amount_behavior": "VARIABLE", "confidence": 0.90,
        "base_day": 7,  "base_amount": 1350,  "tolerance_days": 5,
    },
    "Indane Gas": {
        "direction": "expense", "pattern_type": "MONTHLY", "interval_days": 30,
        "amount_behavior": "FIXED",    "confidence": 0.88,
        "base_day": 15, "base_amount": 1400,  "tolerance_days": 5,
    },
    # ── Expense: Family transfer ────────────────────────────
    "SARATHKUMAR SENTHILKUMAR": {
        "direction": "expense", "pattern_type": "MONTHLY", "interval_days": 30,
        "amount_behavior": "VARIABLE", "confidence": 0.93,
        "base_day": 6,  "base_amount": 9000,  "tolerance_days": 4,
    },
    # ── Expense: Savings investments ────────────────────────
    "Zerodha Broking Limited": {
        "direction": "expense", "pattern_type": "MONTHLY", "interval_days": 30,
        "amount_behavior": "VARIABLE", "confidence": 0.92,
        "base_day": 3,  "base_amount": 1000,  "tolerance_days": 3,
    },
    "AuraGold Digital SIP": {
        "direction": "expense", "pattern_type": "MONTHLY", "interval_days": 30,
        "amount_behavior": "FIXED",    "confidence": 0.96,
        "base_day": 6,  "base_amount": 100,   "tolerance_days": 3,
    },
    # ── Expense: Healthcare ─────────────────────────────────
    "Apollo Pharmacy": {
        "direction": "expense", "pattern_type": "MONTHLY", "interval_days": 30,
        "amount_behavior": "VARIABLE", "confidence": 0.85,
        "base_day": 10, "base_amount": 1000,  "tolerance_days": 7,
    },
    "Medplus": {
        "direction": "expense", "pattern_type": "MONTHLY", "interval_days": 30,
        "amount_behavior": "VARIABLE", "confidence": 0.82,
        "base_day": 22, "base_amount": 800,   "tolerance_days": 7,
    },
    "1mg": {
        "direction": "expense", "pattern_type": "MONTHLY", "interval_days": 30,
        "amount_behavior": "VARIABLE", "confidence": 0.80,
        "base_day": 25, "base_amount": 900,   "tolerance_days": 7,
    },
    "Cult.fit": {
        "direction": "expense", "pattern_type": "MONTHLY", "interval_days": 30,
        "amount_behavior": "VARIABLE", "confidence": 0.93,
        "base_day": 1,  "base_amount": 1499,  "tolerance_days": 4,
    },
    # ── Expense: Credit card bills ──────────────────────────
    "HDFC Credit Card": {
        "direction": "expense", "pattern_type": "MONTHLY", "interval_days": 30,
        "amount_behavior": "VARIABLE", "confidence": 0.96,
        "base_day": 15, "base_amount": 15000, "tolerance_days": 3,
    },
    "ICICI Credit Card": {
        "direction": "expense", "pattern_type": "MONTHLY", "interval_days": 30,
        "amount_behavior": "VARIABLE", "confidence": 0.94,
        "base_day": 5,  "base_amount": 7000,  "tolerance_days": 3,
    },
    # ── Expense: Insurance (annual / quarterly — Portfolio page) ──
    "LIC India": {
        "direction": "expense", "pattern_type": "ANNUAL",    "interval_days": 365,
        "amount_behavior": "FIXED",    "confidence": 0.95,
        "base_day": 15, "base_amount": 46800, "tolerance_days": 7,
    },
    "Star Health Insurance": {
        "direction": "expense", "pattern_type": "ANNUAL",    "interval_days": 365,
        "amount_behavior": "FIXED",    "confidence": 0.94,
        "base_day": 20, "base_amount": 22500, "tolerance_days": 7,
    },
    "HDFC Life Insurance": {
        "direction": "expense", "pattern_type": "QUARTERLY", "interval_days": 90,
        "amount_behavior": "FIXED",    "confidence": 0.96,
        "base_day": 10, "base_amount": 9200,  "tolerance_days": 5,
    },
    # ── Income ──────────────────────────────────────────────
    "Mr Sabitha": {
        "direction": "income", "pattern_type": "MONTHLY", "interval_days": 30,
        "amount_behavior": "FIXED",    "confidence": 0.98,
        "base_day": 28, "base_amount": 16500, "tolerance_days": 3,
    },
    "NIRAIMATHI SANKARASUBRAMANIYAN": {
        "direction": "income", "pattern_type": "MONTHLY", "interval_days": 30,
        "amount_behavior": "FIXED",    "confidence": 0.99,
        "base_day": 5,  "base_amount": 30000, "tolerance_days": 3,
    },
}


# ─────────────────────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────────────────────

def get_connection():
    return psycopg2.connect(DB_URL)


def get_or_create_user(cur, email: str) -> str:
    cur.execute("SELECT id FROM users WHERE email = %s LIMIT 1", (email,))
    row = cur.fetchone()
    if row:
        return str(row[0])
    cur.execute(
        "INSERT INTO users (email, google_id, created_at, updated_at) "
        "VALUES (%s, %s, NOW(), NOW()) RETURNING id",
        (email, f"test-{email}"),
    )
    return str(cur.fetchone()[0])


def ensure_accounts(cur, user_id: str) -> dict:
    """Insert the canonical accounts if missing; return name → id mapping."""
    account_meta = [
        ("hdfc_savings_4319", "4319", "HDFC Bank",  "savings"),
        ("hdfc_savings_7710", "7710", "HDFC Bank",  "savings"),
        ("hdfc_savings_6834", "6834", "HDFC Bank",  "savings"),
        ("icici_credit_4000", "4000", "ICICI Bank", "credit"),
        ("hdfc_savings_1879", "1879", "HDFC Bank",  "savings"),
        ("hdfc_credit_7420",  "7420", "HDFC Bank",  "credit"),
        ("hdfc_savings_6216", "6216", "HDFC Bank",  "savings"),
        ("hdfc_savings_2383", "2383", "HDFC Bank",  "savings"),
    ]
    result = {}
    for key, last_four, bank, acct_type in account_meta:
        acct_id = FIXED_ACCOUNTS[key]
        cur.execute("SELECT id FROM accounts WHERE id = %s", (acct_id,))
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO accounts (id, user_id, account_last_four, bank_name, type) "
                "VALUES (%s, %s, %s, %s, %s)",
                (acct_id, user_id, last_four, bank, acct_type),
            )
        result[key] = acct_id
    return result


def ensure_categories(cur) -> None:
    """Insert every category from FIXED_CATEGORIES if it doesn't already exist.

    This guarantees that categories like 'Loans & EMIs' and 'Fees & Charges'
    are present even on a fresh database, so no transactions are skipped for
    a missing category.
    """
    # De-duplicate by id (some labels share the same uuid, e.g. Loans/Loans & EMIs)
    seen: set = set()
    for label, cat_id in FIXED_CATEGORIES.items():
        if cat_id in seen:
            continue
        seen.add(cat_id)
        cur.execute(
            "INSERT INTO categories (id, label) VALUES (%s, %s) "
            "ON CONFLICT (id) DO NOTHING",
            (cat_id, label),
        )


def fetch_categories(cur) -> dict:
    """Return label → id mapping for all categories in the DB."""
    cur.execute("SELECT id, label FROM categories")
    return {row[1]: str(row[0]) for row in cur.fetchall()}


def get_or_create_transactor(cur, user_id: str, name: str) -> str:
    cur.execute(
        "SELECT id FROM transactors WHERE user_id = %s AND name = %s LIMIT 1",
        (user_id, name),
    )
    row = cur.fetchone()
    if row:
        return str(row[0])
    cur.execute(
        "INSERT INTO transactors (user_id, name) VALUES (%s, %s) RETURNING id",
        (user_id, name),
    )
    return str(cur.fetchone()[0])


def insert_transaction(cur, transactor_id: str, account_id: str,
                       category_id: Optional[str], amount: float,
                       tx_type: str, description: str,
                       date: datetime, user_id: str) -> None:
    cur.execute(
        "INSERT INTO transactions "
        "(transactor_id, account_id, category_id, amount, type, description, date, user_id) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (transactor_id, account_id, category_id, amount,
         tx_type, description, date, user_id),
    )


def seed_user_preferences(cur, user_id: str) -> None:
    """Upsert user preferences so all dashboard widgets are visible."""
    prefs = {
        "dashboard": {
            "show_ai_suggestions":    True,
            "show_budget_summary":    True,
            "show_income_expense":    True,
            "show_transaction_list":  True,
            "show_category_breakdown": True,
        }
    }
    import json
    cur.execute("SELECT id FROM user_preferences WHERE user_id = %s LIMIT 1", (user_id,))
    if cur.fetchone():
        cur.execute(
            "UPDATE user_preferences SET ui_preferences = %s, updated_at = NOW() "
            "WHERE user_id = %s",
            (json.dumps(prefs), user_id),
        )
    else:
        cur.execute(
            "INSERT INTO user_preferences (id, user_id, ui_preferences, created_at, updated_at) "
            "VALUES (%s, %s, %s, NOW(), NOW())",
            (str(uuid.uuid4()), user_id, json.dumps(prefs)),
        )


# ─────────────────────────────────────────────────────────────
# Pattern Seeder
# ─────────────────────────────────────────────────────────────

def _advance_month(dt: datetime) -> datetime:
    if dt.month == 12:
        return dt.replace(year=dt.year + 1, month=1)
    return dt.replace(month=dt.month + 1)


class PatternSeeder:
    """Seeds recurring_patterns, streaks, obligations, and pattern_transactions."""

    def __init__(self, cur, user_id: str) -> None:
        self.cur = cur
        self.user_id = user_id

    # ── lookups ──────────────────────────────

    def _get_transactor_id(self, name: str) -> Optional[str]:
        self.cur.execute(
            "SELECT id FROM transactors WHERE user_id = %s AND name = %s LIMIT 1",
            (self.user_id, name),
        )
        row = self.cur.fetchone()
        return str(row[0]) if row else None

    def _get_or_insert_pattern(self, transactor_id: str, cfg: dict) -> Optional[str]:
        """Insert pattern; returns id (or existing id on duplicate)."""
        # Check first — avoids any conflict entirely
        self.cur.execute(
            "SELECT id FROM recurring_patterns "
            "WHERE user_id=%s AND transactor_id=%s AND direction=%s LIMIT 1",
            (self.user_id, transactor_id, cfg["direction"]),
        )
        row = self.cur.fetchone()
        if row:
            return str(row[0])

        pid = str(uuid.uuid4())
        now = datetime.utcnow()
        # Use column list instead of ON CONFLICT ON CONSTRAINT (unique index ≠ named constraint)
        self.cur.execute(
            """
            INSERT INTO recurring_patterns
              (id, user_id, transactor_id, direction, pattern_type,
               interval_days, amount_behavior, status, confidence,
               detected_at, last_evaluated_at, detection_version,
               created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'ACTIVE',%s,%s,%s,1,%s,%s)
            ON CONFLICT (user_id, transactor_id, direction) DO NOTHING
            RETURNING id
            """,
            (pid, self.user_id, transactor_id,
             cfg["direction"], cfg["pattern_type"], cfg["interval_days"],
             cfg["amount_behavior"], cfg["confidence"],
             now, now, now, now),
        )
        row = self.cur.fetchone()
        return str(row[0]) if row else None

    # ── streak ───────────────────────────────

    def _seed_streak(self, pattern_id: str, months_of_data: int) -> None:
        streak = max(1, months_of_data - random.randint(0, 1))
        now = datetime.utcnow()
        self.cur.execute(
            """
            INSERT INTO recurring_pattern_streaks
              (recurring_pattern_id, current_streak_count, longest_streak_count,
               last_actual_date, last_expected_date, missed_count,
               confidence_multiplier, updated_at)
            VALUES (%s,%s,%s,%s,%s,0,0.95,%s)
            ON CONFLICT (recurring_pattern_id) DO NOTHING
            """,
            (pattern_id, streak, streak, now, now, now),
        )

    # ── obligations ──────────────────────────

    def _seed_obligations(self, pattern_id: str, cfg: dict,
                          start_date: datetime, months: int) -> None:
        today = datetime.utcnow().date()
        tol   = cfg["tolerance_days"]
        lo    = cfg["base_amount"] * 0.95
        hi    = cfg["base_amount"] * 1.05
        base_day = cfg.get("base_day", 1)
        pattern_type = cfg["pattern_type"]

        # Build a list of expected dates
        dates: list[datetime] = []

        if pattern_type == "MONTHLY":
            cur = start_date.replace(day=min(base_day, 28))
            for _ in range(months + 2):  # history + 2 future
                dates.append(cur)
                cur = _advance_month(cur).replace(day=min(base_day, 28))

        elif pattern_type == "ANNUAL":
            # 1 year before start_date and 1 year after today
            base = start_date.replace(day=min(base_day, 28))
            dates.append(base.replace(year=base.year - 1))
            dates.append(base)
            dates.append(base.replace(year=base.year + 1))

        elif pattern_type == "QUARTERLY":
            cur = start_date.replace(day=min(base_day, 28))
            for _ in range(4 + 2):   # ~4 quarters history + 2 future
                dates.append(cur)
                cur = cur + timedelta(days=90)

        for exp_date in dates:
            try:
                exp_day = exp_date.date()

                if exp_day < today - timedelta(days=tol):
                    # Past: mostly FULFILLED, 1-in-12 chance MISSED for realism
                    if random.random() < 0.08:
                        status       = "MISSED"
                        fulfilled_at = None
                        days_early   = None
                    else:
                        status       = "FULFILLED"
                        shift        = random.randint(-2, 2)
                        fulfilled_at = exp_date + timedelta(days=shift)
                        days_early   = float(-shift)  # positive = early
                else:
                    status       = "EXPECTED"
                    fulfilled_at = None
                    days_early   = None

                self.cur.execute(
                    """
                    INSERT INTO pattern_obligations
                      (id, recurring_pattern_id, expected_date, tolerance_days,
                       expected_min_amount, expected_max_amount,
                       status, fulfilled_by_transaction_id, fulfilled_at,
                       days_early, created_at, updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,NULL,%s,%s,NOW(),NOW())
                    """,
                    (str(uuid.uuid4()), pattern_id, exp_date, tol,
                     lo, hi, status, fulfilled_at, days_early),
                )
            except Exception as ex:
                print(f"    ⚠ obligation skipped: {ex}")

    # ── pattern_transactions ─────────────────

    def _link_transactions(self, pattern_id: str, transactor_id: str) -> int:
        self.cur.execute(
            "SELECT id FROM transactions WHERE user_id=%s AND transactor_id=%s",
            (self.user_id, transactor_id),
        )
        txns = self.cur.fetchall()
        count = 0
        for (txn_id,) in txns:
            try:
                self.cur.execute(
                    "INSERT INTO pattern_transactions "
                    "(id, recurring_pattern_id, transaction_id, linked_at) "
                    "VALUES (%s,%s,%s,NOW()) ON CONFLICT DO NOTHING",
                    (str(uuid.uuid4()), pattern_id, txn_id),
                )
                count += 1
            except Exception:
                pass
        return count

    # ── entry-point ──────────────────────────

    def seed_all(self, start_date: datetime, months: int) -> None:
        print("\nSeeding recurring patterns, obligations & streaks...")
        for name, cfg in RECURRING_PATTERN_CONFIGS.items():
            # Each pattern is isolated in its own savepoint so a single failure
            # doesn't abort the whole outer transaction.
            self.cur.execute("SAVEPOINT sp_pattern")
            try:
                transactor_id = self._get_transactor_id(name)
                if not transactor_id:
                    print(f"  ⚠  Transactor not found in DB: {name!r} — skipping")
                    self.cur.execute("RELEASE SAVEPOINT sp_pattern")
                    continue

                pattern_id = self._get_or_insert_pattern(transactor_id, cfg)
                if not pattern_id:
                    print(f"  ⚠  Could not create/find pattern for {name!r}")
                    self.cur.execute("RELEASE SAVEPOINT sp_pattern")
                    continue

                self._seed_streak(pattern_id, months)
                linked = self._link_transactions(pattern_id, transactor_id)
                self._seed_obligations(pattern_id, cfg, start_date, months)
                self.cur.execute("RELEASE SAVEPOINT sp_pattern")
                print(f"  ✓  {name:45s} — {linked} txns linked")
            except Exception as exc:
                self.cur.execute("ROLLBACK TO SAVEPOINT sp_pattern")
                self.cur.execute("RELEASE SAVEPOINT sp_pattern")
                print(f"  ✗  {name!r} failed: {exc}")


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

def main(conn=None) -> None:
    close_conn = conn is None
    if close_conn:
        conn = get_connection()
    conn.autocommit = False

    # Calculate start_date (same logic as TransactionGenerator.generate_all)
    MONTHS = 6
    now = datetime.now()
    start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    for _ in range(MONTHS - 1):
        if start_date.month == 1:
            start_date = start_date.replace(year=start_date.year - 1, month=12)
        else:
            start_date = start_date.replace(month=start_date.month - 1)

    try:
        with conn.cursor() as cur:
            # ── 1. User ───────────────────────────────────────────
            print("Creating / fetching user …")
            user_id = get_or_create_user(cur, TEST_USER_EMAIL)
            print(f"  User ID: {user_id}")

            # ── Guard: skip if data already seeded ───────────────
            cur.execute(
                "SELECT COUNT(*) FROM transactions WHERE user_id = %s", (user_id,)
            )
            if cur.fetchone()[0] > 0:
                print("Synthetic data already present — skipping seeder.")
                conn.commit()
                return

            # ── 2. Accounts & categories ──────────────────────────
            print("Ensuring accounts exist …")
            ensure_accounts(cur, user_id)
            print("Ensuring categories exist …")
            ensure_categories(cur)

            # ── 3. Transactions ───────────────────────────────────
            print("Generating transactions …")
            generator = TransactionGenerator()
            generator.generate_all(start_date=start_date, months=MONTHS)

            inv_cat   = {v: k for k, v in FIXED_CATEGORIES.items()}
            id_to_name = {t["id"]: t["name"] for t in generator.transactors}
            categories = fetch_categories(cur)

            inserted = 0
            skipped  = 0
            for tx in generator.transactions:
                # Resolve category
                if tx["category_id"] is None:
                    db_cat_id = None          # intentionally uncategorised
                else:
                    label = inv_cat.get(tx["category_id"])
                    if label is None:
                        skipped += 1
                        continue
                    db_cat_id = categories.get(label)
                    if db_cat_id is None:
                        skipped += 1
                        continue

                # Resolve transactor (create if missing)
                t_name = id_to_name.get(tx["transactor_id"])
                if not t_name:
                    skipped += 1
                    continue
                transactor_id = get_or_create_transactor(cur, user_id, t_name)

                try:
                    tx_date = datetime.strptime(tx["date"], "%Y-%m-%d %H:%M:%S.000 +0530")
                except ValueError:
                    tx_date = datetime.fromisoformat(tx["date"])

                insert_transaction(
                    cur, transactor_id, tx["account_id"], db_cat_id,
                    float(tx["amount"]), tx["type"], tx["description"],
                    tx_date, user_id,
                )
                inserted += 1

            print(f"  Inserted {inserted} transactions ({skipped} skipped)")

            # ── 4. Patterns, streaks, obligations ─────────────────
            seeder = PatternSeeder(cur, user_id)
            seeder.seed_all(start_date, MONTHS)

            # ── 5. User preferences ───────────────────────────────
            print("Seeding user preferences …")
            seed_user_preferences(cur, user_id)

        conn.commit()
        print(f"\n✅  Synthetic data ready for {TEST_USER_EMAIL}")

    except Exception as exc:
        conn.rollback()
        print(f"\n❌  Error: {exc}")
        raise
    finally:
        if close_conn:
            conn.close()


if __name__ == "__main__":
    main()
