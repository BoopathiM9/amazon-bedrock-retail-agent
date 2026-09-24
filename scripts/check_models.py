import os
import boto3
from dotenv import load_dotenv

load_dotenv()

aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
region = os.getenv("AWS_REGION", "us-east-1")

bedrock = boto3.client(
    "bedrock",
    aws_access_key_id=aws_access_key,
    aws_secret_access_key=aws_secret_key,
    region_name=region
)

try:
    response = bedrock.list_foundation_models(byProvider="Anthropic")
    print("Available Anthropic Models in your account:")
    for m in response.get("modelSummaries", []):
        model_id = m.get("modelId")
        name = m.get("modelName")
        if "sonnet" in model_id.lower() or "haiku" in model_id.lower():
            print(f" - {name}: {model_id}")
except Exception as e:
    print(f"Error: {e}")
