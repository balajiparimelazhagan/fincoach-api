# FinCoach — How Data Flows

> A guided tour from the moment a user taps "Sign in" to the point a transaction lands in the database, patterns are detected, and everything comes back to the screen.

---

## Meet Priya

Priya is a salaried professional who just installed FinCoach. She wants to track her expenses, see her recurring bills, and understand where her money goes each month.

We'll follow **Priya's first session** from start to finish.

---

## Chapter 1 — Priya Signs In

### What she does
Priya taps **Sign in with Google**.

### What happens behind the scenes

The app calls:
```
GET /api/v1/auth/google/signin
```

The server does two things instantly:
1. Generates a **PKCE verifier** — a one-time security secret (think of it as a temporary password that only this login attempt knows).
2. Wraps that secret in a short-lived JWT and sends Priya's browser to Google's login page.

Google authenticates Priya and redirects her back to:
```
GET /api/v1/auth/google/callback?code=abc123&state=<jwt>
```

Now the real work begins.

**The server:**
- Cracks open the `state` JWT to recover the PKCE secret.
- Uses the `code` + secret to fetch Priya's Google tokens via `httpx` (async, non-blocking).
- Verifies the Google ID token to confirm she is who she says she is.
- Extracts: `google_id`, `email`, `name`, `picture`, `access_token`, `refresh_token`.

**The database check:**
```sql
SELECT * FROM users WHERE google_id = 'google-uid-priya' LIMIT 1;
```

First time? No row found. The server creates one:
```
users table
┌─────────────────────────────────────────────────────────────┐
│ id            │ 550e8400-e29b-41d4-a716-446655440000        │
│ email         │ priya@gmail.com                             │
│ name          │ Priya Sharma                                │
│ google_id     │ 117463829174639281746                       │
│ picture       │ https://lh3.googleusercontent.com/...       │
│ access_token  │ ya29.xxx (Google OAuth token)               │
│ refresh_token │ 1//xxx                                      │
│ created_at    │ 2026-03-15 10:23:00                         │
└─────────────────────────────────────────────────────────────┘
```

The server mints **two tokens** for Priya:

```
Access token  — short-lived (30 min), used on every API call
Refresh token — long-lived (7 days), used only to get a new access token
```

Both are JWTs signed with the same secret key, but the refresh token carries an extra `"type": "refresh"` claim so the two can never be swapped accidentally.

They travel to the frontend together as URL query params on the redirect:
```
/dashboard?token=<access_token>&refresh_token=<refresh_token>
```

The app saves both to device storage (Capacitor Preferences on mobile, localStorage on web). Every subsequent API call carries the access token in the `Authorization: Bearer <token>` header.

**As a final step**, it fires off a background job without making Priya wait:
```python
fetch_user_emails_initial.delay(user_id="550e...", months=3)
```

Priya sees the dashboard immediately. The inbox import runs in the background.

---

## Chapter 2 — Her Gmail is Scanned in the Background

Priya's Gmail has three months of bank emails. This is a lot of work, so the system splits it into **monthly batches** using Celery (the background job system).

### Job creation

Three rows land in the database:
```
email_transaction_sync_jobs table
┌────────────┬────────────┬─────────┬──────────────────────┐
│ id         │ user_id    │ status  │ date_range           │
├────────────┼────────────┼─────────┼──────────────────────┤
│ job-jan-01 │ 550e...    │ PENDING │ Jan 1 – Jan 31       │
│ job-feb-01 │ 550e...    │ PENDING │ Feb 1 – Feb 28       │
│ job-mar-01 │ 550e...    │ PENDING │ Mar 1 – Mar 31       │
└────────────┴────────────┴─────────┴──────────────────────┘
```

The first job starts immediately. Jobs 2 and 3 queue behind it.

### Processing one month

A Celery worker picks up `job-jan-01` and:

1. **Marks it `PROCESSING`** in the database.
2. **Connects to Gmail** using Priya's stored credentials and fetches all bank-related emails between Jan 1 and Jan 31.
3. **Processes emails in batches of 100** — parsing each one through an AI coordinator that extracts transaction data:
   ```
   Email subject: "HDFC Bank: Rs.2,450 debited from a/c XX4521"

   Extracted →
     amount:      2450.00
     type:        expense
     date:        2026-01-07
     transactor:  HDFC Bank
     account:     last-four: 4521
     description: Debit alert
   ```

4. **For each extracted transaction**, the system does a chain of database lookups and creates records if they don't exist yet.

### The lookup chain for one transaction

