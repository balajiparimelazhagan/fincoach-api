# FinCoach API — Code Quality & Architecture Report

> Audit date: 2026-03-25
> Scope: `/api/app/` — routes, models, services, schemas, celery tasks, utilities

---

## Executive Summary

The backend is a solid FastAPI + SQLAlchemy async application with good foundations: async patterns, a service layer, and dependency injection. However, several **critical** issues (broken async session usage, insecure JWT defaults, token leakage) must be fixed before production. There are also systemic gaps in error handling, testing, and data-access consistency.

---

## Severity Legend

| Level | Meaning |
|---|---|
| 🔴 Critical | Will crash or cause security breach |
| 🟠 High | Significant correctness/performance/security risk |
| 🟡 Medium | Code quality, maintainability, or minor security gap |
| 🟢 Low | Style, polish, minor optimisation |

---

## 1. Critical Issues 🔴

### 1.1 Mixed Async/Sync Session in Celery Tasks
**File**: `app/celery/celery_tasks.py` lines 77–82

```python
sync_db = Session(bind=db.sync_connection())  # ← fails at runtime
pattern_service = PatternService(sync_db)
```

`db` is an `AsyncSession`; calling `.sync_connection()` from a Celery worker context will raise a runtime error. Pattern streak updates — a core feature — silently fail.

**Fix**: Create a separate synchronous session factory for Celery workers, or use `asyncio.run()` with a proper async session.

---

### 1.2 Sync `.query()` API on AsyncSession
**File**: `app/routes/patterns.py` lines 111, 155, 274, 321

```python
pattern = db.query(RecurringPattern).filter(...).first()  # AttributeError
```

`AsyncSession` does not have `.query()`. This is SQLAlchemy 1.x sync API. All four pattern endpoints will crash with `AttributeError`.

**Fix**: Replace with `await db.execute(select(RecurringPattern).where(...))`.

---

### 1.3 Missing `await` on `db.commit()`
**File**: `app/routes/patterns.py` lines 295, 333

```python
db.commit()   # ← should be: await db.commit()
```

Without `await`, commits silently do nothing in async context. Pattern updates are never persisted.

---

### 1.4 Insecure JWT Secret Default
**File**: `app/config.py` line 31

```python
JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
```

If the env var is not set, the fallback is a publicly known string. Any attacker can forge valid JWT tokens.

**Fix**:
```python
JWT_SECRET_KEY: str = os.environ["JWT_SECRET_KEY"]  # raise KeyError if missing
```

---

### 1.5 Auth Tokens Returned in API Response
**File**: `app/schemas/user.py` lines 14–16

```python
access_token: Optional[str] = None
refresh_token: Optional[str] = None
token_expiry: Optional[datetime] = None
```

Tokens exposed in response bodies appear in network logs, browser history, and downstream services. They should never be in a `UserResponse` schema.

**Fix**: Create a separate `TokenResponse` schema only used in the `/auth/token` endpoint, never in user profile endpoints.

---

## 2. High Severity Issues 🟠

### 2.1 O(n) Row Count — Loads All Rows to Count
**File**: `app/services/transaction_service.py` lines 80–84

```python
result = await self.session.execute(stmt)
return len(result.scalars().all())   # fetches ALL rows into memory
```

For users with large transaction histories this causes memory spikes and slow pagination.

**Fix**:
```python
count_stmt = select(func.count()).select_from(stmt.subquery())
result = await self.session.execute(count_stmt)
return result.scalar_one()
```

---

### 2.2 N+1 Queries in Pattern Discovery
**File**: `app/services/pattern_service.py` lines 225–233

Transactor and currency are fetched in separate queries inside a loop that already iterates over patterns. For 10 patterns this is 20+ extra round-trips.

**Fix**: Use `joinedload(RecurringPattern.transactor)` in the initial query.

---

### 2.3 Synchronous `requests` Blocking the Event Loop
**File**: `app/routes/auth.py` lines 157–167

```python
token_response = requests.post("https://oauth2.googleapis.com/token", data={...})
```

`requests` is synchronous. This blocks the entire async event loop during the OAuth callback, freezing all other concurrent requests.

**Fix**: Replace with `httpx.AsyncClient`:
```python
async with httpx.AsyncClient() as client:
    token_response = await client.post(...)
```

---

### 2.4 No Rollback on Service Errors
**File**: `app/services/transaction_service.py` lines 171–180
**File**: `app/routes/transactors.py` lines 138–140

`HTTPException` is re-raised before reaching the `rollback()` in the except block. On failure, the async session may be left in a dirty state.

**Fix**: Wrap multi-step operations in `try/except` with explicit `await db.rollback()` before re-raising.

---

### 2.5 `amount` Typed as `int` in Schema — Loses Decimal Precision
**File**: `app/schemas/transaction_schemas.py` line 97

