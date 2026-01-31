#!/usr/bin/env python3
"""
Fix email mapping by re-importing with Email2 priority
"""

import sys
import os
import pandas as pd

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from guest_database_manager.database import GuestDatabase

def fix_email_mapping():
    """Fix email mapping by re-importing the Excel file with correct priority."""
    print("🔧 Fixing Email Mapping - Prioritizing Email2 Column")
    print("=" * 55)
    
    # Find the Excel file that was recently imported
    excel_files = []
    for file in os.listdir('.'):
        if file.endswith('.xlsx') and 'sample' not in file.lower():
            excel_files.append(file)
    
    if not excel_files:
        # Look for any excel files in subdirectories
        import glob
        excel_files = glob.glob('**/*.xlsx', recursive=True)
        excel_files = [f for f in excel_files if 'sample' not in f.lower()]
    
    if not excel_files:
        print("❌ No Excel files found to re-import")
        return
    
    # Use the first Excel file found
    excel_file = excel_files[0]
    print(f"📂 Found Excel file: {excel_file}")
    
    # Read the Excel file to check columns
    try:
        df = pd.read_excel(excel_file)
        print(f"📊 Excel file has {len(df)} rows and columns: {list(df.columns)}")
        
        # Check if Email2 column exists and has data
        if 'Email2' in df.columns:
            email2_count = df['Email2'].notna().sum()
            print(f"✅ Email2 column found with {email2_count} non-empty values")
            
            # Show sample Email2 values
            print("\\n📧 Sample Email2 values:")
            sample_emails = df[df['Email2'].notna()]['Email2'].head(5).tolist()
            for i, email in enumerate(sample_emails, 1):
                print(f"  {i}. {email}")
        else:
            print("❌ Email2 column not found in Excel file")
            return
        
        # Re-import with the fixed email priority
        print("\\n🔄 Re-importing with Email2 priority...")
        db = GuestDatabase()
        stats = db.import_from_excel(excel_file)
        
        print(f"📈 Import stats: {stats}")
        
        # Check updated emails
        print("\\n📧 Checking updated emails...")
        guests = db.get_all_guests()
        real_emails = [g for g in guests if g.get('email') and g['email'] != 'anonymous' and '@' in g['email']]
        
        print(f"✅ Guests with real emails after fix: {len(real_emails)}")
        
        if len(real_emails) > 0:
            print("\\n📋 Sample guests with real emails:")
            for i, guest in enumerate(real_emails[:5]):
                print(f"  {i+1}. {guest['full_name']} - {guest['email']}")
        
    except Exception as e:
        print(f"❌ Error processing Excel file: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    fix_email_mapping()
