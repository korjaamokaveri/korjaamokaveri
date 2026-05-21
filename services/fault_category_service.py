from db_init import get_connection


CATEGORY_RULES = [
    {
        "keywords": ["dpf", "particulate filter"],
        "category": "DPF System",
    },
    {
        "keywords": ["egr"],
        "category": "EGR System",
    },
    {
        "keywords": ["turbo", "boost"],
        "category": "Turbo System",
    },
    {
        "keywords": ["hybrid", "hv battery"],
        "category": "Hybrid System",
    },
    {
        "keywords": ["ev", "electric vehicle", "battery pack"],
        "category": "Electric Vehicle System",
    },
    {
        "keywords": ["abs", "brake pressure"],
        "category": "ABS System",
    },
    {
        "keywords": ["can", "communication bus", "u0"],
        "category": "CAN Bus",
    },
]


def slugify_category(name: str) -> str:
    return (
        (name or "")
        .strip()
        .lower()
        .replace(" ", "-")
    )


def find_category_by_name(name: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM fault_categories
        WHERE lower(name) = ?
    """, ((name or "").lower().strip(),))

    row = cur.fetchone()

    conn.close()
    return row


def create_category(name: str, description: str = ""):
    existing = find_category_by_name(name)

    if existing:
        return existing["id"]

    conn = get_connection()
    cur = conn.cursor()

    slug = slugify_category(name)

    cur.execute("""
        INSERT INTO fault_categories (
            name,
            slug,
            description
        )
        VALUES (?, ?, ?)
    """, (
        name.strip(),
        slug,
        description.strip(),
    ))

    category_id = cur.lastrowid

    conn.commit()
    conn.close()

    return category_id


def create_category_suggestion(
    fault_code_id: int,
    suggested_category_name: str,
    reason: str = "",
):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO fault_category_suggestions (
            fault_code_id,
            suggested_category_name,
            suggested_slug,
            reason,
            status
        )
        VALUES (?, ?, ?, ?, 'pending')
    """, (
        fault_code_id,
        suggested_category_name,
        slugify_category(suggested_category_name),
        reason,
    ))

    conn.commit()
    conn.close()


def suggest_category_for_fault(
    fault_code_id: int,
    code: str,
    title: str,
    description: str,
):
    text = f"{code} {title} {description}".lower()

    for rule in CATEGORY_RULES:

        for keyword in rule["keywords"]:

            if keyword.lower() in text:

                create_category_suggestion(
                    fault_code_id=fault_code_id,
                    suggested_category_name=rule["category"],
                    reason=f"Matched keyword: {keyword}",
                )

                return rule["category"]

    return None
