#!/usr/bin/env python3
"""Examine Excel file structure to understand processing status columns."""

import sys
import pandas as pd
sys.path.insert(0, 'src')

def examine_excel_structure():
    """Examine the structure of the Excel file to understand processing columns."""
    excel_file = "Soulful Guest Questionnaire30072025.xlsx"
    
    print(f"=== Examining Excel File Structure: {excel_file} ===")
    
    try:
        # Read Excel file
        df = pd.read_excel(excel_file)
        
        print(f"Total rows: {len(df)}")
        print(f"Total columns: {len(df.columns)}")
        
        print("\n=== All Column Names ===")
        for i, col in enumerate(df.columns, 1):
            print(f"{i:2d}. {col}")
        
        print("\n=== Sample Data (First 3 Rows) ===")
        # Show first few rows with just key columns
        key_columns = []
        for col in df.columns:
            if any(keyword in col.lower() for keyword in ['name', 'email', 'status', 'process', 'accept', 'reject', 'contact', 'response', 'sent']):
                key_columns.append(col)
        
        if key_columns:
            print("Key columns found:")
            for col in key_columns:
                print(f"- {col}")
            
            print("\nSample data for key columns:")
            print(df[key_columns].head(3).to_string(index=False))
        else:
            print("No processing status columns found. Showing first 5 columns:")
            first_cols = df.columns[:5].tolist()
            print(df[first_cols].head(3).to_string(index=False))
        
        print("\n=== Searching for Processing Indicators ===")
        # Look for columns that might indicate processing status
        processing_indicators = []
        for col in df.columns:
            col_lower = col.lower()
            if any(keyword in col_lower for keyword in ['status', 'process', 'accept', 'reject', 'contact', 'response', 'sent', 'email', 'follow']):
                processing_indicators.append(col)
        
        if processing_indicators:
            print("Potential processing status columns:")
            for col in processing_indicators:
                unique_values = df[col].dropna().unique()
                print(f"- {col}: {list(unique_values)[:10]}")  # Show first 10 unique values
        else:
            print("No obvious processing status columns found.")
            
        # Check if there are any additional columns beyond the standard questionnaire
        standard_cols = ['ID', 'Start time', 'Completion time', 'Email', 'Name', 'Full name']
        additional_cols = [col for col in df.columns if col not in standard_cols and not col.startswith('Do you') and not col.startswith('What') and not col.startswith('Have you') and not col.startswith('Are you') and not col.startswith('Is there')]
        
        if additional_cols:
            print(f"\n=== Non-Standard Columns (potential processing info) ===")
            for col in additional_cols:
                print(f"- {col}")
                # Show sample values
                sample_values = df[col].dropna().head(3).tolist()
                if sample_values:
                    print(f"  Sample values: {sample_values}")
    
    except Exception as e:
        print(f"Error reading Excel file: {e}")

if __name__ == "__main__":
    examine_excel_structure()
