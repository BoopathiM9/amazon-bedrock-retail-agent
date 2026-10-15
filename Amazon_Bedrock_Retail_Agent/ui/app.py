"""
1-Page Streamlit Chat Interface for Amazon Bedrock Agent (Claude Sonnet 4.5).
Supports real-time streaming, tool use & Action Group execution trace visualization,
minimal token budget protection, and an offline simulator mode.
"""

import os
import sys
import uuid
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from ui.bedrock_service import invoke_bedrock_agent_live, mock_agent_stream, DEFAULT_MODEL_ID

# Page Configuration
st.set_page_config(
    page_title="Nova AI Agent (Claude Sonnet 4.5)",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .main-title {
        font-size: 2.1rem;
        font-weight: 700;
        margin-bottom: 0.1rem;
        color: #1E293B;
    }
    .sub-title {
        font-size: 1.0rem;
        color: #64748B;
        margin-bottom: 1.2rem;
    }
    .badge-live {
        background-color: #DCFCE7;
        color: #166534;
        padding: 5px 12px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .badge-mock {
        background-color: #FEF3C7;
        color: #92400E;
        padding: 5px 12px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .cost-notice {
        background-color: #EFF6FF;
        border: 1px solid #BFDBFE;
        border-radius: 8px;
        padding: 8px 12px;
        font-size: 0.85rem;
        color: #1E40AF;
        margin-bottom: 12px;
    }
</style>
""", unsafe_allow_html=True)

# Initialize Session State
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "👋 Hello! I am your AI Retail & Support Assistant powered by **Amazon Bedrock (Anthropic Claude Sonnet 4.5)**.\n\n"
                "I am equipped with tools to query databases and handle customer requests:\n"
                "- 📦 **Order Tracking**: `Where is order ORD-1001?`\n"
                "- ❌ **Order Cancellation**: `Cancel order ORD-1003`\n"
                "- 🎧 **Product Catalog & Stock**: `What headphones do you have in stock?`\n"
                "- 📋 **Store Policies**: `What is your return & refund policy?`"
            ),
            "traces": []
        }
    ]

# --- SIDEBAR CONFIGURATION ---
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/9/93/Amazon_Web_Services_Logo.svg", width=75)
    st.title("Bedrock Agent Controls")

    mode_options = ["🟢 Live AWS Bedrock (Claude Sonnet 4.5)", "🧪 Local Simulator (Offline - $0.00)"]
    selected_mode = st.radio(
        "Execution Mode",
        options=mode_options,
        index=0,
        help="Live calls Claude Sonnet 4.5 on Amazon Bedrock. Simulator runs offline without AWS calls."
    )
    is_live_mode = "Live" in selected_mode

    st.divider()

    if is_live_mode:
        st.markdown("""
        <div class="cost-notice">
            💰 <b>Low-Cost Protected</b><br>
            Using pay-as-you-go serverless inference (approx. $0.001 per prompt). Your $200 AWS credit is fully safeguarded.
        </div>
        """, unsafe_allow_html=True)

        aws_region = st.text_input("AWS Region", value=os.getenv("AWS_REGION", "us-east-1"))
        model_id = st.text_input("Model Inference Profile", value=DEFAULT_MODEL_ID, help="Active Anthropic Claude Sonnet 4.5 profile")

        with st.expander("🔑 AWS Credentials Status", expanded=False):
            ak = os.getenv("AWS_ACCESS_KEY_ID", "")
            masked_ak = ak[:4] + "..." + ak[-4:] if len(ak) > 8 else "Not set"
            st.write(f"**Access Key**: `{masked_ak}`")
            st.caption("Credentials loaded securely from your `.env` file.")
    else:
        st.info("🧪 **Offline Simulator Mode**\nRuns locally with zero AWS API calls or charges.")
        aws_region = "local"
        model_id = "local-simulator"

    st.divider()
    enable_trace = st.checkbox("🔍 Inspect Agent Tool Traces", value=True, help="Display Action Group API calls and parameters executed by Claude.")

    if st.button("🔄 Reset Chat Session", use_container_width=True):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = [st.session_state.messages[0]]
        st.rerun()

    st.divider()
    st.subheader("💡 Try Quick Prompts")
    quick_prompts = [
        "Where is my order ORD-1001?",
        "Check stock for Titan Wireless Headphones",
        "What is your return & refund policy?",
        "Cancel order ORD-1003"
    ]
    for qp in quick_prompts:
        if st.button(qp, use_container_width=True, key=f"btn_{qp}"):
            st.session_state.queued_prompt = qp
            st.rerun()

# --- MAIN CONTENT AREA ---
col_header, col_status = st.columns([3, 1])
with col_header:
    st.markdown('<div class="main-title">Nova: Autonomous Retail AI Agent</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Amazon Bedrock • Anthropic Claude Sonnet 4.5 • Lambda Action Groups • Knowledge Base</div>', unsafe_allow_html=True)

with col_status:
    if is_live_mode:
        st.markdown('<span class="badge-live">● Live Bedrock (Sonnet 4.5)</span>', unsafe_allow_html=True)
        st.caption(f"AWS Account: `384875139605`")
    else:
        st.markdown('<span class="badge-mock">● Offline Simulator</span>', unsafe_allow_html=True)
        st.caption("No AWS API Calls")

st.markdown("---")

# Render Existing Chat Messages
for msg in st.session_state.messages:
    role = msg["role"]
    avatar = "🤖" if role == "assistant" else "👤"
    with st.chat_message(role, avatar=avatar):
        st.markdown(msg["content"])

        if enable_trace and msg.get("traces"):
            with st.expander("🛠️ Tool Executions & Reasoned Actions", expanded=False):
                for idx, trace in enumerate(msg["traces"]):
                    st.markdown(f"**Step {idx + 1}:**")
                    st.json(trace)

# Handle Input
user_input = None
if "queued_prompt" in st.session_state and st.session_state.queued_prompt:
    user_input = st.session_state.queued_prompt
    st.session_state.queued_prompt = None
else:
    user_input = st.chat_input("Type your message (e.g., Track ORD-1001 or check product stock)...")

if user_input:
    # 1. Render User Message
    st.session_state.messages.append({"role": "user", "content": user_input, "traces": []})
    with st.chat_message("user", avatar="👤"):
        st.markdown(user_input)

    # 2. Generate Assistant Response
    with st.chat_message("assistant", avatar="🤖"):
        message_placeholder = st.empty()
        full_response = ""
        captured_traces = []

        with st.spinner("Claude is reasoning with tools..."):
            if is_live_mode:
                generator = invoke_bedrock_agent_live(
                    prompt=user_input,
                    conversation_history=st.session_state.messages[:-1],
                    region=aws_region,
                    model_id=model_id,
                    aws_access_key=os.getenv("AWS_ACCESS_KEY_ID"),
                    aws_secret_key=os.getenv("AWS_SECRET_ACCESS_KEY")
                )
            else:
                generator = mock_agent_stream(user_input, st.session_state.session_id)

            for event in generator:
                event_type = event.get("type")
                if event_type == "chunk":
                    full_response += event.get("text", "")
                    message_placeholder.markdown(full_response + "▌")
                elif event_type == "trace":
                    captured_traces.append(event.get("data", {}))
                elif event_type == "error":
                    full_response += f"\n\n🚨 **{event.get('message')}**"
                    message_placeholder.markdown(full_response)

        message_placeholder.markdown(full_response)

        if enable_trace and captured_traces:
            with st.expander("🛠️ Tool Executions & Reasoned Actions", expanded=False):
                for idx, trace in enumerate(captured_traces):
                    st.markdown(f"**Step {idx + 1}:**")
                    st.json(trace)

        st.session_state.messages.append({
            "role": "assistant",
            "content": full_response,
            "traces": captured_traces
        })
