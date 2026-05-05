import os
import re
import sys
import shutil
import sqlite3
from services.suggestion_service import create_ai_enrichment_suggestions
from datetime import datetime

import fitz  # pip install pymupdf

from db_init import get_connection


DEFAULT_MAKE = "Yleinen"
DEFAULT_SYSTEM = "engine"


def clean(value):
    return re.sub(r"\s+", " ", (value or "").strip())


def backup_db():
    db_path = "korjaamo_kaveri.db"
    if os.path.exists(db_path):
        backup_path = f"korjaamo_kaveri_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2(db_path, backup_path)
        print(f"Varmuuskopio tehty: {backup_path}")


def read_pdf_text(pdf_path):
    doc = fitz.open(pdf_path)
    return "\n".join(page.get_text() for page in doc)


def severity_from_priority(priority):
    if priority == "A":
        return "high"
    if priority == "B":
        return "medium"
    return "medium"


def extract_techdoc_rows(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    rows = []
    current = []
    code_re = re.compile(r"^[PCUB][0-9A-Z]{5,7}$")

    for line in lines:
        if code_re.match(line):
            if current:
                rows.append(current)
            current = [line]
        elif current:
            current.append(line)

    if current:
        rows.append(current)

    parsed = []
    for lines in rows:
        row = parse_techdoc_row(lines)
        if row:
            parsed.append(row)

    return parsed


def parse_techdoc_row(lines):
    full_code = lines[0]
    mil_index = None

    for i, line in enumerate(lines):
        if line in {"Syttyy", "Ei syty"} or line.startswith("Syttyy /"):
            mil_index = i
            break

    if mil_index is None:
        return None

    description = clean(" ".join(lines[1:mil_index]))
    if not description:
        return None

    priority = ""
    source_index = None

    for i in range(mil_index + 1, len(lines)):
        match = re.match(r"^(Moottori)\s+([AB])$", lines[i])
        if match:
            priority = match.group(2)
            source_index = i
            break

    mil_lines = []
    for line in lines[mil_index:source_index or len(lines)]:
        if not line.startswith("SAE") and line not in {"Napsauta", "tätä"}:
            mil_lines.append(line)

    sae_code = ""
    for i, line in enumerate(lines):
        if "koodi:" in line and i + 1 < len(lines):
            sae_code = clean(lines[i + 1])
            break

    if sae_code == "-":
        sae_code = ""

    return {
        "code": sae_code or full_code,
        "full_code": full_code,
        "sae_code": sae_code,
        "title": description,
        "description": description,
        "mil_status": clean(" ".join(mil_lines)),
        "priority": priority,
        "severity": severity_from_priority(priority),
        "system": DEFAULT_SYSTEM,
        "make": "Toyota",
    }


def extract_generic_rows(text, make=DEFAULT_MAKE):
    rows = []
    seen = set()

    text = text.replace("\r", "\n")
    lines = [clean(line) for line in text.splitlines() if clean(line)]

    code_re = re.compile(r"\b([PCUB][0-9A-Z]{4,7})\b")

    for i, line in enumerate(lines):
        match = code_re.search(line)
        if not match:
            continue

        code = match.group(1).upper()

        description = line.replace(code, "").strip(" -–:|")
        if len(description) < 5 and i + 1 < len(lines):
            description = lines[i + 1]

        description = clean(description)

        if description.lower() in {
            "click", "napsauta", "tätä", "napsauta tätä"}:
            continue

        if not description or description.lower() in {
            "vikakoodi", "dtc", "description", "kuvaus", "vikatyyppi"
        }:
            continue

        key = (code, description.lower())
        if key in seen:
            continue

        seen.add(key)

        rows.append({
            "code": code,
            "full_code": code,
            "sae_code": code if re.match(r"^[PCUB][0-9A-Z]{4}$", code) else "",
            "title": description,
            "description": description,
            "mil_status": "",
            "priority": "",
            "severity": "medium",
            "system": DEFAULT_SYSTEM,
            "make": make,
        })

    return rows


def default_causes(description):
    d = description.lower()

    if "sytytyskatkos" in d or "misfire" in d:
        return [
            ("Sytytystulppa", "Kulunut tai viallinen sytytystulppa voi aiheuttaa sytytyskatkoksen."),
            ("Sytytyspuola", "Viallinen puola voi aiheuttaa katkoksia."),
            ("Polttoainesuutin", "Suutinvika voi aiheuttaa palamishäiriön."),
            ("Imuvuoto", "Imuvuoto voi sekoittaa seossuhdetta."),
        ]

    if "laiha" in d or "lean" in d:
        return [
            ("Imuvuoto", "Ylimääräinen ilma voi aiheuttaa laihan seoksen."),
            ("Ilmamassamittari", "Virheellinen ilmamäärätieto voi vääristää seosta."),
            ("Polttoainepaine", "Liian matala paine voi aiheuttaa laihan seoksen."),
            ("Happitunnistin", "Virheellinen lambdasignaali voi johtaa väärään säätöön."),
        ]

    if "rikas" in d or "rich" in d:
        return [
            ("Vuotava suutin", "Liiallinen polttoaine voi rikastaa seosta."),
            ("Ilmamassamittari", "Virheellinen mittaus voi aiheuttaa väärän seoksen."),
            ("Polttoainepaine", "Liian korkea paine voi rikastaa seosta."),
            ("Happitunnistin", "Väärä signaali voi ohjata seosta virheellisesti."),
        ]

    if "paine" in d or "pressure" in d:
        return [
            ("Paineanturi", "Anturi voi antaa virheellistä painetietoa."),
            ("Johtosarja tai liitin", "Oikosulku, avoin piiri tai huono kontakti on mahdollinen."),
            ("Pumppu", "Pumppu voi tuottaa liian vähän tai liikaa painetta."),
            ("Suodatin tai tukos", "Virtaus voi olla rajoittunut."),
        ]

    if "o2" in d or "happi" in d or "lambda" in d or "a/f" in d:
        return [
            ("Happitunnistin / A/F-anturi", "Anturi voi olla viallinen."),
            ("Lämmityspiiri", "Anturin lämmitinpiirissä voi olla vika."),
            ("Johtosarja tai liitin", "Tarkista avoin piiri ja oikosulut."),
            ("Pakovuoto", "Vuoto voi vääristää mittausta."),
        ]

    return [
        ("Johtosarja tai liitin", "Tarkista avoin piiri, oikosulku ja liittimien kunto."),
        ("Anturi tai toimilaite", "Viallinen komponentti voi aiheuttaa vikakoodin."),
        ("Virransyöttö tai maadoitus", "Tarkista jännite, sulakkeet ja maadoitukset."),
        ("Ohjainlaite", "Jos muut tarkistukset ovat kunnossa, ohjainlaitteen vika on mahdollinen."),
    ]


def default_steps():
    return [
        ("Lue vikakoodit ja freeze frame -tiedot", "Tallenna olosuhteet ja muut vikakoodit.", "vikakoodinlukija"),
        ("Tarkista näkyvät viat", "Tarkista liittimet, johdot, vuodot ja mekaaniset vauriot.", "silmämääräinen tarkistus"),
        ("Tarkista virransyöttö ja maadoitus", "Mittaa jännite, maa ja mahdolliset oikosulut.", "yleismittari"),
        ("Testaa epäilty komponentti", "Vertaa mittausarvoja valmistajan ohjearvoihin.", "vikakoodinlukija / yleismittari"),
        ("Korjaa vika ja koeaja", "Poista vikakoodi ja varmista ettei se palaa.", "vikakoodinlukija"),
    ]


def is_bad_title(text):
    if not text:
        return True

    text = text.strip()

    if re.match(r"^[PCUB][0-9A-Z]{4,7}$", text):
        return True

    if text.lower() in {"click", "napsauta", "tätä", "napsauta tätä"}:
        return True

    if len(text) < 5:
        return True

    return False

def insert_or_update_fault_code(cur, row):
    code = row["code"]
    make = row["make"]

    description = (
        f"{row['description']}\n\n"
        f"Lähdekoodi: {row['full_code']}\n"
        f"SAE-koodi: {row['sae_code'] or '-'}\n"
        f"MIL: {row['mil_status'] or '-'}\n"
        f"Prioriteetti: {row['priority'] or '-'}"
    )

    cur.execute("""
        SELECT id, title, description
        FROM fault_codes
        WHERE upper(trim(code)) = upper(trim(?))
          AND lower(trim(coalesce(make, 'Yleinen'))) = lower(trim(?))
        LIMIT 1
    """, (code, make))

    existing = cur.fetchone()

    # 🔥 UPDATE
    if existing:
        fault_code_id = existing["id"]
        old_title = existing["title"] or ""
        old_description = existing["description"] or ""

        new_title = row["title"]

        # 🔥 estä otsikon rikkoutuminen
        if is_bad_title(new_title):
            new_title = old_title

        # 🔥 estä kuvauksen rikkoutuminen
        if len(row["description"]) < 10:
            new_description = old_description
        else:
            new_description = description

        cur.execute("""
            UPDATE fault_codes
            SET title = ?,
                description = ?,
                severity = ?,
                system = ?,
                mil_status = ?,
                priority = ?,
                sae_code = ?
            WHERE id = ?
        """, (
            new_title,
            new_description,
            row["severity"],
            row["system"],
            row["mil_status"],
            row["priority"],
            row["sae_code"],
            fault_code_id,
        ))

        return fault_code_id, False

    # 🔥 INSERT
    cur.execute("""
        INSERT INTO fault_codes (
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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        code,
        make,
        row["title"],
        description,
        row["severity"],
        row["system"],
        "",
        row["mil_status"],
        "",
        row["priority"],
        row["sae_code"],
    ))

    return cur.lastrowid, True

    cur.execute("""
        SELECT id
        FROM fault_codes
        WHERE upper(trim(code)) = upper(trim(?))
          AND lower(trim(coalesce(make, 'Yleinen'))) = lower(trim(?))
        LIMIT 1
    """, (code, make))

    existing = cur.fetchone()

    if existing:
        fault_code_id = existing["id"]
        cur.execute("""
            UPDATE fault_codes
            SET title = ?,
                description = ?,
                severity = ?,
                system = ?,
                mil_status = ?,
                priority = ?,
                sae_code = ?
            WHERE id = ?
        """, (
            row["title"],
            description,
            row["severity"],
            row["system"],
            row["mil_status"],
            row["priority"],
            row["sae_code"],
            fault_code_id,
        ))
        return fault_code_id, False

    cur.execute("""
        INSERT INTO fault_codes (
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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        code,
        make,
        row["title"],
        description,
        row["severity"],
        row["system"],
        "",
        row["mil_status"],
        "",
        row["priority"],
        row["sae_code"],
    ))

    return cur.lastrowid, True


def ensure_details(cur, fault_code_id, description):
    cur.execute("SELECT COUNT(*) AS count FROM possible_causes WHERE fault_code_id = ?", (fault_code_id,))
    if cur.fetchone()["count"] == 0:
        for index, (name, desc) in enumerate(default_causes(description), start=1):
            cur.execute("""
                INSERT INTO possible_causes (
                    fault_code_id,
                    cause_name,
                    cause_description,
                    probability_score,
                    priority_order
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                fault_code_id,
                name,
                desc,
                round(max(0.10, 0.45 - (index - 1) * 0.08), 2),
                index,
            ))

    cur.execute("SELECT COUNT(*) AS count FROM test_steps WHERE fault_code_id = ?", (fault_code_id,))
    if cur.fetchone()["count"] == 0:
        for index, (title, desc, tools) in enumerate(default_steps(), start=1):
            cur.execute("""
                INSERT INTO test_steps (
                    fault_code_id,
                    step_order,
                    step_title,
                    step_description,
                    required_tools
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                fault_code_id,
                index,
                title,
                desc,
                tools,
            ))


def import_pdf(pdf_path, make=DEFAULT_MAKE):
    if not os.path.exists(pdf_path):
        print(f"PDF-tiedostoa ei löydy: {pdf_path}")
        return

    backup_db()

    text = read_pdf_text(pdf_path)

    techdoc_rows = extract_techdoc_rows(text)
    generic_rows = extract_generic_rows(text, make=make)

    if len(techdoc_rows) >= 10:
        rows = techdoc_rows
        mode = "TechDoc"
    else:
        rows = generic_rows
        mode = "Generic"

    conn = get_connection()
    cur = conn.cursor()

    added = 0
    updated = 0
    skipped = 0

    for row in rows:
        try:
            fault_code_id, was_added = insert_or_update_fault_code(cur, row)
            ensure_details(cur, fault_code_id, row["description"])
            if was_added:
                create_ai_enrichment_suggestions(fault_code_id)
            if was_added:
                added += 1
            else:
                updated += 1

        except sqlite3.Error as e:
            skipped += 1
            print(f"Ohitettiin {row.get('code')}: {e}")

    conn.commit()
    conn.close()

    print(f"Import valmis ({mode}).")
    print(f"Lisätty: {added}")
    print(f"Päivitetty: {updated}")
    print(f"Ohitettu: {skipped}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Käyttö: python utils/import_pdf_dtc.py "tiedosto.pdf" [merkki]')
        sys.exit(1)

    pdf_path = sys.argv[1]
    make = sys.argv[2] if len(sys.argv) >= 3 else DEFAULT_MAKE

    import_pdf(pdf_path, make)