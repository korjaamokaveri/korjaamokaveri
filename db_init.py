import csv
import os
import re
import sqlite3

import psycopg2
import psycopg2.extras
from psycopg2 import errors

from utils.config import Config

DB_PATH = Config.DB_PATH
DATABASE_URL = os.getenv("DATABASE_URL")


class PostgresCursor:
    def __init__(self, cursor):
        self.cursor = cursor
        self.lastrowid = None

    @property
    def rowcount(self):
        return self.cursor.rowcount

    def _convert_sql(self, sql):
        sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        sql = sql.replace("DATETIME DEFAULT CURRENT_TIMESTAMP", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        sql = sql.replace("DATETIME", "TIMESTAMP")
        sql = sql.replace("REAL", "DOUBLE PRECISION")
        sql = sql.replace("?", "%s")

        if "INSERT OR IGNORE INTO" in sql:
            sql = sql.replace("INSERT OR IGNORE INTO", "INSERT INTO")
            sql = sql.strip()
            if "ON CONFLICT" not in sql.upper():
                sql += " ON CONFLICT DO NOTHING"

        return sql

    def execute(self, sql, params=None):
        params = params or ()

        sql_converted = self._convert_sql(sql)

        # Lisää RETURNING id yksittäisiin INSERT-lauseisiin, jotta lastrowid toimii.
        stripped = sql_converted.strip().lower()
        if (
            stripped.startswith("insert into")
            and "returning" not in stripped
            and "on conflict do nothing" not in stripped
        ):
            sql_converted = sql_converted.rstrip().rstrip(";") + " RETURNING id"

        if (
            stripped.startswith("insert into")
            and "on conflict do nothing" in stripped
            and "returning" not in stripped
        ):
            sql_converted = sql_converted.rstrip().rstrip(";") + " RETURNING id"

        try:
            self.cursor.execute(sql_converted, params)

            self.lastrowid = None
            if sql_converted.strip().lower().startswith("insert into") and "returning id" in sql_converted.lower():
                row = self.cursor.fetchone()
                if row:
                    self.lastrowid = row["id"]

        except errors.DuplicateColumn:
            raise sqlite3.OperationalError("duplicate column")

        except errors.DuplicateTable:
            raise sqlite3.OperationalError("duplicate table")

        except errors.DuplicateObject:
            raise sqlite3.OperationalError("duplicate object")

        return self

    def executemany(self, sql, seq_of_params):
        sql_converted = self._convert_sql(sql)

        if "INSERT OR IGNORE INTO" in sql:
            sql_converted = sql_converted.replace("INSERT OR IGNORE INTO", "INSERT INTO")
            sql_converted = sql_converted.strip()
            if "ON CONFLICT" not in sql_converted.upper():
                sql_converted += " ON CONFLICT DO NOTHING"

        try:
            self.cursor.executemany(sql_converted, seq_of_params)
        except errors.DuplicateColumn:
            raise sqlite3.OperationalError("duplicate column")

        return self

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()


class PostgresConnection:
    def __init__(self, conn):
        self.conn = conn

    def cursor(self):
        return PostgresCursor(
            self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        )

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()


def get_connection():
    if DATABASE_URL:
        conn = psycopg2.connect(DATABASE_URL)
        return PostgresConnection(conn)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
    
def seed_data():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS count FROM fault_codes")
    count = cur.fetchone()["count"]

    if count > 0:
        conn.close()
        return

    cur.execute("""
        INSERT INTO fault_codes (code, title, description, severity, system)
        VALUES (?, ?, ?, ?, ?)
    """, (
        "P0300",
        "Satunnainen sytytyskatkos",
        "Moottorin ohjaus on havainnut satunnaisia sytytyskatkoksia useissa sylintereissä.",
        "medium",
        "engine"
    ))
    p0300_id = cur.lastrowid

    cur.executemany("""
        INSERT INTO possible_causes
        (fault_code_id, cause_name, cause_description, probability_score, priority_order)
        VALUES (?, ?, ?, ?, ?)
    """, [
        (p0300_id, "sytytyspuola", "Viallinen puola voi aiheuttaa sytytyskatkoksia.", 0.40, 1),
        (p0300_id, "sytytystulppa", "Kuluneet tai vioittuneet tulpat voivat aiheuttaa katkoja.", 0.30, 2),
        (p0300_id, "imuvuoto", "Imuvuoto voi sekoittaa seossuhdetta.", 0.20, 3),
        (p0300_id, "polttoainepaine", "Heikko polttoainepaine voi aiheuttaa satunnaista katkosta.", 0.10, 4),
    ])

    cur.executemany("""
        INSERT INTO symptom_matches
        (fault_code_id, keyword, note, weight)
        VALUES (?, ?, ?, ?)
    """, [
        (p0300_id, "nykii", "Nykiminen viittaa usein sytytys- tai seosongelmaan.", 1.2),
        (p0300_id, "tärisee", "Tärinä tukee sytytyskatkoksen mahdollisuutta.", 1.0),
        (p0300_id, "tyhjäkäynti", "Huono tyhjäkäynti voi viitata imuvuotoon tai sytytysongelmaan.", 1.1),
    ])

    cur.executemany("""
        INSERT INTO test_steps
        (fault_code_id, step_order, step_title, step_description, required_tools)
        VALUES (?, ?, ?, ?, ?)
    """, [
        (p0300_id, 1, "Tarkista sytytystulpat", "Irrota ja tarkista tulppien kunto sekä kärkiväli.", "tulppa-avain"),
        (p0300_id, 2, "Tarkista sytytyspuolat", "Tarkista puolien kunto ja vaihda tarvittaessa ristiin.", "yleismittari"),
        (p0300_id, 3, "Tarkista imuvuodot", "Tarkista letkut ja tiivisteet mahdollisten vuotojen varalta.", "savukone / jarrucleaner"),
        (p0300_id, 4, "Mittaa polttoainepaine", "Varmista että polttoainejärjestelmän paine on oikea.", "polttoainepainemittari"),
    ])

    cur.executemany("""
        INSERT INTO vehicle_rules
        (fault_code_id, make, model, engine, year_from, year_to, rule_note, extra_probability_boost)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        (p0300_id, "Volvo", "V70", "2.4", 2000, 2008, "Tässä mallissa sytytyspuolat ovat yleinen aiheuttaja.", 0.15),
        (p0300_id, "Volkswagen", "Passat", "1.8T", 1998, 2005, "Tässä moottorissa imuvuodot ovat tavallisia.", 0.15),
    ])

    cur.execute("""
        INSERT INTO fault_codes (code, title, description, severity, system)
        VALUES (?, ?, ?, ?, ?)
    """, (
        "P0171",
        "Seos liian laiha, pankki 1",
        "Moottori käy liian laihalla seoksella pankissa 1.",
        "medium",
        "fuel"
    ))
    p0171_id = cur.lastrowid

    cur.executemany("""
        INSERT INTO possible_causes
        (fault_code_id, cause_name, cause_description, probability_score, priority_order)
        VALUES (?, ?, ?, ?, ?)
    """, [
        (p0171_id, "imuvuoto", "Ylimääräinen ilma aiheuttaa laihan seoksen.", 0.45, 1),
        (p0171_id, "ilmamassamittari", "Virheellinen mittaus voi vääristää seosta.", 0.25, 2),
        (p0171_id, "alipaineletku", "Vuotava letku voi aiheuttaa saman ilmiön.", 0.20, 3),
        (p0171_id, "polttoainepaine", "Liian alhainen paine voi johtaa laihaan seokseen.", 0.10, 4),
    ])

    cur.executemany("""
        INSERT INTO symptom_matches
        (fault_code_id, keyword, note, weight)
        VALUES (?, ?, ?, ?)
    """, [
        (p0171_id, "nykii", "Laiha seos voi aiheuttaa nykimistä kuormalla.", 1.1),
        (p0171_id, "tehoton", "Tehon puute sopii laihan seoksen vikaan.", 1.0),
        (p0171_id, "tyhjäkäynti", "Epävakaa tyhjäkäynti viittaa usein imuvuotoon.", 1.2),
    ])

    cur.executemany("""
        INSERT INTO test_steps
        (fault_code_id, step_order, step_title, step_description, required_tools)
        VALUES (?, ?, ?, ?, ?)
    """, [
        (p0171_id, 1, "Tarkista imuvuodot", "Käy läpi imupuoli, letkut ja tiivisteet.", "savukone"),
        (p0171_id, 2, "Tarkista alipaineletkut", "Tarkista halkeamat ja irronneet liitokset.", "silmä / käsityökalut"),
        (p0171_id, 3, "Tarkista ilmamassamittari", "Lue arvot testerillä ja vertaa odotettuihin.", "vikakoodinlukija"),
        (p0171_id, 4, "Mittaa polttoainepaine", "Varmista järjestelmän riittävä paine.", "painemittari"),
    ])

    conn.commit()
    conn.close()


def import_dtc_from_csv(file_path):
    conn = get_connection()
    cur = conn.cursor()

    with open(file_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        added = 0

        for row in reader:
            code = (row.get("code") or "").strip()
            title = (row.get("title") or "").strip()
            description = (row.get("description") or "").strip()

            problem_symptoms = (row.get("problem_symptoms") or "").strip()
            mil_status = (row.get("mil_status") or "").strip()
            fail_safe_function = (row.get("fail_safe_function") or "").strip()
            priority = (row.get("priority") or "").strip()
            sae_code = (row.get("sae_code") or "").strip()

            causes = (row.get("causes") or "").strip()
            steps = (row.get("steps") or "").strip()

            if not code:
                continue

            cur.execute("""
                INSERT OR IGNORE INTO fault_codes (
                    code, title, description, severity, system,
                    problem_symptoms, mil_status, fail_safe_function, priority, sae_code
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                code,
                title,
                description,
                "medium",
                description,
                problem_symptoms,
                mil_status,
                fail_safe_function,
                priority,
                sae_code
            ))

            if cur.rowcount == 0:
                continue

            fault_code_id = cur.lastrowid

            if causes:
                for i, c in enumerate(causes.split(";"), start=1):
                    parts = c.split("|")
                    name = parts[0].strip()
                    desc = parts[1].strip() if len(parts) > 1 else ""

                    cur.execute("""
                        INSERT INTO possible_causes
                        (fault_code_id, cause_name, cause_description, priority_order)
                        VALUES (?, ?, ?, ?)
                    """, (fault_code_id, name, desc, i))

            if steps:
                for s in steps.split(";"):
                    parts = s.split("|")
                    if len(parts) < 3:
                        continue

                    order = int(parts[0])
                    step_title = parts[1].strip()
                    step_description = parts[2].strip()

                    cur.execute("""
                        INSERT INTO test_steps
                        (fault_code_id, step_order, step_title, step_description)
                        VALUES (?, ?, ?, ?)
                    """, (fault_code_id, order, step_title, step_description))

            added += 1

    conn.commit()
    conn.close()

    print(f"Import valmis ✅ Lisätty {added} uutta vikakoodia")


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS fault_codes (
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
    CREATE TABLE IF NOT EXISTS possible_causes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fault_code_id INTEGER NOT NULL,
        cause_name TEXT NOT NULL,
        cause_description TEXT,
        probability_score REAL DEFAULT 0,
        priority_order INTEGER DEFAULT 1,
        FOREIGN KEY (fault_code_id) REFERENCES fault_codes(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS symptom_matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fault_code_id INTEGER NOT NULL,
        keyword TEXT NOT NULL,
        note TEXT,
        weight REAL DEFAULT 1.0,
        FOREIGN KEY (fault_code_id) REFERENCES fault_codes(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS test_steps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fault_code_id INTEGER NOT NULL,
        step_order INTEGER NOT NULL,
        step_title TEXT NOT NULL,
        step_description TEXT,
        required_tools TEXT,
        FOREIGN KEY (fault_code_id) REFERENCES fault_codes(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS vehicle_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fault_code_id INTEGER NOT NULL,
        make TEXT,
        model TEXT,
        engine TEXT,
        year_from INTEGER,
        year_to INTEGER,
        rule_note TEXT,
        extra_probability_boost REAL DEFAULT 0,
        FOREIGN KEY (fault_code_id) REFERENCES fault_codes(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        is_admin INTEGER DEFAULT 0,
        account_type TEXT DEFAULT 'basic',
        subscription_status TEXT DEFAULT 'inactive',
        subscription_started_at DATETIME,
        subscription_expires_at DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS saved_diagnoses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        code TEXT NOT NULL,
        make TEXT NOT NULL,
        model TEXT NOT NULL,
        engine TEXT,
        symptoms TEXT,
        initial_image_path TEXT,
        resolution_image_path TEXT,
        requires_resolution_image INTEGER DEFAULT 0,
        result_json TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS solution_feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        diagnosis_id INTEGER,
        fault_code TEXT NOT NULL,
        title TEXT,
        description TEXT,
        vehicle TEXT,
        helpful INTEGER NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (diagnosis_id) REFERENCES saved_diagnoses(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS suggested_fault_code_updates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        diagnosis_id INTEGER,
        fault_code_id INTEGER NOT NULL,
        suggestion_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        source_summary TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        admin_note TEXT,
        reviewed_by_user_id INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        reviewed_at DATETIME,
        FOREIGN KEY (diagnosis_id) REFERENCES saved_diagnoses(id),
        FOREIGN KEY (fault_code_id) REFERENCES fault_codes(id),
        FOREIGN KEY (reviewed_by_user_id) REFERENCES users(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS password_reset_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        token TEXT NOT NULL UNIQUE,
        expires_at DATETIME NOT NULL,
        used_at DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS one_time_purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        product_type TEXT NOT NULL,
        product_key TEXT NOT NULL,
        payment_status TEXT NOT NULL DEFAULT 'pending',
        purchased_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        expires_at DATETIME,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS accounting_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        customer_name TEXT,
        company_name TEXT,
        vat_number TEXT,
        email TEXT,
        product_type TEXT,
        product_name TEXT,
        quantity INTEGER DEFAULT 1,
        unit_price REAL DEFAULT 0,
        total_ex_vat REAL DEFAULT 0,
        vat_rate REAL DEFAULT 0,
        total_vat REAL DEFAULT 0,
        total_price REAL DEFAULT 0,
        currency TEXT DEFAULT 'EUR',
        payment_status TEXT DEFAULT 'paid',
        payment_method TEXT,
        reference_number TEXT,
        note TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS repair_guide_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        make TEXT NOT NULL,
        vehicle_input TEXT NOT NULL,
        input_type TEXT,
        vin_prefix TEXT,
        part_name TEXT NOT NULL,
        note TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        completed_at DATETIME,
        guide_id INTEGER,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS repair_guides (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        make TEXT NOT NULL,
        part_name TEXT NOT NULL,
        vin_prefix TEXT,
        title TEXT,
        steps TEXT NOT NULL,
        tools TEXT,
        notes TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    try:
        cur.execute("ALTER TABLE users ADD COLUMN last_active_at DATETIME")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE users ADD COLUMN is_online INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE users ADD COLUMN full_name TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE users ADD COLUMN phone TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE users ADD COLUMN address_line1 TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE users ADD COLUMN postal_code TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE users ADD COLUMN city TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE users ADD COLUMN country TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE users ADD COLUMN customer_type TEXT DEFAULT 'private'")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE users ADD COLUMN company_name TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE users ADD COLUMN vat_number TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE fault_codes ADD COLUMN make TEXT DEFAULT 'Yleinen'")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE fault_codes ADD COLUMN problem_symptoms TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE fault_codes ADD COLUMN mil_status TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE fault_codes ADD COLUMN fail_safe_function TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE fault_codes ADD COLUMN priority TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE fault_codes ADD COLUMN sae_code TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE saved_diagnoses ADD COLUMN resolved INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE saved_diagnoses ADD COLUMN final_cause TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE saved_diagnoses ADD COLUMN final_fix TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE saved_diagnoses ADD COLUMN feedback_notes TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE saved_diagnoses ADD COLUMN closed_at DATETIME")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE saved_diagnoses ADD COLUMN initial_image_path TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE saved_diagnoses ADD COLUMN resolution_image_path TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE saved_diagnoses ADD COLUMN requires_resolution_image INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("""
        DELETE FROM solution_feedback
        WHERE id IN (
            SELECT sf.id
            FROM solution_feedback sf
            JOIN (
                SELECT user_id, diagnosis_id, MAX(id) AS keep_id
                FROM solution_feedback
                WHERE user_id IS NOT NULL
                  AND diagnosis_id IS NOT NULL
                GROUP BY user_id, diagnosis_id
                HAVING COUNT(*) > 1
            ) dup
              ON sf.user_id = dup.user_id
             AND sf.diagnosis_id = dup.diagnosis_id
            WHERE sf.id != dup.keep_id
        )
        """)
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_fault_codes_code_make
        ON fault_codes (
            upper(trim(code)),
            lower(trim(coalesce(make, 'Yleinen')))
        )
        """)
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_solution_feedback_user_ticket
        ON solution_feedback(user_id, diagnosis_id)
        WHERE user_id IS NOT NULL AND diagnosis_id IS NOT NULL
        """)
    except sqlite3.OperationalError:
        pass
        
    seed_data()
    
    conn.commit()
    conn.close()
