# Import Fix Applied

## Issue
The API was failing to start with:
```
ImportError: cannot import name 'get_session' from 'app.db'
```

## Root Cause
The function in `app/db.py` is named `get_db_session`, not `get_session`.

## Fix Applied
Updated `app/routes/email_sync.py` to use the correct function name:

**Before:**
```python
from app.db import get_session
...
session: AsyncSession = Depends(get_session)
```

**After:**
```python
from app.db import get_db_session
...
session: AsyncSession = Depends(get_db_session)
```

## Files Modified
- `app/routes/email_sync.py` - Changed import and 4 route dependencies

## Status
✅ **Fixed** - API should now start successfully

## Next Steps
Run `docker-compose up --build` to test the fix.
