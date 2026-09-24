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

candidates = [
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "us.anthropic.claude-sonnet-4-6",
    "us.anthropic.claude-sonnet-5",
    "amazon.titan-text-express-v1",
    "amazon.titan-text-lite-v1",
    "us.amazon.nova-lite-v1:0",
    "us.amazon.nova-pro-v1:0"
]

for model_id in candidates:
    try:
        response = bedrock_runtime.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": "Hi! Answer with 'OK' and your model name."}]}],
            inferenceConfig={"maxTokens": 50, "temperature": 0.1}
        )
        reply = response["output"]["message"]["content"][0]["text"].strip()
        print(f"[ACTIVE & WORKING] {model_id} -> {reply}")
        break
    except Exception as e:
        err = str(e)
        if "AccessDeniedException" in err:
            status = "Need Model Access Request"
        elif "ResourceNotFoundException" in err:
            status = "Legacy / Not Found"
        elif "ValidationException" in err:
            status = "Validation Error"
        else:
            status = err[:80]
        print(f" - {model_id}: {status}")
