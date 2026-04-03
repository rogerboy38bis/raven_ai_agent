#!/usr/bin/env python3
"""Standalone cleanup script for weight_buffer.db.

Run directly on RPi:
    cd ~/raven-bot/raven_ai_agent/rpi_client
    python3 cleanup_db.py
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / 'weight_buffer.db'

def main():
    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Show current state
    cur.execute("SELECT COUNT(*) FROM submission_history")
    total = cur.fetchone()[0]
    print(f"\nCurrent entries: {total}")

    cur.execute("""
        SELECT barrel_serial, COUNT(*) as cnt, MAX(gross_weight), MIN(gross_weight)
        FROM submission_history
        GROUP BY barrel_serial
        HAVING cnt > 1
        ORDER BY cnt DESC
    """)
    dups = cur.fetchall()
    print(f"Barrels with duplicates: {len(dups)}")
    for row in dups:
        print(f"  {row[0]}: {row[1]} entries, weights {row[3]} - {row[2]} kg")

    # Show what will be deleted
    cur.execute("""
        SELECT id, barrel_serial, gross_weight, timestamp
        FROM submission_history
        WHERE id NOT IN (
            SELECT MAX(id)
            FROM submission_history
            GROUP BY barrel_serial
        )
        ORDER BY barrel_serial, id
    """)
    to_delete = cur.fetchall()
    print(f"\nRows to delete: {len(to_delete)}")

    # Delete duplicates
    confirm = input("\nDelete duplicates, keep latest? [y/N]: ").strip().lower()
    if confirm == 'y':
        cur.execute("""
            DELETE FROM submission_history
            WHERE id NOT IN (
                SELECT MAX(id)
                FROM submission_history
                GROUP BY barrel_serial
            )
        """)
        deleted = cur.rowcount
        conn.commit()
        print(f"Deleted {deleted} rows")

        cur.execute("SELECT COUNT(*) FROM submission_history")
        print(f"Remaining entries: {cur.fetchone()[0]}")

        # Also cleanup pending if needed
        cur.execute("SELECT COUNT(*) FROM weight_buffer")
        pending = cur.fetchone()[0]
        if pending > 0:
            print(f"\nPending submissions: {pending}")
            retry = input("Retry pending? [y/N]: ").strip().lower()
            if retry == 'y':
                # Just show them, actual retry is done via web UI
                cur.execute("SELECT * FROM weight_buffer ORDER BY created_at")
                for row in cur.fetchall():
                    print(f"  {row}")
    else:
        print("Cancelled")

    conn.close()
    print("\nDone!")

if __name__ == '__main__':
    main()