```
Step 1 — Find or create the Category
  SELECT * FROM categories WHERE label = 'Bank Transfer';
  → Not found. INSERT into categories.

Step 2 — Find or create the Transactor (the merchant/entity)
  SELECT * FROM transactors WHERE source_id = 'HDFC-4521' AND user_id = '550e...';
  → Not found. Try by name:
  SELECT * FROM transactors WHERE name = 'HDFC Bank' AND user_id = '550e...';
  → Not found. INSERT into transactors.

Step 3 — Find or create the Currency
  SELECT * FROM currencies WHERE value = 'INR';
  → Found (INR already exists globally).

Step 4 — Find or create the Account
  SELECT * FROM accounts WHERE account_last_four = '4521' AND user_id = '550e...';
  → Not found. INSERT into accounts.

Step 5 — Insert the Transaction
  INSERT INTO transactions (...) VALUES (...);
```

The transaction row that gets saved:
```
transactions table (one row)
┌───────────────┬──────────────────────────────────────────────┐
│ id            │ txn-abc-001                                  │
│ amount        │ 2450.00                                      │
│ type          │ expense                                      │
│ date          │ 2026-01-07 00:00:00+05:30                    │
│ description   │ Debit alert                                  │
│ transactor_id │ → transactors.id (HDFC Bank row)             │
│ category_id   │ → categories.id (Bank Transfer row)          │
│ currency_id   │ → currencies.id (INR row)                    │
│ account_id    │ → accounts.id (XX4521 row)                   │
│ user_id       │ 550e8400-... (Priya)                         │
│ message_id    │ gmail-msg-id-xyz (prevents duplicates)       │
│ confidence    │ 0.95                                         │
└───────────────┴──────────────────────────────────────────────┘
```

> **Duplicate protection:** The `message_id` is unique. If the same Gmail message is processed twice, the second INSERT fails silently — no duplicate transaction.

5. **Immediately queues a pattern check** (more on this in Chapter 4):
   ```python
   update_recurring_streak.delay(
       user_id="550e...",
       transactor_id="transactor-hdfc-id",
       direction="expense",
       transaction_date="2026-01-07"
   )
   ```

6. **Updates the job's progress** in the database after every batch so Priya can see a live progress indicator.

7. When all emails are done, marks the job `COMPLETED`.

---

## Chapter 3 — Priya Browses Her Transactions

### Request flow for listing transactions

Priya opens the Transactions page. The app calls:
```
GET /api/v1/transactions?limit=20&offset=0&type=expense
Authorization: Bearer <jwt>
```

**Step 1 — Authenticate Priya**

Every request goes through the same guard:
```python
# From the Authorization header, extract the JWT
payload = decode_access_token(token)
user_id = payload["sub"]  # "550e8400-..."

# Look up Priya in the database
SELECT * FROM users WHERE id = '550e8400-...';
```

If the access token is still valid, the request continues normally.

If it has **expired** (after 30 minutes), the server responds:
```json
HTTP 401  { "detail": "Token expired" }
```

The app catches this silently — Priya never sees a login screen. See Chapter 3a for what happens next.

**Step 2 — Build the query**

The route hands the filters to a `TransactionQueryBuilder`:
```python
query = (
    TransactionQueryBuilder(session, user_id="550e...")
    .with_type("expense")          # WHERE type = 'expense'
    # date_from / date_to / amount_min etc. can stack on top
)
```

Each filter method adds one `WHERE` clause. They only activate if a value was actually provided — unused filters are skipped entirely.

**Step 3 — Two database hits**

```sql
-- Count (for pagination header)
SELECT COUNT(*) FROM (
  SELECT id FROM transactions
  WHERE user_id = '550e...' AND type = 'expense'
) AS subquery;
→ 47

-- Fetch page 1
SELECT t.*, tr.*, c.*, a.*
FROM transactions t
LEFT JOIN transactors tr ON t.transactor_id = tr.id
LEFT JOIN categories  c  ON t.category_id   = c.id
LEFT JOIN accounts    a  ON t.account_id    = a.id
WHERE t.user_id = '550e...' AND t.type = 'expense'
ORDER BY t.date DESC
LIMIT 20 OFFSET 0;
```

The `LEFT JOIN`s are done as **eager loads** (`joinedload`) — all related data comes back in one query, not one-per-transaction.

**Step 4 — Serialise and return**

The ORM objects get converted to plain dicts and sent back:
```json
{
  "count": 47,
  "items": [
    {
      "id": "txn-abc-001",
      "amount": 2450.0,
      "type": "expense",
      "date": "2026-01-07T00:00:00+05:30",
      "transactor": { "id": "...", "name": "HDFC Bank", "label": null },
      "category":   { "id": "...", "label": "Bank Transfer" },
      "account":    { "id": "...", "account_last_four": "4521", "bank_name": "HDFC" }
    },
    ...
  ]
}
```

---

## Chapter 3a — The Access Token Expires (Priya Doesn't Notice)

It's been 35 minutes. Priya is still on the Transactions page and pulls to refresh. The app sends the same request with the now-expired access token. The server returns `401 Token expired`.

