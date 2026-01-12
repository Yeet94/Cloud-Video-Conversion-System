#!/usr/bin/env python3
import sqlite3

conn = sqlite3.connect('/data/jobs.db')
cursor = conn.cursor()

cursor.execute('SELECT id, status, input_path, output_format, error_message FROM jobs ORDER BY created_at DESC')
rows = cursor.fetchall()

for row in rows:
    print(f"\nJob ID: {row[0]}")
    print(f"  Status: {row[1]}")
    print(f"  Input: {row[2]}")
    print(f"  Output Format: {row[3]}")
    print(f"  Error: {row[4]}")
    print("  ---")