```python
amount: Optional[int] = None   # DB stores Numeric(10,2)
```

`1500.75` becomes `1500`. Financial data must never silently lose precision.

**Fix**: Use `Optional[Decimal]` or `Optional[float]` with explicit rounding.

---

### 2.6 No Input Length Validation on String Fields
**File**: `app/schemas/transaction_schemas.py` lines 21–22, 35–36

```python
transactor_label: Optional[str] = Field(None)  # no max_length
```

A user can POST a 10 MB label string. Causes database bloat and potential DoS.

**Fix**: Add `max_length` on all free-text fields.

---

### 2.7 Bulk Update Count Incorrectly Reported
**File**: `app/services/transaction_service.py` lines 285–289

`updated_count` only increments for `category_id` changes, not `transactor_label` changes. Response reports wrong count.

---

### 2.8 No Tests
**File**: `tests/` (empty)

The test directory contains only `__init__.py`. There are zero unit, integration, or end-to-end tests. Any refactoring — including fixing the issues above — carries unquantified regression risk.

**Fix**: Add `pytest-asyncio`, mock async sessions, and test at minimum: auth flow, transaction CRUD, pattern discovery, and Celery task logic.

---

### 2.9 Google Credentials Stored Unencrypted in Database
**File**: `app/models/user.py` lines 20–21

```python
google_credentials_json = Column(String, nullable=True)
google_token_pickle = Column(LargeBinary, nullable=True)
```

A database dump exposes full Gmail OAuth credentials. This grants email access for every user.

**Fix**: Encrypt at rest using a secrets vault (AWS Secrets Manager, GCP KMS, or SQLAlchemy-utils `EncryptedType`).

---

### 2.10 Wildcard CORS in Default Config
**File**: `app/config.py` line 15

```python
CORS_ORIGINS: ... = os.getenv("CORS_ORIGINS", "http://localhost,...,*")
```

`*` in production CORS allows any origin to make credentialed requests.

**Fix**: Remove `*` from defaults; require explicit env var in production.

---

## 3. Medium Severity Issues 🟡

### 3.1 Repository Pattern Missing — Business Logic Scattered
Routes, services, Celery tasks, and helpers all contain raw SQLAlchemy queries. Query logic is duplicated (count query appears multiple times). Hard to test, hard to change.

**Fix**: Introduce `TransactionRepository`, `PatternRepository`, etc. as the single data-access layer. Services depend only on repository interfaces.

---

### 3.2 Two Conflicting DB Session Factories
`app/dependencies.py` exports `get_db()` and `app/db.py` exports `get_db_session()`. Routes inconsistently import from both.

**Fix**: Consolidate into one `get_db` in `dependencies.py`; delete the duplicate.

---

### 3.3 No Unit of Work for Multi-Step Operations
Transaction creation → pattern update → streak recalculation spans multiple commits. If any step fails, prior commits cannot be rolled back.

**Fix**: Wrap logical operations in a single session context or implement a Unit of Work pattern.

---

### 3.4 Missing Compound Database Indexes
Frequently filtered column combinations lack indexes:

| Table | Missing Index |
|---|---|
| `transactions` | `(user_id, category_id)` |
| `transactions` | `(user_id, date)` |
| `email_transaction_sync_jobs` | `(user_id, status)` |
| `recurring_patterns` | `(user_id, status)` (exists), `(user_id, direction)` missing |

---

### 3.5 Circular Import — Celery ↔ Services
**File**: `app/services/transaction_handler.py` lines 25–26

```python
from app.celery.celery_tasks import update_recurring_streak  # inside function
```

Function-scoped import is a red flag for circular dependency. Indicates architecture needs restructuring: Celery tasks should depend on services, never the reverse.

---

### 3.6 Celery Task Swallows Errors — No Auto-Retry
**File**: `app/celery/celery_tasks.py` lines 104–107

```python
return {'status': 'error', 'error': str(e)}  # Celery sees SUCCESS
```

Celery marks the task as succeeded. No retry happens. Use `raise self.retry(exc=e)` to engage Celery's retry mechanism.

---

### 3.7 Pagination Offset Unbounded
**File**: `app/routes/accounts.py` lines 54–55

```python
offset: int = Query(default=0, ge=0)  # no upper bound
```

A request with `offset=10000000` causes the database to scan 10 million rows.

**Fix**: Add `le=10000` or use cursor-based pagination.

---

### 3.8 Sensitive PII Logged in Plaintext
Multiple routes log user IDs, emails, and transaction amounts. These appear in log files, APM dashboards, and third-party log aggregators.

**Fix**: Log IDs only (no names, emails, or amounts); add a PII-scrubbing log filter.

---

