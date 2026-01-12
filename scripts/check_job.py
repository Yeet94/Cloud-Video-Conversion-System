#!/usr/bin/env python3
import sqlite3
import sys

conn = sqlite3.connect('/data/jobs.db')
cursor = conn.cursor()

# Get schema
cursor.execute('PRAGMA table_info(jobs)')
cols = cursor.fetchall()
col_names = [c[1] for c in cols]
print(f"Columns: {col_names}\n")

# Get recent jobs
cursor.execute('SELECT * FROM jobs ORDER BY created_at DESC LIMIT 5')
rows = cursor.fetchall()

print("Recent jobs:")
for row in rows:
    job_dict = dict(zip(col_names, row))
    print(f"\nJob ID: {job_dict.get('id')}")
    print(f"  Status: {job_dict.get('status')}")
    print(f"  Input: {job_dict.get('input_path')}")
    print(f"  Output: {job_dict.get('output_path')}")
    print(f"  Error: {job_dict.get('error_message')}")
    print(f"  Created: {job_dict.get('created_at')}")
