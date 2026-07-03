import os
import re
import json
from typing import Any
from pydantic import BaseModel
from google.adk.workflow import Workflow, START, node, FunctionNode
from google.adk.agents import LlmAgent
from google.adk.tools import AgentTool, ToolContext
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.agents.context import Context
from google.adk.apps import App, ResumabilityConfig
from google.adk.models import Gemini
from google.genai import types
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from app.config import config

# Set up MCP tools connection parameters to point to the local mcp_server.py
mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="uv",
            args=["run", "python", "-m", "app.mcp_server"],
        ),
    )
)

# ─── RETRY CONFIGURATION ───
retry_config = types.HttpRetryOptions(
    attempts=5,
    initial_delay=2.0,
    max_delay=10.0,
    http_status_codes=[503, 429]
)

# ─── SPECIALIZED SUB-AGENTS ───

trial_matcher_agent = LlmAgent(
    name="trial_matcher_agent",
    model=Gemini(model=config.model, retry_options=retry_config),
    instruction="""You are a Clinical Trial Matching Specialist. 
Your goal is to search for clinical trials and extract detailed trial criteria for specific studies.
Always use search_clinical_trials to find trials, and get_trial_details to look up a trial's specifics.
Provide accurate trial listings and highlight key facts like title, location, status, and criteria.""",
    description="Specialist agent that searches and matches clinical trials for specific conditions.",
    tools=[mcp_toolset]
)

eligibility_simplifier_agent = LlmAgent(
    name="eligibility_simplifier_agent",
    model=Gemini(model=config.model, retry_options=retry_config),
    instruction="""You are a Medical Eligibility Simplifier.
Your job is to translate complex medical terms and abbreviations into simple, patient-friendly explanations.
Analyze inclusion and exclusion criteria and explain them in clear, layman's terms.
Use the translate_jargon tool to look up and define complex terms.""",
    description="Specialist agent that simplifies medical terminology and eligibility criteria.",
    tools=[mcp_toolset]
)

# ─── ORCHESTRATOR TOOLS ───

def request_trial_registration(
    trial_id: str,
    patient_name: str,
    email: str,
    tool_context: ToolContext
) -> dict:
    """Initiates registration/application for a specific clinical trial.
    Call this tool only when the user explicitly requests to sign up, apply, or register for a trial.

    Args:
        trial_id: The NCT identification ID (e.g. 'NCT01123456').
        patient_name: The patient's full name.
        email: The patient's contact email.

    Returns:
        A status dictionary indicating that consent is pending.
    """
    coordinator_email = "coordination@trial-registry.org"
    if "NCT01123456" in trial_id:
        coordinator_email = "lung_trials@bostonmedical.org"
    elif "NCT02234567" in trial_id:
        coordinator_email = "melanoma_study@sfhealth.org"
    elif "NCT03345678" in trial_id:
        coordinator_email = "diabetes_research@nyu.edu"

    # Store registration details in the state for the workflow checkpoint
    tool_context.state["pending_registration"] = {
        "trial_id": trial_id,
        "patient_name": patient_name,
        "email": email,
        "coordinator_email": coordinator_email
    }
    
    return {
        "status": "pending_consent",
        "message": f"Registration request initiated for {trial_id}. Awaiting human-in-the-loop consent approval."
    }

# ─── ORCHESTRATOR AGENT ───

health_navigator_orchestrator = LlmAgent(
    name="health_navigator_orchestrator",
    model=Gemini(model=config.model, retry_options=retry_config),
    instruction="""You are the Health Navigator Orchestrator. 
Your goal is to guide patients in finding clinical trials and understanding eligibility requirements.
You coordinate between the Trial Matcher Specialist and the Eligibility Simplifier Specialist.

CRITICAL INSTRUCTIONS FOR REGISTRATION:
- If the user explicitly requests to apply, sign up, or register for a trial (e.g. saying "I want to apply", "register me", etc.), you MUST call the request_trial_registration tool.
- Use the most recently discussed or mentioned clinical trial ID (such as 'NCT01123456') from the conversation history as the trial_id argument. Do NOT search for trials or consult Trial Matcher Specialist when the user is trying to register.
- Extract the user's name (e.g., 'John Doe') and email (e.g., 'john.doe@example.com') from the message and pass them as patient_name and email arguments.
- If an SSN is present (even if redacted as [REDACTED SSN]), do NOT mention or ask for the SSN. Just call the registration tool with the name and email.

OTHER ROLES:
- Use Trial Matcher Specialist to find trials matching the user's condition.
- Use Eligibility Simplifier Specialist to translate complex terms or check eligibility criteria.
Be professional, empathetic, clear, and explain which specialist you are consulting.""",
    description="Main coordinator agent for Health Navigator.",
    tools=[
        AgentTool(trial_matcher_agent),
        AgentTool(eligibility_simplifier_agent),
        request_trial_registration
    ]
)

# ─── WORKFLOW NODES ───