### 3.9 No Structured (JSON) Logging
Plain `f"string {variable}"` log messages cannot be parsed by log aggregators (Datadog, Loki, CloudWatch).

**Fix**: Use `structlog` or configure `python-json-logger` for JSON output.

---

### 3.10 No Rate Limiting on Auth Endpoints
No throttling on `/auth/google/callback` or `/auth/token`. Susceptible to brute-force or SSRF.

**Fix**: Add `slowapi` or a reverse-proxy rate limit for `/auth/*`.

---

## 4. Low Severity Issues 🟢

| # | File | Issue |
|---|---|---|
| 4.1 | `utils/transaction_serializer.py:21` | `int(transaction.amount)` drops decimal — use `Decimal` |
| 4.2 | `routes/categories.py:7` | `import uuid` unused — `uuid.uuid4()` never called in route |
| 4.3 | `celery/celery_tasks.py:107` | Magic number `30` for retry delay — extract to constant |
| 4.4 | `alembic/versions/` | Migrations 026–031 create then immediately drop the same tables — consolidate |
| 4.5 | `alembic/env.py:82-102` | Seeding script runs inside migration env — separate concerns |
| 4.6 | `models/recurring_pattern.py:69` | `status` column has no DB-level check constraint |
| 4.7 | `celery/email_processing_helper.py:33` | `BATCH_SIZE = 100` hardcoded — make configurable |
| 4.8 | Multiple routes | Inconsistent logging levels (`info` vs `debug`) — define a policy |
| 4.9 | Multiple services | Long methods without docstrings (e.g. `_calculate_month_boundaries`) |
| 4.10 | `routes/patterns.py:217` | `direction` validated against hardcoded list — use Pydantic Enum |

---

## 5. Architecture Recommendations

### 5.1 Layer Separation
Current structure mixes data access into routes. Recommended:

```
routes/          → HTTP in/out only (request parsing, response serialisation)
services/        → business logic, orchestration
repositories/    → all SQLAlchemy queries
schemas/         → Pydantic models for validation and serialisation
models/          → SQLAlchemy ORM models
```

### 5.2 Repository Pattern
```python
class TransactionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def find_by_user(self, user_id: str, ...) -> list[Transaction]:
        stmt = select(Transaction).where(Transaction.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_by_user(self, user_id: str) -> int:
        stmt = select(func.count()).where(Transaction.user_id == user_id)
        return (await self.session.execute(stmt)).scalar_one()
```

### 5.3 Configuration Hardening
```python
# config.py — fail fast on missing secrets
class Settings(BaseSettings):
    JWT_SECRET_KEY: str          # required — no default
    GOOGLE_CLIENT_SECRET: str    # required — no default
    DATABASE_URL: str            # required — no default

    model_config = ConfigDict(env_file=".env", extra="forbid")
```

### 5.4 Async HTTP Client (singleton)
```python
# lifespan context in main.py
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient(timeout=10.0)
    yield
    await app.state.http_client.aclose()
```

---

## 6. Summary Statistics

| Category | Critical 🔴 | High 🟠 | Medium 🟡 | Low 🟢 |
|---|---|---|---|---|
| Security | 2 | 2 | 3 | 0 |
| Correctness | 3 | 4 | 2 | 1 |
| Performance | 0 | 2 | 2 | 1 |
| Architecture | 0 | 1 | 4 | 2 |
| Code Quality | 0 | 1 | 3 | 6 |
| **Total** | **5** | **10** | **14** | **10** |

### Scores (1–10)

| Area | Score | Notes |
|---|---|---|
| Architecture | 6/10 | Good intent; scattered execution |
| Security | 4/10 | Auth solid; credential handling weak |
| Performance | 5/10 | N+1 queries, sync blocking event loop |
| Testing | 1/10 | No tests |
| Code Quality | 6/10 | Consistent style; error handling inconsistent |

---

## 7. Prioritised Fix Order

### Phase 1 — Before Production
1. Fix `await db.commit()` in `patterns.py`
2. Replace `.query()` with async `select()` in `patterns.py`
3. Fix Celery async/sync session confusion
4. Remove JWT default; raise on missing env var
5. Remove tokens from `UserResponse` schema
6. Replace `requests.post` with `httpx.AsyncClient`

### Phase 2 — Next Sprint
7. Add `max_length` to all free-text schema fields
8. Fix `amount` type from `int` to `Decimal`
9. Add `func.count()` for pagination counts
10. Add compound DB indexes
11. Encrypt stored Google credentials
12. Add basic test suite (auth + transaction CRUD)

### Phase 3 — Ongoing
13. Extract Repository layer
14. Consolidate session factory to single `get_db`
15. Add structured JSON logging
16. Add rate limiting on auth routes
17. Implement Celery retry with `raise self.retry(exc=e)`
18. Remove wildcard from CORS defaults
