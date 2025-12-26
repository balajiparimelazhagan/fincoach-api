# Spending Analysis & Recurring Transaction Detection

**Version:** 1.0  
**Created:** December 21, 2025  
**Purpose:** Design document for flexible recurring transaction detection and budget forecasting

---

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [Core Concepts](#core-concepts)
3. [Use Cases & Examples](#use-cases--examples)
4. [Pattern Detection Algorithm](#pattern-detection-algorithm)
5. [Budget Forecasting](#budget-forecasting)
6. [Configuration](#configuration)
7. [API Design](#api-design)

---

## Problem Statement

### The Challenge

Users have various recurring expenses that don't follow rigid patterns:
- **Variable frequencies**: Not all bills are monthly (28 days, 60 days, 90 days)
- **Variable amounts**: Electricity bills, grocery expenses vary each time
- **Variable dates**: Payments may occur on different dates within a period
- **Mixed patterns**: Some fixed (₹500/month), some variable (₹800-₹1200/month)

### The Goal

1. **Detect recurring transactions** automatically based on periodic presence
2. **Forecast next month's budget** by analyzing historical patterns
3. **Support flexible patterns** that match real-world behavior
4. **Provide actionable insights** for financial planning

---

## Core Concepts

### 1. Period-Based Presence Detection

**Key Insight:** A transaction is "recurring" if the transactor appears regularly in consecutive time periods, **regardless of exact date or amount**.

**Example:**
```
Transactor: Selvam Janaki
- January 1, 2025: ₹16,170
- February 5, 2025: ₹1,660
- March 20, 2025: ₹1,702

Analysis:
✓ Appears in 3 consecutive months
✓ Pattern = Monthly Recurring
✓ Average = ₹6,510 (or median ₹1,702 to handle outliers)
```

### 2. Transactor Labels

**Purpose:** Allow users to nickname transactors for better organization

**Examples:**
- Original: "ACT FIBERNET PVT LTD" → Label: "Home Internet"
- Original: "Selvam Janaki" → Label: "Tenant"
- Original: "TNEB CHENNAI" → Label: "Electricity Bill"

**Implementation:** Store as separate field, don't modify original transactor name (needed for AI extraction accuracy)

### 3. Pattern Types

| Pattern Type | Description | Example |
|-------------|-------------|---------|
| **Fixed-Monthly** | Same amount, monthly | Internet: ₹500 every month |
| **Variable-Monthly** | Different amounts, monthly | Electricity: ₹800-₹1200 monthly |
| **Flexible-Monthly** | Any amount, any date, but monthly presence | Tenant: ₹1600-₹16000, dates vary |
| **Bi-Monthly** | Appears every 2 months | Gas: Every alternate month |
| **Quarterly** | Appears every 3 months | Insurance: Every 3 months |
| **Custom Interval** | Appears at custom intervals | Phone: Every 28 days |

---

## Use Cases & Examples

### Use Case 1: Fixed Recurring Bill (Internet)

**Scenario:** User pays internet bill every 3 months with fixed amount

**Transactions:**
```
2025-01-01: ₹500 → ACT Fibernet
2025-04-01: ₹500 → ACT Fibernet
2025-07-01: ₹500 → ACT Fibernet
2025-10-01: ₹500 → ACT Fibernet
```

**Detection:**
- ✅ Same transactor: ACT Fibernet
- ✅ Appears every 3 months (quarterly pattern)
- ✅ Amount consistent: ₹500 (0% variance)
- ✅ 4 occurrences (≥ 3 minimum)

**Pattern:** Quarterly Recurring, Fixed Amount

**Forecast for 2026:**
- Next due: January 1, 2026
- Expected amount: ₹500
- Confidence: Very High (100% amount consistency, perfect interval)

---

### Use Case 2: Variable Recurring Bill (Electricity)

**Scenario:** Electricity bill comes monthly but amount varies based on usage

**Transactions:**
```
2025-01-15: ₹800 → TNEB Chennai
2025-02-15: ₹1,200 → TNEB Chennai
2025-03-15: ₹950 → TNEB Chennai
2025-04-15: ₹1,100 → TNEB Chennai
2025-05-15: ₹880 → TNEB Chennai
```

**Detection:**
- ✅ Same transactor: TNEB Chennai
- ✅ Appears every month (5 consecutive months)
- ✅ Amount varies: ₹800-₹1,200 (40% variance)
- ✅ Date consistent: ~15th of month (±2 days)

**Pattern:** Monthly Recurring, Variable Amount

**Forecast for June 2025:**
- Next due: June 15, 2025
- Expected amount: ₹986 (average) or ₹950 (median)
- Confidence: High (consistent frequency, expected variance)
- Budget range: ₹800-₹1,200

---

### Use Case 3: Flexible Recurring Payment (Tenant/Family)

**Scenario:** User sends money to tenant/mother monthly, but amount and date vary significantly

**Transactions:**
```
2025-01-01: ₹16,170 → Selvam Janaki
2025-02-05: ₹1,660 → Selvam Janaki
2025-03-20: ₹1,702 → Selvam Janaki
2025-04-10: ₹2,500 → Selvam Janaki
2025-05-25: ₹1,800 → Selvam Janaki
```

**Detection:**
- ✅ Same transactor: Selvam Janaki
- ✅ Appears every month (5 consecutive months)
- ❌ Amount highly variable: ₹1,660-₹16,170 (outlier detected)
- ❌ Date highly variable: 1st to 25th

**Pattern:** Monthly Recurring, Highly Variable

**Forecast for June 2025:**
- Next due: June 2025 (specific date unpredictable)
- Expected amount: ₹1,966 (median, excluding outlier ₹16,170)
- Confidence: Medium (consistent presence, high variance)
- Note: Flag ₹16,170 as potential outlier/one-time expense

---

### Use Case 4: Bi-Monthly Bill (Gas)

**Scenario:** Gas bill comes every 2 months with variable amounts

**Transactions:**
```
2025-01-20: ₹520 → Bharat Gas
2025-03-18: ₹560 → Bharat Gas
2025-05-22: ₹540 → Bharat Gas
2025-07-19: ₹580 → Bharat Gas
```

**Detection:**
- ✅ Same transactor: Bharat Gas
- ✅ Appears in alternate months (4 occurrences)
- ✅ Amount similar: ₹520-₹580 (11% variance)
- ✅ Bi-monthly pattern detected

**Pattern:** Bi-Monthly Recurring, Slightly Variable

**Forecast for September 2025:**
- Next due: September 2025 (mid-month)
- Expected amount: ₹550 (average)
- Confidence: High (consistent bi-monthly pattern)

---

### Use Case 5: Custom Interval (Phone Recharge)

**Scenario:** Phone recharge every 28 days (not monthly!)

**Transactions:**
```
2025-01-01: ₹199 → Airtel
2025-01-29: ₹199 → Airtel (28 days later)
2025-02-26: ₹199 → Airtel (28 days later)
2025-03-26: ₹199 → Airtel (30 days later, slight variance)
2025-04-23: ₹199 → Airtel (28 days later)
```

**Detection:**
- ✅ Same transactor: Airtel
- ✅ Appears every ~28 days (5 occurrences)
- ✅ Amount consistent: ₹199 (0% variance)
- ✅ Custom interval pattern detected (not monthly!)

**Pattern:** 28-Day Recurring, Fixed Amount

**Forecast for Next Recharge:**
- Next due: May 21, 2025 (28 days from last)
- Expected amount: ₹199
- Confidence: Very High (perfect consistency)

---

### Use Case 6: Mixed Transactions (Groceries)

**Scenario:** User shops at same store multiple times per month with varying amounts

**Transactions:**
```
2025-01-05: ₹450 → D-Mart
2025-01-15: ₹1,200 → D-Mart
2025-01-28: ₹850 → D-Mart
2025-02-03: ₹600 → D-Mart
2025-02-18: ₹1,100 → D-Mart
2025-02-25: ₹700 → D-Mart
```

**Detection:**
- ✅ Same transactor: D-Mart
- ✅ Multiple transactions per month
- ❌ No clear interval pattern (3+ times monthly)
- ✅ Appears in consecutive months

**Pattern:** Frequent Variable Transactions (Not traditionally "recurring")

**Insight:**
- Total Jan spending: ₹2,500
- Total Feb spending: ₹2,400
- Average monthly spending: ₹2,450

**Forecast for March 2025:**
- Frequency: 3 transactions expected
- Total spending: ~₹2,450
- Per transaction: ~₹800
- Confidence: Medium (variable pattern)

---

## Pattern Detection Algorithm

### Step 1: Data Preparation

```python
For each transactor:
  1. Fetch all transactions for user
  2. Sort by date (ascending)
  3. Filter minimum 3 transactions
  4. Group by transactor_id
```

### Step 2: Period Bucketing

```python
For each transactor's transactions:
  1. Create monthly buckets (YYYY-MM format)
     Example: 2025-01, 2025-02, 2025-03
  
  2. Aggregate transactions per bucket:
     - Count of transactions
     - Total amount spent
     - Average amount
     - Min/Max amounts
     - Dates of transactions
```

### Step 3: Pattern Recognition

```python
# Monthly Pattern Detection
consecutive_months = count_consecutive_periods(monthly_buckets)
if consecutive_months >= MIN_OCCURRENCES_FOR_RECURRING (3):
    pattern = "Monthly Recurring"
    confidence = calculate_confidence(amount_variance, date_variance)

# Bi-Monthly Pattern Detection
alternate_month_appearances = check_alternate_months(monthly_buckets)
if alternate_month_appearances >= MIN_OCCURRENCES_FOR_RECURRING (3):
    pattern = "Bi-Monthly Recurring"

# Quarterly Pattern Detection
quarterly_appearances = check_quarterly_pattern(monthly_buckets)
if quarterly_appearances >= MIN_OCCURRENCES_FOR_RECURRING (3):
    pattern = "Quarterly Recurring"

# Custom Interval Detection
intervals = calculate_intervals_between_transactions(dates)
avg_interval = mean(intervals)
interval_variance = std_deviation(intervals)

if interval_variance < DATE_VARIANCE_TOLERANCE (5 days):
    if avg_interval == 28:
        pattern = "28-Day Recurring"
    elif avg_interval == 30:
        pattern = "Monthly Recurring"
    elif avg_interval == 60:
        pattern = "Bi-Monthly Recurring"
    elif avg_interval == 90:
        pattern = "Quarterly Recurring"
```

┌─────────────────────────────────────────────────────────────┐
│                     USER REQUEST                             │
│         GET /analytics/recurring-patterns                    │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
         ┌─────────────────────────────┐
         │  API reads from CACHE       │ ← Fast response!
         │  (pattern_service.py)       │
         └─────────────────────────────┘
                       │
         ┌─────────────┴──────────────┐
         │                            │
         ▼                            ▼
    Return Data              trigger_refresh=true?
    (instant)                        │
                                     ▼
                      ┌──────────────────────────────┐
                      │  Celery Task (Async)         │
                      │  detect_recurring_patterns   │
                      └──────────────┬───────────────┘
                                     │
                                     ▼
                      ┌──────────────────────────────┐
                      │  Pattern Detection Helper    │
                      │  (pattern_detection_helper)  │
                      └──────────────┬───────────────┘
                                     │
                                     ▼
                      ┌──────────────────────────────┐
                      │ COORDINATOR                  │
                      │ PatternDetectionCoordinator  │
                      └──────────────┬───────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    │                │                │
                    ▼                ▼                ▼
         ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
         │  AGENT 1     │ │  AGENT 2     │ │  AGENT 3     │
         │  Monthly     │ │  BiMonthly   │ │  Quarterly   │
         │  Detector    │ │  Detector    │ │  Detector    │
         └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
                │                │                │
                └────────────────┼────────────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │  Pattern Detected?     │
                    └────────────┬───────────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
                    ▼                         ▼
         ┌──────────────────┐     ┌──────────────────┐
         │  AGENT 4         │     │  AGENT 5         │
         │  Amount Analyzer │     │  Confidence      │
         │                  │     │  Calculator      │
         └──────────────────┘     └──────────────────┘
                    │                         │
                    └────────────┬────────────┘
                                 │
                                 ▼
                      ┌──────────────────┐
                      │  AGENT 6         │
                      │  Date Predictor  │
                      └──────────┬───────┘
                                 │
                                 ▼
                      ┌──────────────────┐
                      │  Save to Cache   │
                      │  (database)      │
                      └──────────────────┘