"""
Local test harness for Lambda Handler.
Simulates AWS Bedrock Agent Action Group invocations offline.
"""

import json
from lambda_function import lambda_handler


def test_get_order():
    event = {
        "messageVersion": "1.0",
        "actionGroup": "OrderActionGroup",
        "apiPath": "/orders/{orderId}",
        "httpMethod": "GET",
        "parameters": [
            {"name": "orderId", "type": "string", "value": "ORD-1001"}
        ]
    }
    response = lambda_handler(event)
    assert response["response"]["httpStatusCode"] == 200
    body = json.loads(response["response"]["responseBody"]["application/json"]["body"])
    print("[PASS] test_get_order: Order ID:", body["order_id"], "| Status:", body["status"])


def test_list_customer_orders():
    event = {
        "messageVersion": "1.0",
        "actionGroup": "OrderActionGroup",
        "apiPath": "/orders",
        "httpMethod": "GET",
        "parameters": [
            {"name": "customer", "type": "string", "value": "Alice"}
        ]
    }
    response = lambda_handler(event)
    assert response["response"]["httpStatusCode"] == 200
    body = json.loads(response["response"]["responseBody"]["application/json"]["body"])
    print(f"[PASS] test_list_customer_orders: Found {body['count']} orders for Alice")


def test_get_product():
    event = {
        "messageVersion": "1.0",
        "actionGroup": "OrderActionGroup",
        "apiPath": "/products/{productId}",
        "httpMethod": "GET",
        "parameters": [
            {"name": "productId", "type": "string", "value": "PROD-001"}
        ]
    }
    response = lambda_handler(event)
    assert response["response"]["httpStatusCode"] == 200
    body = json.loads(response["response"]["responseBody"]["application/json"]["body"])
    print(f"[PASS] test_get_product: {body['name']} | Price: ${body['price']} | Stock: {body['stock']}")


def test_create_and_cancel_order():
    # 1. Create order
    create_event = {
        "messageVersion": "1.0",
        "actionGroup": "OrderActionGroup",
        "apiPath": "/orders",
        "httpMethod": "POST",
        "requestBody": {
            "content": {
                "application/json": {
                    "properties": [
                        {"name": "customer_name", "type": "string", "value": "Test User"},
                        {"name": "product", "type": "string", "value": "PROD-002"},
                        {"name": "quantity", "type": "integer", "value": 1}
                    ]
                }
            }
        }
    }
    res_create = lambda_handler(create_event)
    assert res_create["response"]["httpStatusCode"] == 201
    body_create = json.loads(res_create["response"]["responseBody"]["application/json"]["body"])
    new_order_id = body_create["order_id"]
    print(f"[PASS] test_create_order: Created {new_order_id} for {body_create['customer_name']}")

    # 2. Cancel order
    cancel_event = {
        "messageVersion": "1.0",
        "actionGroup": "OrderActionGroup",
        "apiPath": "/orders/{orderId}/cancel",
        "httpMethod": "POST",
        "parameters": [
            {"name": "orderId", "type": "string", "value": new_order_id}
        ],
        "requestBody": {
            "content": {
                "application/json": {
                    "properties": [
                        {"name": "reason", "type": "string", "value": "Customer changed mind"}
                    ]
                }
            }
        }
    }
    res_cancel = lambda_handler(cancel_event)
    assert res_cancel["response"]["httpStatusCode"] == 200
    body_cancel = json.loads(res_cancel["response"]["responseBody"]["application/json"]["body"])
    print(f"[PASS] test_cancel_order: Cancelled {body_cancel['order_id']} | Refund: ${body_cancel['refund_amount']}")


if __name__ == "__main__":
    print("--- Running Local Bedrock Agent Lambda Handler Tests ---")
    test_get_order()
    test_list_customer_orders()
    test_get_product()
    test_create_and_cancel_order()
    print("--- All Lambda Tests Passed Successfully! ---")
