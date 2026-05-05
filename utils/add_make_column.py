import sys
import os

project_root = os.path.dirname(os.path.dirname(__file__))

if project_root not in sys.path:
    sys.path.insert(0, project_root)

from db_init import get_connection

conn = get_connection()
cur = conn.cursor()

try:
    cur.execute("ALTER TABLE fault_codes ADD COLUMN make TEXT DEFAULT 'Yleinen';")
    conn.commit()
    print("OK: make-sarake lisätty.")
except Exception as e:
    print("Virhe:", e)

conn.close()