### What the app does instead of logging her out

The response interceptor in `api.ts` catches the 401 and kicks off a **silent refresh** before Priya sees anything go wrong.

```
App sends:  GET /transactions  → 401 Token expired

Interceptor:
  1. Pauses the failed request
  2. Reads the refresh token from device storage
  3. Calls POST /auth/refresh  →  { refresh_token: "eyJ..." }
```

**The server validates the refresh token:**
```python
# Decode and check that type == "refresh"
payload = decode_refresh_token(request.refresh_token)
user_id  = payload["sub"]

# Confirm the user still exists
SELECT * FROM users WHERE id = user_id;

# Issue a brand-new access token
new_access_token = create_access_token({"sub": user_id, "email": user.email})
```

**Response:**
```json
{ "access_token": "eyJnew...", "token_type": "bearer" }
```

**Back in the app:**
```
  4. Saves the new access token to device storage
  5. Replays the original GET /transactions with the new token
  6. Returns the result as if nothing happened
```

Priya's pull-to-refresh completes normally. She never saw a login screen.

### What if multiple requests expire at the same time?

Say Priya opens the app after being away for an hour. Three API calls fire simultaneously and all get `401`. Without protection, this would trigger three parallel refresh calls — a race condition.

The interceptor handles this with a **queue**:
- The **first** 401 starts the refresh and sets a `isRefreshing = true` flag.
- The **second and third** 401s see the flag and park themselves in a waiting queue.
- Once the refresh succeeds, the queue drains — all three requests retry with the new token in the correct order.

### What if the refresh token itself has expired (after 7 days)?

```
POST /auth/refresh  →  401 "Refresh token expired, please sign in again"
```

This time the app clears both tokens from storage and redirects Priya to the login screen. There is no way around this — the session has truly ended and she needs to sign in again.

---

## Chapter 4 — Priya Updates a Transaction

Priya sees a ₹2,450 debit labelled "Bank Transfer". She knows it's an EMI payment. She taps to re-categorise it, and selects **"All future transactions from HDFC"**.

### What the app sends

```
PATCH /api/v1/transactions/txn-abc-001/bulk
Authorization: Bearer <jwt>

{
  "category_id": "cat-emi-uuid",
  "transactor_label": "Home Loan EMI",
  "update_scope": "current_and_future"
}
```

### What the server does

**Step 1** — Fetch the original transaction (with auth check).

**Step 2** — Determine which transactions to update.

`update_scope: "current_and_future"` means:
```sql
SELECT * FROM transactions
WHERE user_id      = '550e...'
  AND transactor_id = 'transactor-hdfc-id'
  AND date         >= '2026-01-07'  -- the clicked transaction's date
```

This returns every HDFC transaction from January onwards — say, 3 months of EMI payments (Jan, Feb, Mar).

**Step 3** — Apply the updates in memory, then commit once.

```python
for tx in transactions_to_update:       # 3 transactions
    tx.category_id = "cat-emi-uuid"     # Set category on each

original_tx.transactor.label = "Home Loan EMI"   # Rename the transactor once

await session.commit()                  # One atomic write for everything
```

**Step 4** — Respond.

```json
{
  "updated_count": 3,
  "transaction": { "id": "txn-abc-001", "category": { "label": "Home Loan EMI" }, ... }
}
```

Priya sees the label change instantly everywhere — all three months update because the transactor entity itself was renamed.

---

## Chapter 5 — Patterns Are Detected Automatically

After every new transaction is saved, a background job fires:
```python
update_recurring_streak.delay(
    user_id="550e...",
    transactor_id="transactor-hdfc-id",
    direction="expense",
    transaction_date="2026-01-07"
)
```

A Celery worker picks this up and runs the **pattern engine**.

### What the pattern engine does

It looks at all transactions for Priya → HDFC Bank → expense, and asks:
> "Is there a consistent monthly gap between these payments?"

If it finds one — say, payments on the 7th of Jan, Feb, Mar — it records a pattern:

```
recurring_patterns table
┌──────────────────┬───────────────────────────────────────────┐
│ id               │ pat-hdfc-emi-001                          │
│ user_id          │ 550e... (Priya)                           │
│ transactor_id    │ transactor-hdfc-id                        │
│ direction        │ expense                                   │
│ pattern_type     │ MONTHLY                                   │
│ interval_days    │ 30                                        │
│ amount_behavior  │ FIXED                                     │
│ status           │ ACTIVE                                    │
│ confidence       │ 0.91                                      │
└──────────────────┴───────────────────────────────────────────┘
```