async def security_checkpoint(ctx: Context, node_input: types.Content):
    # Extract text from input Content
    text_input = ""
    if node_input and node_input.parts:
        text_input = "".join([p.text for p in node_input.parts if p.text])
    
    # Audit log template
    audit_log = {
        "event": "security_checkpoint_evaluation",
        "session_id": ctx.session.id,
        "input_length": len(text_input),
        "pii_scrubbed": False,
        "injection_detected": False,
        "domain_rule_triggered": False,
        "status": "AUTHORIZED"
    }
    
    # 1. PII Scrubbing (Regex for Social Security Numbers)
    ssn_regex = r"\b\d{3}-\d{2}-\d{4}\b"
    scrubbed_text = text_input
    if re.search(ssn_regex, text_input):
        scrubbed_text = re.sub(ssn_regex, "[REDACTED SSN]", text_input)
        audit_log["pii_scrubbed"] = True
    
    # 2. Prompt Injection Detection
    injection_keywords = [
        "ignore previous instructions",
        "system prompt",
        "dan mode",
        "override rules",
        "you are now a",
        "ignore all rules"
    ]
    has_injection = any(kw in text_input.lower() for kw in injection_keywords)
    if has_injection:
        audit_log["injection_detected"] = True
        audit_log["status"] = "REJECTED"
        print(json.dumps({"severity": "CRITICAL", "message": "Prompt injection attempt blocked", "details": audit_log}))
        yield Event(output="Security threat detected: unauthorized prompt manipulation attempt.", route="SECURITY_EVENT")
        return
        
    # 3. Domain-specific rule (Consent / Minors block)
    minor_match = re.search(r"\b(i'm|i am|age is|age:)\s*([1-9]|1[0-7])\b", text_input.lower())
    if minor_match:
        audit_log["domain_rule_triggered"] = True
        audit_log["status"] = "REJECTED"
        print(json.dumps({"severity": "WARNING", "message": "Domain policy exception: User age under 18", "details": audit_log}))
        yield Event(output="Policy Restriction: Users must be 18 years or older to participate or request clinical trial matches.", route="SECURITY_EVENT")
        return
        
    print(json.dumps({"severity": "INFO", "message": "Input authorized", "details": audit_log}))
    
    # Yield scrubbed content as output to route to the orchestrator
    scrubbed_content = types.Content(role="user", parts=[types.Part.from_text(text=scrubbed_text)])
    yield Event(output=scrubbed_content, route="AUTHORIZED")

def security_breach_handler(node_input: str):
    warning = f"⚠️ [Security / Policy Violation]: {node_input}"
    return Event(
        output=warning,
        content=types.Content(role='model', parts=[types.Part.from_text(text=warning)])
    )

async def registration_checkpoint(ctx: Context, node_input: Any):
    pending = ctx.state.get("pending_registration")
    if not pending:
        return

    # Awaiting consent via interrupt
    if not ctx.resume_inputs or "confirm_registration" not in ctx.resume_inputs:
        yield RequestInput(
            interrupt_id="confirm_registration",
            message=f"✋ [HITL Consent Required]\nDo you consent to share your name ({pending.get('patient_name')}) and contact email ({pending.get('email')}) with the study coordinators for trial {pending.get('trial_id')}? Please reply 'Yes' or 'No'."
        )
        return

    # Process response
    consent_reply = ctx.resume_inputs["confirm_registration"].strip().lower()
    
    log_entry = {
        "event": "registration_consent_decision",
        "trial_id": pending.get('trial_id'),
        "user_reply": consent_reply,
        "session_id": ctx.session.id
    }
    
    if consent_reply in ["yes", "y", "agree", "confirm"]:
        print(json.dumps({"severity": "INFO", "message": "Consent granted", "details": log_entry}))
        result_msg = (
            f"✅ Consent granted. Your registration details have been forwarded to {pending.get('coordinator_email')}.\n"
            f"A coordinator will reach out to you at {pending.get('email')} soon."
        )
    else:
        print(json.dumps({"severity": "WARNING", "message": "Consent denied", "details": log_entry}))
        result_msg = "❌ Consent declined. Registration aborted and no personal details were shared."

    yield Event(
        output=result_msg,
        content=types.Content(role='model', parts=[types.Part.from_text(text=result_msg)]),
        state={"pending_registration": None}
    )

# ─── WORKFLOW GRAPH ───

health_navigator_workflow = Workflow(
    name="health_navigator_workflow",
    edges=[
        (START, security_checkpoint),
        (security_checkpoint, {
            'AUTHORIZED': health_navigator_orchestrator,
            'SECURITY_EVENT': security_breach_handler
        }),
        (health_navigator_orchestrator, registration_checkpoint),
    ]
)

# ─── APP INSTANCE ───

app = App(
    root_agent=health_navigator_workflow,
    name="app",
    resumability_config=ResumabilityConfig(is_resumable=True)
)

root_agent = health_navigator_workflow

