"""
Database management module for Bedrock Agent Action Group backend.
Supports SQLite (compatible with AWS Lambda /tmp directory and local execution).
"""

import os
import sqlite3
import tempfile
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

# Cross-platform temp path: /tmp in AWS Lambda, %TEMP% on Windows
DB_PATH = os.path.join(tempfile.gettempdir(), "retail_store.db")


def get_db_connection() -> sqlite3.Connection:
    """Creates a connection with dict-like row access."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database() -> None:
    """Initializes tables and seeds mock data if not already present."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            product_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL,
            stock INTEGER NOT NULL,
            description TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL,
            customer_name TEXT NOT NULL,
            product_id TEXT NOT NULL,
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            total_amount REAL NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            delivery_date TEXT
        )
    """)

    # Seed products if empty
    cursor.execute("SELECT COUNT(*) FROM products")
    if cursor.fetchone()[0] == 0:
        sample_products = [
            ("PROD-001", "Titan Wireless Headphones", "Electronics", 149.99, 45, "Active noise cancelling over-ear Bluetooth headphones with 30h battery."),
            ("PROD-002", "Smart Fitness Watch V2", "Wearables", 199.99, 12, "Heart rate, SpO2, GPS, sleep tracking, waterproof 50m."),
            ("PROD-003", "Ergonomic Mechanical Keyboard", "Accessories", 89.99, 0, "RGB mechanical keyboard with hot-swappable switches (Currently Out of Stock)."),
            ("PROD-004", "Ultra HD 4K Webcam", "Electronics", 79.99, 28, "1080p60/4k30 autofocus webcam with stereo dual-array microphone."),
            ("PROD-005", "USB-C Multi-Port Hub (8-in-1)", "Accessories", 49.99, 85, "HDMI 4K, 100W PD charging, 3x USB 3.0, SD/TF card reader.")
        ]
        cursor.executemany(
            "INSERT INTO products (product_id, name, category, price, stock, description) VALUES (?, ?, ?, ?, ?, ?)",
            sample_products
        )

    # Seed orders if empty
    cursor.execute("SELECT COUNT(*) FROM orders")
    if cursor.fetchone()[0] == 0:
        now = datetime.utcnow()
        sample_orders = [
            ("ORD-1001", "CUST-101", "Alice Johnson", "PROD-001", "Titan Wireless Headphones", 1, 149.99, "In Transit", 
             (now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S"), (now + timedelta(days=1)).strftime("%Y-%m-%d")),
            ("ORD-1002", "CUST-102", "Bob Smith", "PROD-002", "Smart Fitness Watch V2", 1, 199.99, "Delivered", 
             (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S"), (now - timedelta(days=4)).strftime("%Y-%m-%d")),
            ("ORD-1003", "CUST-101", "Alice Johnson", "PROD-005", "USB-C Multi-Port Hub (8-in-1)", 2, 99.98, "Processing", 
             (now - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S"), (now + timedelta(days=3)).strftime("%Y-%m-%d")),
            ("ORD-1004", "CUST-103", "Charlie Davis", "PROD-004", "Ultra HD 4K Webcam", 1, 79.99, "Cancelled", 
             (now - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S"), None)
        ]
        cursor.executemany(
            "INSERT INTO orders (order_id, customer_id, customer_name, product_id, product_name, quantity, total_amount, status, created_at, delivery_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            sample_orders
        )

    conn.commit()
    conn.close()


def get_order_by_id(order_id: str) -> Optional[Dict[str, Any]]:
    """Fetch order details by order_id."""
    init_database()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE order_id = ? COLLATE NOCASE", (order_id.strip(),))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def list_orders_by_customer(customer_identifier: str) -> List[Dict[str, Any]]:
    """Search orders by customer ID or customer name."""
    init_database()
    conn = get_db_connection()
    cursor = conn.cursor()
    query = "%" + customer_identifier.strip() + "%"
    cursor.execute(
        "SELECT * FROM orders WHERE customer_id LIKE ? OR customer_name LIKE ? COLLATE NOCASE ORDER BY created_at DESC", 
        (query, query)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_product_by_id_or_name(search_term: str) -> Optional[Dict[str, Any]]:
    """Look up product by exact ID or partial name."""
    init_database()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE product_id = ? COLLATE NOCASE", (search_term.strip(),))
    row = cursor.fetchone()
    if not row:
        query = "%" + search_term.strip() + "%"
        cursor.execute("SELECT * FROM products WHERE name LIKE ? COLLATE NOCASE LIMIT 1", (query,))
        row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def list_products(category: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all products or filter by category."""
    init_database()
    conn = get_db_connection()
    cursor = conn.cursor()
    if category and category.strip():
        cursor.execute("SELECT * FROM products WHERE category LIKE ? COLLATE NOCASE", (f"%{category.strip()}%",))
    else:
        cursor.execute("SELECT * FROM products")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def cancel_order(order_id: str, reason: str = "Customer requested cancellation") -> Dict[str, Any]:
    """Cancels an order if eligible (only if Processing or In Transit)."""
    init_database()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE order_id = ? COLLATE NOCASE", (order_id.strip(),))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return {"success": False, "error": f"Order {order_id} not found."}

    current_status = row["status"]
    if current_status in ["Delivered", "Cancelled"]:
        conn.close()
        return {
            "success": False, 
            "error": f"Order {order_id} cannot be cancelled because its current status is '{current_status}'."
        }

    cursor.execute("UPDATE orders SET status = 'Cancelled' WHERE order_id = ?", (row["order_id"],))
    conn.commit()
    conn.close()

    return {
        "success": True,
        "order_id": row["order_id"],
        "previous_status": current_status,
        "new_status": "Cancelled",
        "reason": reason,
        "refund_initiated": True,
        "refund_amount": row["total_amount"]
    }


def create_order(customer_name: str, product_id_or_name: str, quantity: int = 1) -> Dict[str, Any]:
    """Creates a new order and decrements inventory."""
    init_database()
    product = get_product_by_id_or_name(product_id_or_name)
    if not product:
        return {"success": False, "error": f"Product '{product_id_or_name}' not found."}

    if product["stock"] < quantity:
        return {
            "success": False, 
            "error": f"Insufficient stock for '{product['name']}'. Requested: {quantity}, Available: {product['stock']}."
        }

    conn = get_db_connection()
    cursor = conn.cursor()

    # Decrement stock
    new_stock = product["stock"] - quantity
    cursor.execute("UPDATE products SET stock = ? WHERE product_id = ?", (new_stock, product["product_id"]))

    # Generate new order ID
    cursor.execute("SELECT COUNT(*) FROM orders")
    count = cursor.fetchone()[0]
    new_order_id = f"ORD-{1005 + count}"
    customer_id = f"CUST-{hash(customer_name) % 900 + 100}"
    total_amount = round(product["price"] * quantity, 2)
    created_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    delivery_date = (datetime.utcnow() + timedelta(days=3)).strftime("%Y-%m-%d")

    cursor.execute("""
        INSERT INTO orders (order_id, customer_id, customer_name, product_id, product_name, quantity, total_amount, status, created_at, delivery_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (new_order_id, customer_id, customer_name, product["product_id"], product["name"], quantity, total_amount, "Processing", created_at, delivery_date))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "order_id": new_order_id,
        "customer_name": customer_name,
        "product_name": product["name"],
        "quantity": quantity,
        "total_amount": total_amount,
        "status": "Processing",
        "estimated_delivery": delivery_date
    }
