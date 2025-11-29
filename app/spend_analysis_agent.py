import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from sqlalchemy import create_engine, Column, String, DateTime, Numeric, Boolean, Integer, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# --- Database Configuration ---
DATABASE_URL = "postgresql+asyncpg://postgres:root@db/postgres"  # Replace with your actual DB URL
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()

# --- SQLAlchemy ORM Models ---

class User(Base):
    __tablename__ = "users"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    email = Column(String, nullable=False, unique=True)
    name = Column(String, nullable=True)
    # ... other user fields from 001_create_users_table.py
    created_at = Column(DateTime(timezone=True), server_default=sa.text('now()'), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=sa.text('now()'), nullable=False)

class Category(Base):
    __tablename__ = "categories"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    label = Column(String, nullable=False)
    picture = Column(String, nullable=True)

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    amount = Column(Numeric(10, 2), nullable=False)
    # The transaction_id in the migration was a String, assuming it's an external ID.
    transaction_id = Column(String, nullable=True)
    type = Column(String, nullable=False)  # 'income', 'expense'
    date = Column(DateTime(timezone=True), nullable=False)
    transactor_id = Column(PG_UUID(as_uuid=True), ForeignKey("transactors.id"), nullable=True)
    category_id = Column(PG_UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True)
    description = Column(String, nullable=True)
    confidence = Column(String, nullable=True)
    currency_id = Column(PG_UUID(as_uuid=True), ForeignKey("currencies.id"), nullable=True)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    message_id = Column(String, nullable=True)

class SpendAnalysis(Base):
    __tablename__ = "spend_analysis"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    pattern_name = Column(String, nullable=False)
    category_id = Column(PG_UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True)
    recurrence_type = Column(String, nullable=False)  # monthly | weekly | yearly
    recurrence_interval = Column(Integer, nullable=True)
    source_vendor = Column(String, nullable=True)
    next_prediction_date = Column(DateTime(timezone=True), nullable=False)
    predicted_amount = Column(Numeric(10, 2), nullable=True)
    confidence_score = Column(Numeric(5, 2), nullable=True)  # 0-100
    agent_notes = Column(Text, nullable=True)
    notification_sent = Column(Boolean, server_default="FALSE", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=sa.text('now()'), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=sa.text('now()'), nullable=False)

# --- Helper Functions ---

def extract_vendor_name(description: str) -> Optional[str]:
    """
    Extracts a vendor name from a transaction description.
    This is a basic implementation and can be greatly improved with more sophisticated NLP techniques.
    """
    common_vendors = ["Netflix", "Spotify", "Amazon", "Apple", "Google", "Microsoft", "Hulu", "Gym", "Rent"]
    for vendor in common_vendors:
        if re.search(r'\b' + re.escape(vendor) + r'\b', description, re.IGNORECASE):
            return vendor
    
    # Try to extract words that look like a vendor name
    # e.g., "Starbucks Coffee" -> "Starbucks"
    match = re.match(r'(\w+)', description)
    if match:
        return match.group(1).capitalize()
    
    return None

def calculate_next_prediction_date(
    last_date: datetime, recurrence_type: str, recurrence_interval: int
) -> datetime:
    """
    Calculates the next predicted transaction date based on recurrence.
    """
    if recurrence_type == "monthly":
        # Simple monthly addition, needs to handle month-end dates gracefully
        next_date = last_date + timedelta(days=30 * recurrence_interval) # Approximation
    elif recurrence_type == "weekly":
        next_date = last_date + timedelta(weeks=recurrence_interval)
    elif recurrence_type == "yearly":
        next_date = last_date + timedelta(days=365 * recurrence_interval) # Approximation
    else:
        raise ValueError(f"Unknown recurrence type: {recurrence_type}")
    
    return next_date

def calculate_confidence_score(transaction_count: int, consistency_score: float) -> float:
    """
    Generates a confidence score based on the number of transactions and consistency.
    `consistency_score` could be derived from date regularity, amount consistency, etc.
    """
    score = (transaction_count * 10 + consistency_score * 90) / 100 # Example formula
    return min(100.0, max(0.0, float(score)))

