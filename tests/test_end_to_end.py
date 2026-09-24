"""
End-to-End verification test.
Validates:
1. OpenAPI schema syntax and required fields
2. Bedrock prompt instructions readability
3. Offline Bedrock mock simulator generation
4. Local SQLite database queries and state updates
"""

import os
import sys
import json

# Add parent directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend_lambda.database import init_database, get_order_by_id, list_products
from ui.bedrock_service import mock_agent_stream


def test_openapi_schema_validity():
    schema_path = os.path.join(os.path.dirname(__file__), "..", "schemas", "openapi_schema.json")
    assert os.path.exists(schema_path), "OpenAPI schema file does not exist"
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)
    assert schema["openapi"] == "3.0.0"
    assert "/orders/{orderId}" in schema["paths"]
    assert "/products" in schema["paths"]
    assert "/orders/{orderId}/cancel" in schema["paths"]
    print("\n[OK] OpenAPI schema structure verified.")


def test_agent_instructions_file():
    instructions_path = os.path.join(os.path.dirname(__file__), "..", "bedrock_agent", "agent_instructions.txt")
    assert os.path.exists(instructions_path)
    with open(instructions_path, "r", encoding="utf-8") as f:
        text = f.read()
    assert len(text) > 100
    assert "Claude" in text or "Assistant" in text or "Order" in text
    print("[OK] Bedrock Agent Instructions verified.")


def test_database_initialization():
    init_database()
    order = get_order_by_id("ORD-1001")
    assert order is not None
    assert order["status"] == "In Transit"

    products = list_products()
    assert len(products) >= 5
    print("[OK] Database initialization and seed records verified.")


def test_mock_agent_stream_execution():
    generator = mock_agent_stream("Where is order ORD-1001?", "test-session-123")
    events = list(generator)
    assert len(events) > 0
    
    traces = [e for e in events if e.get("type") == "trace"]
    chunks = [e for e in events if e.get("type") == "chunk"]
    
    assert len(traces) >= 2, "Expected at least 2 trace steps (Action Group invoke & result)"
    full_text = "".join(c.get("text", "") for c in chunks)
    assert "ORD-1001" in full_text
    assert "In Transit" in full_text
    print(f"[OK] Mock Agent Stream generated {len(chunks)} chunks, response length {len(full_text)} chars.")


if __name__ == "__main__":
    test_openapi_schema_validity()
    test_agent_instructions_file()
    test_database_initialization()
    test_mock_agent_stream_execution()
    print("\n All End-to-End local verification tests passed successfully!")
