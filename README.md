# FinCoach API

FinCoach is an AI-powered financial coaching application designed to help gig economy workers like Ravi, a Rapido bike taxi rider, manage their unpredictable income and build better financial habits.

## About FinCoach

### The Problem

Gig economy workers face unique financial challenges:
- **Unpredictable Income**: Earnings fluctuate based on ride demand, platform incentives, and seasonal patterns
- **Expense Management**: Manual tracking of cash-based and informal transactions is difficult
- **Financial Organization**: Struggling to balance fuel costs, rent, maintenance, and tax-related expenses
- **Lack of Emergency Funds**: No safety net for income dips or unexpected expenses
- **Inconsistent Money Habits**: Difficulty maintaining financial discipline without structured guidance

### Key Features

#### 1. Income Prediction
AI-powered forecasting analyzes patterns from gig platform data and income-related emails to predict daily and monthly earnings. This helps users anticipate busy and slow periods, enabling proactive financial planning.

#### 2. Smart Expense Tracking via Email Parsing
Instead of direct bank integration, users grant secure permission for the app to access financial transaction emails. The system automatically parses transaction alerts and receipts, extracting:
- Transaction amounts and dates
- Recipients and merchants
- Transaction categories (fuel, loan, food, etc.)

This provides automated, real-world expense tracking without requiring bank connections.

#### 3. AI Financial Coach
Personalized coaching tips are delivered based on parsed transaction data and user behavior patterns. The coach provides actionable advice on:
- Optimizing ride timing for better earnings
- Fuel savings strategies
- Emergency fund building
- Financial awareness improvements

#### 4. Streaks & Badges (Gamification)
- **Daily Streaks**: Encourages consistent logging of cash expenses and spending reviews
- **Achievement Badges**: Celebrates financial milestones and positive habits
- **Social Motivation**: Fosters engagement through gamified financial management

#### 5. Emergency Savings Automation
The app intelligently suggests or automatically moves small sums from higher earning days into an emergency fund. Users can set goals (e.g., ₹12,000 for rent and fuel) and receive guidance on using the fund only for critical needs.

### User Journey

#### Onboarding
1. Welcome with clear, friendly onboarding experience
2. Set savings goals (e.g., ₹12,000 emergency fund)
3. Grant secure email permission for transaction tracking
4. Optionally connect gig platform data (e.g., Rapido)
5. Configure notification and privacy preferences

#### Daily Use
- Check income predictions and streak progress
- View personalized coaching tips based on spending/earning activity
- Optionally add manual expense entries
- Review parsed transaction summaries from email data

#### Weekly Use
- Review spending categories and income trends with visualizations
- Receive personalized financial plans based on income fluctuations
- Track progress against savings goals
- Earn achievement badges for milestones
- Share progress or seek help from community features

## Setup

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- PostgreSQL (via Docker)

### Installation

1. Clone the repository
2. Copy `.env.example` to `.env` and configure your environment variables:
   ```bash
   cp .env.example .env
   ```

3. Start the application using Docker Compose:
   ```bash
   docker-compose up --build
   ```

The API will be available at `http://localhost:8000`

### Environment Variables

- `DATABASE_URL`: PostgreSQL connection string
- `CORS_ORIGINS`: Comma-separated list of allowed CORS origins

See `.env.example` for default values.

## API Documentation

Once the application is running, you can access:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Development

### Running Locally

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set up environment variables in `.env`

3. Run the application:
   ```bash
   uvicorn app.main:app
   ```

Note: The container runs uvicorn without auto-reload by default to avoid scanning `.git` and other large directories. For local development, run `uvicorn app.main:app` or use your preferred dev server configuration.

## Project Structure

```
app/
├── __init__.py
├── main.py          # FastAPI application
├── config.py        # Configuration settings
├── db.py            # Database connection
├── exceptions.py    # Custom exceptions
├── models/          # SQLAlchemy models
├── routes/          # API routes
└── services/        # Business logic
```

## Health Check

Check API health:
```bash
curl http://localhost:8000/health
```
