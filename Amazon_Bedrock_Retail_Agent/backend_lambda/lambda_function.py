"""
AWS Lambda Handler for Amazon Bedrock Agent Action Group.
Handles incoming Bedrock agent requests, dispatches actions to database queries,
and formats responses according to the Bedrock Agent response specification.
"""

import json
import logging
from typing import Dict, Any, List

# Import our database logic
try:
    from database import (
        get_order_by_id,
        list_orders_by_customer,
        get_product_by_id_or_name,
        list_products,
        cancel_order,
        create_order,
        init_database
    )
except ImportError:
    from .database import (
        get_order_by_id,
        list_orders_by_customer,
        get_product_by_id_or_name,
        list_products,
        cancel_order,
        create_order,
        init_database
    )

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def extract_parameters(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extracts query and path parameters from Bedrock Agent event.
    Parameters format: [{'name': 'paramName', 'type': 'string', 'value': 'val'}, ...]
    """
    params = {}
    for param in event.get("parameters", []):
        params[param["name"]] = param["value"]

    # Also check requestBody if present
    request_body = event.get("requestBody", {})
    content = request_body.get("content", {})
    app_json = content.get("application/json", {})

    # OpenAPI schema style: list of properties
    properties = app_json.get("properties", [])
    if isinstance(properties, list):
        for prop in properties:
            params[prop["name"]] = prop["value"]
    elif isinstance(app_json, dict):
        # In case raw dictionary body was passed
        for k, v in app_json.items():
            if k != "properties":
                params[k] = v

    return params


def route_request(action_group: str, api_path: str, http_method: str, function_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Routes the request to appropriate backend database/API action.
    Supports both OpenAPI path matching and Bedrock Function-calling matching.
    """
    logger.info(f"Routing request: apiPath={api_path}, method={http_method}, function={function_name}, params={params}")

    # 1. Get Order Details
    if api_path == "/orders/{orderId}" and http_method == "GET" or function_name == "getOrder":
        order_id = params.get("orderId") or params.get("order_id")
        if not order_id:
            return {"status_code": 400, "body": {"error": "Missing orderId parameter."}}
        order = get_order_by_id(order_id)
        if order:
            return {"status_code": 200, "body": order}
        return {"status_code": 404, "body": {"error": f"Order {order_id} not found."}}

    # 2. List Orders for a Customer
    elif (api_path == "/orders" and http_method == "GET") or function_name == "listCustomerOrders":
        customer = params.get("customer") or params.get("customer_id") or params.get("customer_name")
        if not customer:
            return {"status_code": 400, "body": {"error": "Missing customer identifier parameter."}}
        orders = list_orders_by_customer(customer)
        return {"status_code": 200, "body": {"count": len(orders), "orders": orders}}

    # 3. Cancel Order
    elif (api_path == "/orders/{orderId}/cancel" and http_method == "POST") or function_name == "cancelOrder":
        order_id = params.get("orderId") or params.get("order_id")
        reason = params.get("reason", "Customer requested cancellation")
        if not order_id:
            return {"status_code": 400, "body": {"error": "Missing orderId parameter."}}
        result = cancel_order(order_id, reason)
        status_code = 200 if result.get("success") else 400
        return {"status_code": status_code, "body": result}

    # 4. Create New Order
    elif (api_path == "/orders" and http_method == "POST") or function_name == "createOrder":
        customer_name = params.get("customer_name") or params.get("customer")
        product = params.get("product") or params.get("product_id") or params.get("product_name")
        quantity = int(params.get("quantity", 1))

        if not customer_name or not product:
            return {"status_code": 400, "body": {"error": "Missing required fields: customer_name, product."}}

        result = create_order(customer_name, product, quantity)
        status_code = 201 if result.get("success") else 400
        return {"status_code": status_code, "body": result}

    # 5. Get Product Info / Check Inventory
    elif (api_path == "/products/{productId}" and http_method == "GET") or function_name == "getProduct":
        product_id = params.get("productId") or params.get("product_id") or params.get("search")
        if not product_id:
            return {"status_code": 400, "body": {"error": "Missing productId parameter."}}
        product = get_product_by_id_or_name(product_id)
        if product:
            return {"status_code": 200, "body": product}
        return {"status_code": 404, "body": {"error": f"Product '{product_id}' not found."}}

    # 6. List Products Catalog
    elif (api_path == "/products" and http_method == "GET") or function_name == "listProducts":
        category = params.get("category")
        products = list_products(category)
        return {"status_code": 200, "body": {"count": len(products), "products": products}}

    # Fallback / Unknown route
    return {
        "status_code": 404,
        "body": {
            "error": f"Action not recognized. apiPath={api_path}, method={http_method}, function={function_name}"
        }
    }


def lambda_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """
    AWS Lambda entry point for Bedrock Agent Action Group invocations.
    """
    logger.info(f"Received Bedrock Agent Event: {json.dumps(event)}")
    init_database()

    action_group = event.get("actionGroup", "DefaultActionGroup")
    api_path = event.get("apiPath", "")
    http_method = event.get("httpMethod", "")
    function_name = event.get("function", "")

    # Extract all parameters from query, path, and body
    params = extract_parameters(event)

    # Route and execute backend logic
    action_result = route_request(action_group, api_path, http_method, function_name, params)
    status_code = action_result["status_code"]
    response_body = action_result["body"]

    # Construct Bedrock Agent expected response format
    # Note: Bedrock expects responseBody.application/json.body as a JSON-serialized string or raw text
    json_body_str = json.dumps(response_body)

    if function_name:
        # Function-based Action Group response format
        response = {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": action_group,
                "function": function_name,
                "functionResponse": {
                    "responseBody": {
                        "TEXT": {
                            "body": json_body_str
                        }
                    }
                }
            }
        }
    else:
        # OpenAPI API-path based Action Group response format
        response = {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": action_group,
                "apiPath": api_path,
                "httpMethod": http_method,
                "httpStatusCode": status_code,
                "responseBody": {
                    "application/json": {
                        "body": json_body_str
                    }
                }
            },
            "sessionAttributes": event.get("sessionAttributes", {}),
            "promptSessionAttributes": event.get("promptSessionAttributes", {})
        }

    logger.info(f"Returning Bedrock Agent Response: {json.dumps(response)}")
    return response
