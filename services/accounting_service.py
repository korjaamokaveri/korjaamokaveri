from db_init import get_connection


DEFAULT_PRICES = {
    "basic_subscription": {"name": "Basic-tilaus", "unit_price": 19.90, "vat_rate": 25.5},
    "component_guide": {"name": "Komponenttikohtainen ohje", "unit_price": 14.90, "vat_rate": 25.5},
    "wiring_diagram": {"name": "Kytkentäkaavio", "unit_price": 9.90, "vat_rate": 25.5},
}


def _price_info(product_type: str):
    key = (product_type or "").strip().lower()
    return DEFAULT_PRICES.get(
        key,
        {"name": key or "Tuntematon tuote", "unit_price": 0.0, "vat_rate": 25.5},
    )


def _build_customer_name(row):
    full_name = (row["full_name"] or "").strip() if "full_name" in row.keys() else ""
    if full_name:
        return full_name
    return (row["email"] or "").strip() if "email" in row.keys() else ""


def create_accounting_entry(
    user_id=None,
    customer_name: str = "",
    company_name: str = "",
    vat_number: str = "",
    email: str = "",
    product_type: str = "",
    product_name: str = "",
    quantity: int = 1,
    unit_price: float = 0.0,
    vat_rate: float = 25.5,
    payment_status: str = "paid",
    payment_method: str = "",
    reference_number: str = "",
    note: str = "",
    currency: str = "EUR",
):
    quantity = int(quantity or 1)
    if quantity < 1:
        quantity = 1

    unit_price = float(unit_price or 0)
    vat_rate = float(vat_rate or 0)

    total_price = round(quantity * unit_price, 2)
    total_ex_vat = round(total_price / (1 + vat_rate / 100), 2) if vat_rate >= 0 else total_price
    total_vat = round(total_price - total_ex_vat, 2)

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO accounting_entries (
            user_id,
            customer_name,
            company_name,
            vat_number,
            email,
            product_type,
            product_name,
            quantity,
            unit_price,
            total_ex_vat,
            vat_rate,
            total_vat,
            total_price,
            currency,
            payment_status,
            payment_method,
            reference_number,
            note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        (customer_name or "").strip(),
        (company_name or "").strip(),
        (vat_number or "").strip(),
        (email or "").strip().lower(),
        (product_type or "").strip(),
        (product_name or "").strip(),
        quantity,
        unit_price,
        total_ex_vat,
        vat_rate,
        total_vat,
        total_price,
        (currency or "EUR").strip().upper(),
        (payment_status or "paid").strip().lower(),
        (payment_method or "").strip(),
        (reference_number or "").strip(),
        (note or "").strip(),
    ))

    entry_id = cur.lastrowid
    conn.commit()
    conn.close()
    return entry_id


def get_all_accounting_entries():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            otp.id,
            otp.user_id,
            COALESCE(u.full_name, u.email, '') AS customer_name,
            COALESCE(u.company_name, '') AS company_name,
            COALESCE(u.vat_number, '') AS vat_number,
            COALESCE(u.email, '') AS email,
            otp.product_type,
            otp.product_key,
            otp.payment_status,
            otp.purchased_at,
            otp.expires_at,
            COALESCE(u.customer_type, 'private') AS customer_type,
            COALESCE(u.phone, '') AS phone,
            COALESCE(u.address_line1, '') AS address_line1,
            COALESCE(u.postal_code, '') AS postal_code,
            COALESCE(u.city, '') AS city,
            COALESCE(u.country, '') AS country
        FROM one_time_purchases otp
        LEFT JOIN users u ON u.id = otp.user_id
        ORDER BY otp.purchased_at DESC, otp.id DESC
    """)

    raw_rows = cur.fetchall()
    conn.close()

    items = []
    for row in raw_rows:
        info = _price_info(row["product_type"])
        quantity = 1
        unit_price = float(info["unit_price"])
        vat_rate = float(info["vat_rate"])
        total_price = round(quantity * unit_price, 2)
        total_ex_vat = round(total_price / (1 + vat_rate / 100), 2)
        total_vat = round(total_price - total_ex_vat, 2)

        items.append({
            "id": row["id"],
            "user_id": row["user_id"],
            "customer_name": _build_customer_name(row),
            "company_name": row["company_name"] or "",
            "vat_number": row["vat_number"] or "",
            "email": row["email"] or "",
            "product_type": row["product_type"] or "",
            "product_name": info["name"],
            "product_key": row["product_key"] or "",
            "quantity": quantity,
            "unit_price": unit_price,
            "total_ex_vat": total_ex_vat,
            "vat_rate": vat_rate,
            "total_vat": total_vat,
            "total_price": total_price,
            "currency": "EUR",
            "payment_status": row["payment_status"] or "pending",
            "payment_method": "",
            "reference_number": "",
            "note": row["product_key"] or "",
            "created_at": row["purchased_at"],
            "expires_at": row["expires_at"],
            "customer_type": row["customer_type"] or "private",
            "phone": row["phone"] or "",
            "address_line1": row["address_line1"] or "",
            "postal_code": row["postal_code"] or "",
            "city": row["city"] or "",
            "country": row["country"] or "",
        })

    return items


def get_accounting_summary():
    items = get_all_accounting_entries()

    paid_items = [item for item in items if (item["payment_status"] or "").strip().lower() == "paid"]

    summary = {
        "row_count": len(paid_items),
        "total_quantity": sum(item["quantity"] for item in paid_items),
        "total_ex_vat": round(sum(item["total_ex_vat"] for item in paid_items), 2),
        "total_vat": round(sum(item["total_vat"] for item in paid_items), 2),
        "total_price": round(sum(item["total_price"] for item in paid_items), 2),
    }

    grouped_map = {}
    for item in items:
        key = (item["product_type"] or "").strip() or "unknown"
        if key not in grouped_map:
            grouped_map[key] = {
                "product_type": key,
                "row_count": 0,
                "total_quantity": 0,
                "total_price": 0.0,
            }

        grouped_map[key]["row_count"] += 1
        grouped_map[key]["total_quantity"] += item["quantity"]
        grouped_map[key]["total_price"] = round(
            grouped_map[key]["total_price"] + item["total_price"], 2
        )

    grouped = [grouped_map[key] for key in sorted(grouped_map.keys())]
    return summary, grouped


def get_accounting_entries_by_status(payment_status: str):
    status = (payment_status or "").strip().lower()
    return [
        item for item in get_all_accounting_entries()
        if (item["payment_status"] or "").strip().lower() == status
    ]


def get_accounting_entries_for_user(user_id: int):
    return [
        item for item in get_all_accounting_entries()
        if item["user_id"] == user_id
    ]