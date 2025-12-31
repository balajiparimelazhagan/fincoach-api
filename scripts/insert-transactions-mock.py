import csv
import psycopg2
from datetime import datetime

# ======================
# CONFIG
# ======================
DB_CONFIG = {
    "host": "localhost",
    "port": 5434,
    "dbname": "postgres",
    "user": "postgres",
    "password": "root",
}

USER_ID = "110bfb44-99fa-46c0-8b9e-6669ffaa2984"
CSV_PATH = "/Users/balaji/projects/fincoach/api/scripts/transactions-mock.csv"


# ======================
# DB HELPERS
# ======================
def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def get_or_create_transactor(cur, name: str) -> str:
    cur.execute("""
        SELECT id
        FROM transactors
        WHERE user_id = %s
          AND name = %s
        LIMIT 1
    """, (USER_ID, name))
    row = cur.fetchone()
    if row:
        return row[0]

    cur.execute("""
        INSERT INTO transactors (
            user_id,
            name
        )
        VALUES (%s, %s)
        RETURNING id
    """, (USER_ID, name))
    return cur.fetchone()[0]


def get_or_create_account(cur, user_id: str, name: str) -> str:
    # Generate a unique account_last_four based on the name
    account_last_four = str(hash(name) % 10000).zfill(4)
    
    cur.execute("""
        SELECT id
        FROM accounts
        WHERE user_id = %s
          AND account_last_four = %s
        LIMIT 1
    """, (user_id, account_last_four))
    row = cur.fetchone()
    if row:
        return row[0]

    cur.execute("""
        INSERT INTO accounts (
            user_id,
            bank_name,
            account_last_four,
            type
        )
        VALUES (%s, %s, %s, 'savings')
        RETURNING id
    """, (user_id, name, account_last_four))
    return cur.fetchone()[0]


def get_or_create_category(cur, name: str) -> str:
    cur.execute("""
        SELECT id
        FROM categories
        WHERE label = %s
        LIMIT 1
    """, (name,))
    row = cur.fetchone()
    if row:
        return row[0]

    cur.execute("""
        INSERT INTO categories (
            label
        )
        VALUES (%s)
        RETURNING id
    """, (name,))
    return cur.fetchone()[0]


# ======================
# TRANSACTION INSERT
# ======================
def insert_transaction_if_missing(cur, tx):
    cur.execute("""
        INSERT INTO transactions (
            transactor_id,
            account_id,
            category_id,
            amount,
            type,
            description,
            date,
            user_id
        )
        SELECT
            %s, %s, %s, %s, %s, %s, %s, %s
        WHERE NOT EXISTS (
            SELECT 1
            FROM transactions
            WHERE transactor_id = %s
              AND account_id = %s
              AND category_id = %s
              AND amount = %s
              AND type = %s
              AND description = %s
              AND date = %s
        )
    """, (
        tx["transactor_id"],
        tx["account_id"],
        tx["category_id"],
        tx["amount"],
        tx["type"],
        tx["description"],
        tx["date"],
        tx["user_id"],
        # dedup
        tx["transactor_id"],
        tx["account_id"],
        tx["category_id"],
        tx["amount"],
        tx["type"],
        tx["description"],
        tx["date"],
    ))


# ======================
# MAIN
# ======================
def main():
    conn = get_connection()
    conn.autocommit = False

    inserted = 0

    try:
        with conn.cursor() as cur:
            # Create a single account for all transactions
            account_id = get_or_create_account(
                cur, USER_ID, "HDFC Bank"
            )
            
            with open(CSV_PATH, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)

                for row in reader:
                    transactor_id = get_or_create_transactor(
                        cur, row["Transactor"]
                    )

                    category_id = get_or_create_category(
                        cur, row["Category"]
                    )

                    tx = {
                        "transactor_id": transactor_id,
                        "account_id": account_id,
                        "category_id": category_id,
                        "amount": float(row["Amount"]),
                        "type": "debit",
                        "description": row["Transactor"],
                        "date": datetime.strptime(row["Date"], "%d/%m/%Y"),
                        "user_id": USER_ID,
                    }

                    insert_transaction_if_missing(cur, tx)
                    if cur.rowcount > 0:
                        inserted += 1

        conn.commit()
        print(f"✅ Inserted {inserted} new canonical transactions")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()