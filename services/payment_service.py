from db_init import get_connection
from services.accounting_service import create_accounting_entry


PRODUCT_CATALOG = {
    "basic_subscription": {
        "product_name": "Basic-tilaus",
        "unit_price": 19.90,
        "vat_rate": 25.5,
    },
    "component_guide": {
        "product_name": "Komponenttikohtainen ohje",
        "unit_price": 14.90,
        "vat_rate": 25.5,
    },
    "wiring_diagram": {
        "product_name": "Kytkentäkaavio",
        "unit_price": 9.90,
        "vat_rate": 25.5,
    },
}


def get_product_pricing(product_type: str):
    key = (product_type or "").strip().lower()
    return PRODUCT_CATALOG.get(
        key,
        {
            "product_name": key or "Tuote",
            "unit_price": 0.00,
            "vat_rate": 25.5,
        },
    )


def ensure_one_time_purchase(user_id: int, product_type: str, product_key: str = ""):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT id FROM one_time_purchases
        WHERE user_id = ?
          AND lower(product_type) = lower(?)
          AND coalesce(product_key, '') = ?
        ORDER BY id DESC
        LIMIT 1
    """, (user_id, product_type, product_key))

    row = cur.fetchone()

    if row:
        conn.close()
        return row["id"]

    cur.execute("""
        INSERT INTO one_time_purchases (user_id, product_type, product_key, payment_status)
        VALUES (?, ?, ?, 'pending')
    """, (user_id, product_type, product_key))

    purchase_id = cur.lastrowid
    conn.commit()
    conn.close()
    return purchase_id


def mark_one_time_purchase_paid(
    user_id: int,
    product_type: str,
    product_key: str = "",
    payment_method: str = "manual",
):
    pricing = get_product_pricing(product_type)

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE one_time_purchases
        SET payment_status = 'paid'
        WHERE user_id = ?
          AND lower(product_type) = lower(?)
          AND coalesce(product_key, '') = ?
    """, (user_id, product_type, product_key))

    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cur.fetchone()

    conn.commit()
    conn.close()

    return create_accounting_entry(
        user_id=user_id,
        customer_name=(user["full_name"] if user else "") or (user["email"] if user else ""),
        company_name=(user["company_name"] if user else "") or "",
        vat_number=(user["vat_number"] if user else "") or "",
        email=(user["email"] if user else "") or "",
        product_type=product_type,
        product_name=pricing["product_name"],
        quantity=1,
        unit_price=pricing["unit_price"],
        vat_rate=pricing["vat_rate"],
        payment_status="paid",
        payment_method=payment_method,
        reference_number="manual",
        note=product_key,
        currency="EUR",
    )