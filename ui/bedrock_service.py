"""
Bedrock Agent Runtime Service module.
Provides live agent execution using Anthropic Claude Sonnet on Amazon Bedrock
with native Tool Calling (Action Groups), Knowledge Base policy search,
and an offline simulator mode.
"""

import os
import sys
import json
import time
import uuid
from typing import Generator, Dict, Any, List, Optional
import boto3
from botocore.exceptions import ClientError, BotoCoreError

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    from backend_lambda.lambda_combined import lambda_handler
    from backend_lambda.database import (
        get_order_by_id, list_orders_by_customer, get_product_by_id_or_name, 
        list_products, cancel_order, create_order
    )
except ImportError:
    lambda_handler = None

# Active Claude Sonnet model ID in AWS Bedrock (US Inference Profile)
DEFAULT_MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

# Bedrock Tool Specification matching our Action Group
TOOL_CONFIG = {
    "tools": [
        {
            "toolSpec": {
                "name": "getOrder",
                "description": "Retrieves the current status, delivery date, customer name, items, and total amount for a specific order ID.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "orderId": {"type": "string", "description": "The unique order ID, e.g. ORD-1001"}
                        },
                        "required": ["orderId"]
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "cancelOrder",
                "description": "Cancels an order if eligible (In Transit or Processing) and initiates a refund.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "orderId": {"type": "string", "description": "The unique order ID to cancel, e.g. ORD-1001"},
                            "reason": {"type": "string", "description": "Reason for cancellation"}
                        },
                        "required": ["orderId"]
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "listProducts",
                "description": "Retrieves the retail catalog of available products, price, stock, and descriptions.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "category": {"type": "string", "description": "Optional category filter, e.g. Electronics, Wearables, Accessories"}
                        }
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "getProduct",
                "description": "Retrieves product specs, current price, and available inventory stock for a product ID or product name.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "productId": {"type": "string", "description": "The product ID or product name, e.g. PROD-001 or Titan Headphones"}
                        },
                        "required": ["productId"]
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "searchKnowledgeBase",
                "description": "Searches the store policy knowledge base for return windows, refunds, warranty, and shipping guidelines.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Policy query, e.g. return window, refund policy, shipping times"}
                        },
                        "required": ["query"]
                    }
                }
            }
        }
    ]
}

SYSTEM_PROMPT = [
    {
        "text": (
            "You are Nova, an intelligent, helpful, and professional Customer Support & Order Management Assistant for a Retail Store.\n"
            "You have access to tools to track orders, cancel orders, list products, check inventory, and search store policies.\n"
            "Guidelines:\n"
            "- When an order ID or product is referenced, use your tools to fetch accurate real-time data.\n"
            "- Always be concise, polite, and helpful.\n"
            "- If a product is out of stock, inform the customer politely and suggest alternatives.\n"
            "- If an order cannot be cancelled (e.g. already delivered), explain why clearly.\n"
        )
    }
]


def search_local_knowledge_base(query: str) -> str:
    """Simulates Knowledge Base retrieval from markdown policy documents."""
    query_lower = query.lower()
    docs_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "bedrock_agent", "knowledge_base_docs"))
    
    content = ""
    if any(k in query_lower for k in ["ship", "delivery", "track"]):
        shipping_file = os.path.join(docs_dir, "shipping_and_delivery.md")
        if os.path.exists(shipping_file):
            with open(shipping_file, "r", encoding="utf-8") as f:
                content += f.read()
    else:
        return_file = os.path.join(docs_dir, "return_policy.md")
        if os.path.exists(return_file):
            with open(return_file, "r", encoding="utf-8") as f:
                content += f.read()

    return content if content else "30-day return policy on all products. Standard shipping takes 3-5 days."


