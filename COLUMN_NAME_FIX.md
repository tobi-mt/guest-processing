# Database Column Name Fix

## Issue
The dashboard was crashing with:
```
sqlite3.OperationalError: no such column: created_at
```

## Root Cause
- The code in `database.py` and `app.py` was trying to use column name `created_at`
- The actual database table uses column name `date_added`
- This mismatch caused SQL queries to fail

## Solution
Updated the following files to use the correct column names:

### 1. `/src/guest_database_manager/database.py`
- Changed `ORDER BY created_at DESC` → `ORDER BY date_added DESC` (2 locations)

### 2. `/src/guest_database_manager/app.py`  
- Changed `row.get("created_at")` → `row.get("date_added")`
- Updated comment and display logic accordingly

## Verification
✅ All database queries now work correctly:
- `get_all_guests()` - Returns 135 guests
- `get_guests_by_status(True)` - Returns 117 processed guests  
- `get_guests_by_status(False)` - Returns 18 unprocessed guests

## Status
✅ **Dashboard is now working correctly at http://localhost:8052**

The database schema mismatch has been resolved and all functionality is restored.
