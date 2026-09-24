import os
import boto3
from dotenv import load_dotenv

load_dotenv()

bedrock_runtime = boto3.client(
    "bedrock-runtime",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION", "us-east-1")
)

model_id = "us.anthropic.claude-sonnet-4-20250514-v1:0"

try:
    response = bedrock_runtime.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": "Hello, Claude! Respond in 1 brief sentence."}]}]
    )
    reply = response["output"]["message"]["content"][0]["text"]
    print(f"[SUCCESS] Claude Sonnet 4 responded: {reply}")
except Exception as e:
    print(f"[ERROR] Failed to invoke {model_id}: {e}")