And for each upcoming month, it creates an **obligation** (a prediction):
```
pattern_obligations table
┌──────────────┬──────────────────┬────────────┬──────────┐
│ pattern_id   │ expected_date    │ status     │ amount   │
├──────────────┼──────────────────┼────────────┼──────────┤
│ pat-hdfc-... │ 2026-04-07       │ EXPECTED   │ 2450.00  │
│ pat-hdfc-... │ 2026-03-07       │ FULFILLED  │ 2450.00  │
│ pat-hdfc-... │ 2026-02-07       │ FULFILLED  │ 2450.00  │
└──────────────┴──────────────────┴────────────┴──────────┘
```

When the April 7 payment arrives (as a new email), the engine automatically marks that obligation `FULFILLED` and extends the streak — all without Priya doing anything.

---

## Chapter 6 — The Database at a Glance

All the tables referenced in this story, and how they relate:

```
                     ┌─────────┐
                     │  users  │
                     └────┬────┘
          ┌───────────────┼──────────────────┐
          ▼               ▼                  ▼
   ┌─────────────┐  ┌───────────┐  ┌──────────────────────────┐
   │transactions │  │transactors│  │ email_transaction_sync_  │
   └──────┬──────┘  └───────────┘  │ jobs                     │
          │                        └──────────────────────────┘
    ┌─────┼──────────┐
    ▼     ▼          ▼
┌────────┐ ┌──────────┐ ┌──────────┐
│category│ │ accounts │ │currencies│
└────────┘ └──────────┘ └──────────┘

          ┌─────────────────────┐
          │  recurring_patterns │
          └─────────┬───────────┘
                    ▼
        ┌───────────────────────┐
        │  pattern_obligations  │
        └───────────────────────┘
                    ▼
        ┌───────────────────────┐
        │  recurring_pattern_   │
        │  streaks              │
        └───────────────────────┘
```

---

## The Full Journey — One-Page Summary

```
Priya taps "Sign In"
        │
        ▼
Google OAuth → two JWTs minted (access: 30 min, refresh: 7 days)
  → User row created in DB
  → Both tokens saved to device storage
        │
        ▼ (background, Priya doesn't wait)
Celery: 3 monthly email-sync jobs created
        │
        ▼
Gmail API → 90 days of bank emails fetched
        │
        ▼
AI coordinator parses each email
        │
        ▼
For each email:
  Lookup / create → Category
  Lookup / create → Transactor
  Lookup / create → Currency
  Lookup / create → Account
  INSERT           → Transaction (message_id prevents duplicates)
        │
        ▼ (per transaction, in background)
Pattern engine: does HDFC debit happen every ~30 days?
  Yes → INSERT RecurringPattern + PatternObligations
  No  → no action
        │
        ▼
Priya opens the app (30+ minutes later)
  GET /transactions → 401 Token expired
        │
        ▼ (silent, Priya doesn't see this)
  POST /auth/refresh → validate refresh token → new access token
  GET /transactions retried → SELECT + eager-load joins → JSON response
        │
        ▼
Priya re-categorises "Bank Transfer" as "Home Loan EMI"
  PATCH /transactions/:id/bulk (scope: current_and_future)
  → SELECT matching transactions
  → UPDATE category_id on each
  → RENAME transactor.label
  → COMMIT
  → Return updated_count: 3
        │
        ▼
7 days later — refresh token expires
  Next API call → 401 from /auth/refresh
  → Both tokens cleared → Priya redirected to login
```

---

## A Few Things Worth Knowing

**Sessions last 7 days without interruption.** The access token (30 min) keeps the server load-light — short-lived tokens mean a compromised token stops working quickly. The refresh token (7 days) means Priya doesn't have to sign in again every half-hour. When both expire, a full Google sign-in is required.

**The two tokens cannot be mixed up.** The refresh token carries a `"type": "refresh"` claim. If someone tries to use a refresh token as a regular API bearer token, or vice-versa, the server rejects it immediately.

**Concurrent expiry is handled gracefully.** If five API calls fire at once and all hit a 401, only one refresh call goes to the server. The other four park in a queue and replay automatically once the new token arrives. Priya sees a slight delay at most.

**Everything is async.** From the moment a request arrives to the final database write, the server never blocks. It can handle many users simultaneously because it uses Python's `async/await` throughout and a PostgreSQL connection pool (10–20 connections shared across all requests).

**Background work is isolated.** Email parsing, pattern detection, streak updates — none of these block the user's request. They run in Celery workers as separate processes. If one fails, it retries automatically.

**Relationships are loaded in one shot.** When fetching a transaction, the database joins its transactor, category, and account in a single query. No round-tripping to the database once per relationship.

**Idempotency is built in.** Gmail `message_id` is stored as a unique key. Running the same import twice produces no duplicates.

**Patterns are deterministic.** No AI guesses whether your HDFC debit is recurring — the engine looks at actual gaps between real dates and computes a confidence score mathematically.