def predict_amount(amounts: List[Decimal]) -> Decimal:
    """
    Estimates the predicted amount based on the median of past amounts.
    """
    if not amounts:
        return Decimal('0.00')
    sorted_amounts = sorted(amounts)
    mid = len(sorted_amounts) // 2
    if len(sorted_amounts) % 2 == 0:
        return (sorted_amounts[mid - 1] + sorted_amounts[mid]) / 2
    else:
        return sorted_amounts[mid]

# --- Core Pattern Detection Logic ---

async def detect_recurring_patterns(
    user_id: UUID, session: AsyncSession, lookback_days: int = 180, amount_tolerance_percent: float = 20.0
) -> List[dict]:
    """
    Detects recurring spending patterns for a given user.
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=lookback_days)

    transactions_data = (
        await session.execute(
            select(Transaction)
            .filter(Transaction.user_id == user_id)
            .filter(Transaction.date >= start_date)
            .filter(Transaction.type == 'expense') # Focus on expenses for spend analysis
            .order_by(Transaction.date)
        )
    ).scalars().all()

    # Group transactions by potential pattern identifiers (vendor, category, rough amount)
    grouped_patterns = {}
    for transaction in transactions_data:
        vendor = extract_vendor_name(transaction.description or "")
        category_id = transaction.category_id
        
        # Create a "fuzzy" key for grouping similar transactions
        # This handles minor amount variations
        fuzzy_amount = round(transaction.amount / Decimal('10.0')) * Decimal('10.0') # Group by tens
        
        key = (vendor, category_id, fuzzy_amount)
        if key not in grouped_patterns:
            grouped_patterns[key] = []
        grouped_patterns[key].append(transaction)
    
    recurring_patterns = []

    for key, transactions in grouped_patterns.items():
        if len(transactions) < 2: # Need at least two transactions to detect a pattern
            continue
        
        # Sort transactions by date for pattern analysis
        transactions.sort(key=lambda t: t.date)

        # Analyze dates and amounts
        dates = [t.date for t in transactions]
        amounts = [t.amount for t in transactions]

        # Check for consistent amount within tolerance
        median_amount = predict_amount(amounts)
        consistent_amounts = all(
            abs((amount - median_amount) / median_amount * 100) <= amount_tolerance_percent
            for amount in amounts if median_amount != 0
        )
        if not consistent_amounts:
            continue # Amounts too varied for a reliable pattern

        # Calculate time differences between transactions
        time_diffs = []
        for i in range(1, len(dates)):
            diff = dates[i] - dates[i-1]
            time_diffs.append(diff)
        
        if not time_diffs:
            continue

        # Determine recurrence type and interval
        avg_diff_days = sum(td.days for td in time_diffs) / len(time_diffs)
        
        recurrence_type = None
        recurrence_interval = None
        
        # Simple heuristics for common recurrence types
        if 28 <= avg_diff_days <= 32: # Roughly monthly
            recurrence_type = "monthly"
            recurrence_interval = 1
        elif 6 <= avg_diff_days <= 8: # Roughly weekly
            recurrence_type = "weekly"
            recurrence_interval = 1
        elif 360 <= avg_diff_days <= 370: # Roughly yearly
            recurrence_type = "yearly"
            recurrence_interval = 1
        
        # Further refinement for recurrence_interval based on avg_diff_days for monthly/weekly/yearly
        if recurrence_type == "monthly":
            recurrence_interval = max(1, round(avg_diff_days / 30))
        elif recurrence_type == "weekly":
            recurrence_interval = max(1, round(avg_diff_days / 7))
        elif recurrence_type == "yearly":
            recurrence_interval = max(1, round(avg_diff_days / 365))

        if not recurrence_type:
            continue # Could not determine a clear recurrence pattern

        # Construct pattern name
        vendor, category_id, _ = key
        pattern_name = f"{vendor or 'Unknown'} {transactions[0].description[:20]} (Recurring)" if vendor else f"{transactions[0].description[:30]} (Recurring)"

        # Calculate confidence score (more sophisticated logic can be added here)
        consistency_score_val = 100.0 if consistent_amounts and all(td.days > 0 for td in time_diffs) else 50.0 # Basic
        confidence_score_val = calculate_confidence_score(len(transactions), consistency_score_val)

        # Predict next date and amount
        next_prediction_date_val = calculate_next_prediction_date(
            dates[-1], recurrence_type, recurrence_interval
        )
        predicted_amount_val = predict_amount(amounts)

        recurring_patterns.append({
            "user_id": user_id,
            "pattern_name": pattern_name,
            "category_id": category_id,
            "recurrence_type": recurrence_type,
            "recurrence_interval": recurrence_interval,
            "source_vendor": vendor,
            "next_prediction_date": next_prediction_date_val,
            "predicted_amount": predicted_amount_val,
            "confidence_score": Decimal(str(confidence_score_val)),
            "agent_notes": f"Detected {recurrence_type} pattern with {len(transactions)} transactions. Average interval: {avg_diff_days:.2f} days.",
        })
    
    return recurring_patterns

# --- Database Insert/Update Logic ---

async def upsert_spend_analysis(
    session: AsyncSession, pattern_data: dict
) -> SpendAnalysis:
    """
    Inserts a new spend analysis record or updates an existing one.
    """
    existing_pattern = (
        await session.execute(
            select(SpendAnalysis)
            .filter(SpendAnalysis.user_id == pattern_data["user_id"])
            .filter(SpendAnalysis.pattern_name == pattern_data["pattern_name"])
            # Consider more robust matching for existing patterns (e.g., source_vendor, recurrence_type)
        )
    ).scalar_one_or_none()

    if existing_pattern:
        # Update existing pattern
        existing_pattern.next_prediction_date = pattern_data["next_prediction_date"]
        existing_pattern.predicted_amount = pattern_data["predicted_amount"]
        existing_pattern.confidence_score = pattern_data["confidence_score"]
        existing_pattern.agent_notes = pattern_data["agent_notes"]
        existing_pattern.updated_at = datetime.now()
        # Reset notification_sent if next_prediction_date has significantly changed
        # or if it's a new prediction for the current cycle
        if existing_pattern.notification_sent and existing_pattern.next_prediction_date.date() > datetime.now().date():
             existing_pattern.notification_sent = False
        
        # Update recurrence details if they've changed
        existing_pattern.recurrence_type = pattern_data["recurrence_type"]
        existing_pattern.recurrence_interval = pattern_data["recurrence_interval"]
        existing_pattern.source_vendor = pattern_data["source_vendor"]
        existing_pattern.category_id = pattern_data["category_id"]

        await session.flush() # Flush to get updated object state
        return existing_pattern
    else:
        # Create new pattern
        new_pattern = SpendAnalysis(**pattern_data)
        session.add(new_pattern)
        await session.flush() # Flush to get ID if needed downstream
        return new_pattern

# --- Main Agent Function ---

async def run_agent(user_id: UUID):
    """
    Main function to run the recurring spend analysis agent for a specific user.
    """
    async with AsyncSessionLocal() as session:
        print(f"Running spend analysis for user: {user_id}")
        
        # 1. Detect recurring patterns
        detected_patterns = await detect_recurring_patterns(user_id, session)
        
        print(f"Detected {len(detected_patterns)} recurring patterns.")

        # 2. Upsert results into spend_analysis table
        for pattern_data in detected_patterns:
            await upsert_spend_analysis(session, pattern_data)
        
        await session.commit()
        print(f"Spend analysis complete for user: {user_id}")

# --- Example Usage (for local testing) ---
# To run this example, you would typically need:
# 1. A running PostgreSQL database with the defined tables and some sample data.
# 2. The 'asyncpg' and 'psycopg2-binary' (or 'psycopg') libraries installed.
# 3. An actual user_id from your database.
if __name__ == "__main__":
    import asyncio
    from sqlalchemy import text # For checking DB connection

    async def test_db_connection():
        async with AsyncSessionLocal() as session:
            try:
                await session.execute(text("SELECT 1"))
                print("Database connection successful!")
            except Exception as e:
                print(f"Database connection failed: {e}")

    async def main():
        await test_db_connection()
        # Replace with a real user ID from your database for testing
        example_user_id = UUID("your-user-id-here") 
        if str(example_user_id) == "your-user-id-here":
            print("Please replace 'your-user-id-here' with an actual user ID from your database.")
            print("You might need to manually add some test transactions for that user.")
        else:
            await run_agent(example_user_id)

    asyncio.run(main())
