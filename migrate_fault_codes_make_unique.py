import sqlite3
from db_init import get_connection


def migrate_fault_codes_make_unique():
    conn = get_connection()
    cur = conn.cursor()

    print("Aloitetaan fault_codes-migraatio...")

    cur.execute("PRAGMA foreign_keys = OFF")
    conn.commit()

    try:
        cur.execute("ALTER TABLE fault_codes RENAME TO fault_codes_old")

        cur.execute("""
        CREATE TABLE fault_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            make TEXT DEFAULT 'Yleinen',
            title TEXT NOT NULL,
            description TEXT,
            severity TEXT,
            system TEXT,
            problem_symptoms TEXT,
            mil_status TEXT,
            fail_safe_function TEXT,
            priority TEXT,
            sae_code TEXT
        )
        """)

        cur.execute("""
        INSERT INTO fault_codes (
            id,
            code,
            make,
            title,
            description,
            severity,
            system,
            problem_symptoms,
            mil_status,
            fail_safe_function,
            priority,
            sae_code
        )
        SELECT
            id,
            upper(trim(code)),
            CASE
                WHEN make IS NULL OR trim(make) = '' THEN 'Yleinen'
                ELSE trim(make)
            END,
            title,
            description,
            severity,
            system,
            problem_symptoms,
            mil_status,
            fail_safe_function,
            priority,
            sae_code
        FROM fault_codes_old
        """)

        cur.execute("""
        CREATE UNIQUE INDEX idx_fault_codes_code_make
        ON fault_codes (
            upper(trim(code)),
            lower(trim(coalesce(make, 'Yleinen')))
        )
        """)

        cur.execute("DROP TABLE fault_codes_old")

        conn.commit()
        print("Migraatio valmis ✅")
        print("Sama vikakoodi voi nyt olla usealla merkillä.")

    except Exception as e:
        conn.rollback()
        print("Migraatio epäonnistui ❌")
        print("Virhe:", e)
    finally:
        cur.execute("PRAGMA foreign_keys = ON")
        conn.commit()
        conn.close()


if __name__ == "__main__":
    migrate_fault_codes_make_unique()