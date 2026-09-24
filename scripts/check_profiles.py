import os
import boto3
from dotenv import load_dotenv

load_dotenv()

bedrock = boto3.client(
    "bedrock",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION", "us-east-1")
)

try:
    response = bedrock.list_inference_profiles(typeEquals="SYSTEM_DEFINED")
    print("Available System Defined Inference Profiles:")
    for prof in response.get("inferenceProfileSummaries", []):
        name = prof.get("inferenceProfileName", "")
        pid = prof.get("inferenceProfileId", "")
        if "sonnet" in name.lower() or "haiku" in name.lower():
            print(f" - {name}: {pid}")
except Exception as e:
    print(f"Error: {e}")
