#!/usr/bin/env python3
import sys
import os
import time
import psycopg2
from psycopg2 import OperationalError
from urllib.parse import urlparse

def wait_for_db(max_retries=30, delay=1):
    """Wait for database server to be ready (connects to default postgres database)"""
    # Get DATABASE_URL from environment
    database_url = os.getenv("DATABASE_URL", "postgresql://postgres:root@db/postgres")
    
    # Parse the database URL
    parsed = urlparse(database_url)
    
    # Connect to default 'postgres' database to check if server is ready
    # (This database always exists, so we can check server readiness)
    retries = 0
    while retries < max_retries:
        try:
            conn = psycopg2.connect(
                host=parsed.hostname or "db",
                port=parsed.port or 5432,
                user=parsed.username or "postgres",
                password=parsed.password or "root",
                database="postgres"  # Always use default postgres DB to check server readiness
            )
            conn.close()
            print("Database server is ready!")
            return True
        except OperationalError:
            retries += 1
            print(f"Database server is unavailable - waiting... ({retries}/{max_retries})")
            time.sleep(delay)
    
    print("Database connection failed after maximum retries")
    return False

if __name__ == "__main__":
    success = wait_for_db()
    sys.exit(0 if success else 1)

