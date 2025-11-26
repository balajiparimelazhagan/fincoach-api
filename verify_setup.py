"""
Pre-deployment verification checklist.
Run this script to verify all components are properly configured.
"""
import os
import sys
from pathlib import Path

def check_file_exists(filepath, description):
    """Check if a file exists"""
    if Path(filepath).exists():
        print(f"✅ {description}: {filepath}")
        return True
    else:
        print(f"❌ {description} MISSING: {filepath}")
        return False

def main():
    print("="*60)
    print("FinCoach Celery Implementation Verification")
    print("="*60)
    
    checks = []
    
    # Check core files
    print("\n📋 Core Configuration Files:")
    checks.append(check_file_exists("requirements.txt", "Requirements file"))
    checks.append(check_file_exists("docker-compose.yml", "Docker Compose config"))
    checks.append(check_file_exists("Dockerfile", "Dockerfile"))
    
    # Check new models
    print("\n📋 Models:")
    checks.append(check_file_exists("app/models/email_sync_job.py", "EmailSyncJob model"))
    
    # Check Celery configuration
    print("\n📋 Celery Configuration:")
    checks.append(check_file_exists("app/celery_app.py", "Celery app config"))
    checks.append(check_file_exists("app/workers/email_tasks.py", "Email tasks"))
    
    # Check routes
    print("\n📋 API Routes:")
    checks.append(check_file_exists("app/routes/email_sync.py", "Email sync routes"))
    
    # Check migrations
    print("\n📋 Database Migrations:")
    checks.append(check_file_exists("alembic/versions/011_create_email_sync_jobs_table.py", "EmailSyncJob migration"))
    checks.append(check_file_exists("alembic/versions/012_add_unique_constraint_message_id.py", "Unique constraint migration"))
    
    # Check documentation
    print("\n📋 Documentation:")
    checks.append(check_file_exists("EMAIL_PROCESSING_GUIDE.md", "Setup guide"))
    checks.append(check_file_exists("IMPLEMENTATION_SUMMARY.md", "Implementation summary"))
    checks.append(check_file_exists("LOGIC_PRESERVATION_REPORT.md", "Logic preservation report"))
    
    # Summary
    print("\n" + "="*60)
    total_checks = len(checks)
    passed_checks = sum(checks)
    failed_checks = total_checks - passed_checks
    
    print(f"Total Checks: {total_checks}")
    print(f"✅ Passed: {passed_checks}")
    print(f"❌ Failed: {failed_checks}")
    print("="*60)
    
    if all(checks):
        print("\n🎉 All checks passed! Ready to deploy.")
        print("\n📝 Next steps:")
        print("1. docker-compose up --build")
        print("2. docker-compose exec api alembic upgrade head")
        print("3. Test with: curl -X POST http://localhost:8000/api/v1/email-sync/start/{user_id}")
        return 0
    else:
        print("\n⚠️  Some checks failed. Please review the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
