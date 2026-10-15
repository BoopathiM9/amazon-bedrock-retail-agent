import os
import json
import boto3
from dotenv import load_dotenv

load_dotenv()

from backend_lambda.lambda_combined import lambda_handler

bedrock_runtime = boto3.client(
    "bedrock-runtime",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION", "us-east-1")
)

MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

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
        }
    ]
}

messages = [
    {"role": "user", "content": [{"text": "Where is my order ORD-1001?"}]}
]

print("Invoking Claude Sonnet 4.5 with tool configuration...")
response = bedrock_runtime.converse(
    modelId=MODEL_ID,
    messages=messages,
    toolConfig=TOOL_CONFIG
)

stop_reason = response["stopReason"]
print("Stop reason:", stop_reason)

if stop_reason == "tool_use":
    message = response["output"]["message"]
    messages.append(message)
    
    # Process tool uses
    tool_results = []
    for content in message["content"]:
        if "toolUse" in content:
            tool_use = content["toolUse"]
            tool_name = tool_use["name"]
            tool_input = tool_use["input"]
            tool_id = tool_use["toolUseId"]
            print(f"[TOOL CALLED] {tool_name} with params {tool_input}")
            
            # Execute backend Lambda logic
            event = {
                "actionGroup": "OrderActionGroup",
                "function": tool_name,
                "parameters": [{"name": k, "type": "string", "value": v} for k, v in tool_input.items()]
            }
            res = lambda_handler(event)
            body_str = res["response"]["functionResponse"]["responseBody"]["TEXT"]["body"]
            print(f"[TOOL RESULT] {body_str}")
            
            tool_results.append({
                "toolResult": {
                    "toolUseId": tool_id,
                    "content": [{"json": json.loads(body_str)}]
                }
            })
    
    messages.append({"role": "user", "content": tool_results})
    
    # Get final answer from Claude
    final_res = bedrock_runtime.converse(
        modelId=MODEL_ID,
        messages=messages,
        toolConfig=TOOL_CONFIG
    )
    final_text = final_res["output"]["message"]["content"][0]["text"]
    print(f"\n[FINAL CLAUDE RESPONSE]\n{final_text}")