def execute_tool_call(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Routes tool call to our Lambda handler or Knowledge Base."""
    if tool_name == "searchKnowledgeBase":
        kb_text = search_local_knowledge_base(tool_input.get("query", ""))
        return {"documents": [{"content": kb_text, "source": "s3://retail-kb/store_policy.md"}]}

    event = {
        "actionGroup": "OrderManagementActionGroup",
        "function": tool_name,
        "parameters": [{"name": k, "type": "string", "value": str(v)} for k, v in tool_input.items()]
    }
    res = lambda_handler(event)
    body_str = res["response"]["functionResponse"]["responseBody"]["TEXT"]["body"]
    return json.loads(body_str)


def invoke_bedrock_agent_live(
    prompt: str,
    conversation_history: List[Dict[str, Any]],
    region: str = "us-east-1",
    model_id: str = DEFAULT_MODEL_ID,
    aws_access_key: Optional[str] = None,
    aws_secret_key: Optional[str] = None
) -> Generator[Dict[str, Any], None, None]:
    """
    Invokes Claude Sonnet on Amazon Bedrock with automatic tool calling.
    Streams back chunks and tool execution traces.
    """
    try:
        kwargs = {"region_name": region}
        if aws_access_key and aws_secret_key:
            kwargs["aws_access_key_id"] = aws_access_key
            kwargs["aws_secret_access_key"] = aws_secret_key

        bedrock_runtime = boto3.client("bedrock-runtime", **kwargs)

        # Build message history for Bedrock Converse API
        messages = []
        for msg in conversation_history:
            if msg["role"] in ["user", "assistant"]:
                messages.append({"role": msg["role"], "content": [{"text": msg["content"]}]})
        messages.append({"role": "user", "content": [{"text": prompt}]})

        # Step 1: Initial call to Claude with tools
        response = bedrock_runtime.converse(
            modelId=model_id,
            messages=messages,
            system=SYSTEM_PROMPT,
            toolConfig=TOOL_CONFIG,
            inferenceConfig={"temperature": 0.2, "maxTokens": 1000}
        )

        stop_reason = response["stopReason"]
        output_msg = response["output"]["message"]

        # Step 2: Check if Claude wants to use tools (Action Group execution)
        if stop_reason == "tool_use":
            messages.append(output_msg)
            tool_results = []

            for content_block in output_msg.get("content", []):
                if "toolUse" in content_block:
                    tool_use = content_block["toolUse"]
                    tool_name = tool_use["name"]
                    tool_input = tool_use.get("input", {})
                    tool_id = tool_use["toolUseId"]

                    # Yield trace to UI
                    yield {
                        "type": "trace",
                        "data": {
                            "step": "Tool Invocation",
                            "tool": tool_name,
                            "input": tool_input
                        }
                    }

                    # Execute tool
                    tool_result_data = execute_tool_call(tool_name, tool_input)

                    yield {
                        "type": "trace",
                        "data": {
                            "step": "Tool Output",
                            "tool": tool_name,
                            "output": tool_result_data
                        }
                    }

                    tool_results.append({
                        "toolResult": {
                            "toolUseId": tool_id,
                            "content": [{"json": tool_result_data}]
                        }
                    })

            messages.append({"role": "user", "content": tool_results})

            # Step 3: Stream the final answer from Claude
            stream_res = bedrock_runtime.converse_stream(
                modelId=model_id,
                messages=messages,
                system=SYSTEM_PROMPT,
                toolConfig=TOOL_CONFIG,
                inferenceConfig={"temperature": 0.2, "maxTokens": 1000}
            )

            for chunk_event in stream_res.get("stream", []):
                if "contentBlockDelta" in chunk_event:
                    delta = chunk_event["contentBlockDelta"].get("delta", {})
                    if "text" in delta:
                        yield {"type": "chunk", "text": delta["text"]}

        else:
            # Direct text answer without tools
            for c in output_msg.get("content", []):
                if "text" in c:
                    yield {"type": "chunk", "text": c["text"]}

    except ClientError as e:
        err_msg = e.response.get("Error", {}).get("Message", str(e))
        yield {"type": "error", "message": f"AWS Bedrock Error: {err_msg}"}
    except Exception as e:
        yield {"type": "error", "message": f"Error: {str(e)}"}


def mock_agent_stream(prompt: str, session_id: str) -> Generator[Dict[str, Any], None, None]:
    """Offline Simulator mode ($0.00 AWS cost)."""
    prompt_lower = prompt.lower().strip()
    traces = []
    response_text = ""

    if "cancel" in prompt_lower and ("ord-" in prompt_lower or "order" in prompt_lower):
        import re
        match = re.search(r"ord-\d+", prompt_lower)
        order_id = match.group(0).upper() if match else "ORD-1001"
        traces.append({"step": "Action Group Invocation", "tool": "cancelOrder", "input": {"orderId": order_id}})
        res = cancel_order(order_id)
        traces.append({"step": "Action Group Output", "response": res})
        if res.get("success"):
            response_text = f"Your order **{order_id}** has been successfully cancelled. A full refund of **${res['refund_amount']}** has been initiated."
        else:
            response_text = f"Could not cancel order **{order_id}**: {res.get('error')}"

    elif "ord-" in prompt_lower or ("order" in prompt_lower and any(w in prompt_lower for w in ["track", "status", "where"])):
        import re
        match = re.search(r"ord-\d+", prompt_lower)
        order_id = match.group(0).upper() if match else "ORD-1001"
        traces.append({"step": "Action Group Invocation", "tool": "getOrder", "input": {"orderId": order_id}})
        order = get_order_by_id(order_id)
        traces.append({"step": "Action Group Output", "response": order or {"error": "Not found"}})
        if order:
            response_text = (
                f"### Order Details for **{order['order_id']}**\n\n"
                f"- **Customer**: {order['customer_name']}\n"
                f"- **Item**: {order['product_name']} (Qty: {order['quantity']})\n"
                f"- **Total**: ${order['total_amount']:.2f}\n"
                f"- **Status**: `{order['status']}`\n"
                f"- **Estimated Delivery**: {order['delivery_date'] or 'N/A'}"
            )
        else:
            response_text = f"I could not locate an order with ID **{order_id}**."

    elif any(w in prompt_lower for w in ["return", "refund", "warranty", "shipping", "policy"]):
        traces.append({"step": "Knowledge Base Query", "source": "return_policy.md"})
        response_text = (
            "Based on our **Store Policy**:\n\n"
            "- **Return Window**: You have **30 days** from delivery to return any item in original condition.\n"
            "- **Refund Timeline**: Refunds are processed within 3 to 5 business days after inspection.\n"
            "- **Warranty**: All hardware products include a **1-Year Limited Manufacturer Warranty**.\n"
            "- **Standard Shipping**: Free on orders over $50 (3-5 business days)."
        )

    else:
        traces.append({"step": "Action Group Invocation", "tool": "listProducts"})
        products = list_products()
        traces.append({"step": "Action Group Output", "count": len(products)})
        prod_list = "\n".join([f"- **{p['name']}** (${p['price']}) - Stock: {p['stock']} left" for p in products[:4]])
        response_text = f"Here are popular products currently in our catalog:\n\n{prod_list}\n\nAsk me about any product or order!"

    for trace in traces:
        yield {"type": "trace", "data": trace}
        time.sleep(0.04)

    words = response_text.split(" ")
    buffer = ""
    for i, word in enumerate(words):
        buffer += word + " "
        if i % 3 == 0 or i == len(words) - 1:
            yield {"type": "chunk", "text": buffer}
            buffer = ""
            time.sleep(0.03)
