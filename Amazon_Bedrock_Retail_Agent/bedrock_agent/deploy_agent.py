"""
Automated Bedrock Agent Deployment and Setup Script using Boto3.
Can create or update the Bedrock Agent, attach the Action Group, prepare the agent, and create an alias.
"""

import os
import json
import time
import argparse
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL_ID = "anthropic.claude-3-5-sonnet-20240620-v1:0"
DEFAULT_AGENT_NAME = "RetailOrderSupportAgent"


def get_bedrock_agent_client(region: str):
    return boto3.client("bedrock-agent", region_name=region)


def load_file_content(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def create_or_get_agent_role(iam_client, role_name: str = "AmazonBedrockExecutionRoleForAgent") -> str:
    """Creates or retrieves the IAM role for Bedrock Agent."""
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "bedrock.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }
        ]
    }

    try:
        response = iam_client.get_role(RoleName=role_name)
        print(f"[INFO] Found existing IAM Role: {role_name}")
        return response["Role"]["Arn"]
    except iam_client.exceptions.NoSuchEntityException:
        print(f"[INFO] Creating IAM Role: {role_name}")
        res = iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="Bedrock Agent execution role created for retail order assistant"
        )
        role_arn = res["Role"]["Arn"]

        # Attach policy to allow invoking Claude 3.5 Sonnet
        bedrock_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": ["bedrock:InvokeModel*"],
                    "Resource": "*"
                }
            ]
        }
        iam_client.put_role_policy(
            RoleName=role_name,
            PolicyName="BedrockModelInvocationPolicy",
            PolicyDocument=json.dumps(bedrock_policy)
        )
        # Give IAM a few seconds to propagate
        time.sleep(5)
        return role_arn


def deploy_agent(
    region: str,
    agent_name: str,
    model_id: str,
    lambda_arn: str = None,
    schema_path: str = "schemas/openapi_schema.json",
    instructions_path: str = "bedrock_agent/agent_instructions.txt"
):
    print(f"=== Starting Bedrock Agent Deployment in {region} ===")
    bedrock_agent = get_bedrock_agent_client(region)
    iam = boto3.client("iam")

    # 1. Setup IAM Role
    role_arn = create_or_get_agent_role(iam)
    print(f"Role ARN: {role_arn}")

    # 2. Check if agent already exists
    instructions = load_file_content(instructions_path)
    existing_agents = bedrock_agent.list_agents().get("agentSummaries", [])
    agent_id = None

    for agent in existing_agents:
        if agent["agentName"] == agent_name:
            agent_id = agent["agentId"]
            print(f"[INFO] Found existing agent '{agent_name}' with ID: {agent_id}")
            break

    if not agent_id:
        print(f"[INFO] Creating new Bedrock Agent '{agent_name}'...")
        create_res = bedrock_agent.create_agent(
            agentName=agent_name,
            instruction=instructions,
            foundationModel=model_id,
            agentResourceRoleArn=role_arn,
            description="Autonomous retail order and product support assistant"
        )
        agent_id = create_res["agent"]["agentId"]
        print(f"[SUCCESS] Created Agent with ID: {agent_id}")
    else:
        print(f"[INFO] Updating Agent '{agent_name}'...")
        bedrock_agent.update_agent(
            agentId=agent_id,
            agentName=agent_name,
            instruction=instructions,
            foundationModel=model_id,
            agentResourceRoleArn=role_arn
        )

    # 3. Create or Update Action Group if Lambda ARN provided
    if lambda_arn:
        action_group_name = "OrderManagementActionGroup"
        schema_json = load_file_content(schema_path)
        print(f"[INFO] Configuring Action Group '{action_group_name}' with Lambda: {lambda_arn}")

        # Check existing action groups
        ag_list = bedrock_agent.list_agent_action_groups(agentId=agent_id, agentVersion="DRAFT")
        existing_ag_id = None
        for ag in ag_list.get("actionGroupSummaries", []):
            if ag["actionGroupName"] == action_group_name:
                existing_ag_id = ag["actionGroupId"]
                break

        if existing_ag_id:
            bedrock_agent.update_agent_action_group(
                agentId=agent_id,
                agentVersion="DRAFT",
                actionGroupId=existing_ag_id,
                actionGroupName=action_group_name,
                description="APIs for tracking orders, listing products, and managing order state",
                actionGroupExecutor={"lambda": lambda_arn},
                apiSchema={"payload": schema_json},
                actionGroupState="ENABLED"
            )
            print("[SUCCESS] Updated existing Action Group.")
        else:
            bedrock_agent.create_agent_action_group(
                agentId=agent_id,
                agentVersion="DRAFT",
                actionGroupName=action_group_name,
                description="APIs for tracking orders, listing products, and managing order state",
                actionGroupExecutor={"lambda": lambda_arn},
                apiSchema={"payload": schema_json},
                actionGroupState="ENABLED"
            )
            print("[SUCCESS] Created Action Group.")

    # 4. Prepare Agent
    print("[INFO] Preparing Agent...")
    bedrock_agent.prepare_agent(agentId=agent_id)
    time.sleep(3)

    # 5. Create or Get Agent Alias
    alias_name = "live"
    alias_id = None
    aliases = bedrock_agent.list_agent_aliases(agentId=agent_id).get("agentAliasSummaries", [])
    for alias in aliases:
        if alias["agentAliasName"] == alias_name:
            alias_id = alias["agentAliasId"]
            print(f"[INFO] Found existing alias '{alias_name}': {alias_id}")
            break

    if not alias_id:
        print(f"[INFO] Creating alias '{alias_name}'...")
        res_alias = bedrock_agent.create_agent_alias(
            agentId=agent_id,
            agentAliasName=alias_name,
            description="Live production alias"
        )
        alias_id = res_alias["agentAlias"]["agentAliasId"]
        print(f"[SUCCESS] Created Agent Alias: {alias_id}")

    print("\n" + "=" * 50)
    print("DEPLOYMENT COMPLETE! Set these in your .env or Streamlit UI:")
    print(f"BEDROCK_AGENT_ID={agent_id}")
    print(f"BEDROCK_AGENT_ALIAS_ID={alias_id}")
    print(f"AWS_REGION={region}")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy Amazon Bedrock Agent")
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"), help="AWS Region")
    parser.add_argument("--name", default=DEFAULT_AGENT_NAME, help="Bedrock Agent Name")
    parser.add_argument("--model", default=DEFAULT_MODEL_ID, help="Foundation Model ID")
    parser.add_argument("--lambda-arn", default=os.getenv("LAMBDA_ARN", None), help="Lambda Function ARN for Action Group")
    args = parser.parse_args()

    deploy_agent(
        region=args.region,
        agent_name=args.name,
        model_id=args.model,
        lambda_arn=args.lambda_arn
    )
