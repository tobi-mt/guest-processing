# Migration Guide - Refactored Guest Database Manager

## Overview
This guide helps you transition from the old monolithic code to the new refactored, modular architecture.

## What Changed?

### Old Structure
```
database.py (593 lines)
  - Schema management
  - Data mapping
  - File reading
  - Database operations
  - All mixed together
```

### New Structure
```
constants.py (150 lines)         - Configuration & constants
data_mapper.py (120 lines)       - Data transformation
file_reader.py (85 lines)        - File I/O operations  
schema_manager.py (140 lines)    - Database schema management
database_refactored.py (270 lines) - Clean database interface
```

## Step-by-Step Migration

### Step 1: Verify Tests Pass
```bash
python test_refactored_modules.py
```

### Step 2: Backup Current Database
```bash
cp guest_database.db guest_database.backup.db
```

### Step 3: Update Database Import (Gradual)

#### Option A: Test Alongside (Recommended)
Keep both versions and test:
```python
# In your code
from database import GuestDatabase as OldDB
from database_refactored import GuestDatabase as NewDB

# Test both
old_db = OldDB()
new_db = NewDB()

# Compare results
old_guests = old_db.get_all_guests()
new_guests = new_db.get_all_guests()
assert len(old_guests) == len(new_guests)
```

#### Option B: Direct Switch
```python
# Before
from database import GuestDatabase

# After
from database_refactored import GuestDatabase
```

### Step 4: Update app.py

Find this line:
```python
from database import GuestDatabase
```

Replace with:
```python
from database_refactored import GuestDatabase
```

###Step 5: Test the Application
```bash
streamlit run src/guest_database_manager/app.py
```

### Step 6: Verify All Features
- ✅ Import CSV files
- ✅ Import Excel files
- ✅ View guest list
- ✅ Search and filter
- ✅ Accept/Reject/Skip guests
- ✅ Send emails
- ✅ View analytics

### Step 7: Replace Old File (Optional)
Once everything works:
```bash
# Backup old file
mv src/guest_database_manager/database.py src/guest_database_manager/database_old.py

# Rename new file
mv src/guest_database_manager/database_refactored.py src/guest_database_manager/database.py
```

## API Compatibility

### All Public Methods Remain the Same
```python
db = GuestDatabase()

# These all work exactly the same:
db.insert_guest(guest_data)
db.update_guest_by_id(guest_id, guest_data)
db.get_guest_by_id(guest_id)
db.get_all_guests()
db.mark_guest_processed(guest_id)
db.accept_guest_with_email(guest_id, message)
db.reject_guest_with_email(guest_id, message)
db.skip_guest(guest_id, reason)
db.get_stats()
db.get_email_stats()
db.import_from_csv(file_path)
db.import_from_excel(file_path)
```

### New Methods Added
```python
# Unified import method (works for both CSV and Excel)
db.import_from_file(file_path)

# Unmark processed guests
db.mark_guest_unprocessed(guest_id)
```

## Benefits of Migration

### 1. Easier Maintenance
- Each module has a single responsibility
- Changes are isolated and safer
- Easier to find and fix bugs

### 2. Better Testing
- Each module can be tested independently
- Faster test execution
- More reliable tests

### 3. Improved Performance
- Reduced redundant operations
- Optimized database queries
- Better error handling

### 4. Enhanced Extensibility
- Easy to add new import formats
- Simple to add new database columns
- Clear pattern for new features

## Troubleshooting

### Import Errors
If you get import errors:
```python
# Make sure you're in the right directory
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
```

### Database Compatibility
The new code works with existing databases:
```python
# Automatic schema migration
db = GuestDatabase("existing_database.db")
# Schema manager will add any missing columns automatically
```

### Performance Issues
If imports are slower:
```python
# The first import may take longer due to schema verification
# Subsequent operations will be faster
```

## Rollback Procedure

If you need to rollback:

### 1. Restore Backup
```bash
cp guest_database.backup.db guest_database.db
```

### 2. Revert Code Changes
```bash
git checkout -- src/guest_database_manager/database.py
git checkout -- src/guest_database_manager/app.py
```

### 3. Restart Application
```bash
streamlit run src/guest_database_manager/app.py
```

## Support

If you encounter issues:

1. Check the test results: `python test_refactored_modules.py`
2. Review the REFACTORING_SUMMARY.md document
3. Check logs in the terminal output
4. Verify database schema: Check column names match expectations

## Next Steps

After successful migration:

1. ✅ Remove old database.py backup
2. ✅ Update documentation
3. ✅ Add unit tests for new features
4. ✅ Consider adding integration tests
5. ✅ Update deployment scripts

## Timeline Recommendation

- **Week 1**: Test refactored modules alongside old code
- **Week 2**: Gradual migration of non-critical features
- **Week 3**: Full migration and testing
- **Week 4**: Monitor and optimize

## Conclusion

The refactored code maintains 100% backward compatibility while providing significant improvements in maintainability, testability, and performance. The migration can be done gradually with minimal risk.
