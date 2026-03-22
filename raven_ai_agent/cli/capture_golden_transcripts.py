"""
Phase 9 Golden Transcript Capture Script

This script captures "golden transcripts" - expected conversation flows
that can be used for:
- Regression testing
- Documentation/examples
- Production runbooks

Usage:
    from raven_ai_agent.cli.capture_golden_transcripts import capture_transcript, save_transcript
    transcript = capture_transcript("sales_order_status")
    save_transcript(transcript, "golden_transcript_so_status.json")
"""
import json
import frappe
from datetime import datetime
from typing import Dict, List
from pathlib import Path

from raven_ai_agent.agents import SalesOrderFollowupAgent, ManufacturingAgent, PaymentAgent, WorkflowOrchestrator


# Define scenario templates
SCENARIOS = {
    "sales_order_status": {
        "description": "Check status of a specific Sales Order",
        "bot_type": "sales_order_follow_up",
        "commands": [
            "status SO-00763",
            "full status SO-00763",
        ]
    },
    "sales_order_list": {
        "description": "List recent sales orders",
        "bot_type": "sales_order_follow_up",
        "commands": [
            "list recent sales orders",
            "pending orders",
        ]
    },
    "manufacturing_work_order": {
        "description": "Create and manage work orders from SO",
        "bot_type": "manufacturing",
        "commands": [
            "show work orders",
            "mfg status SO-00763",
        ]
    },
    "payment_check": {
        "description": "Check payment status and create payments",
        "bot_type": "payment",
        "commands": [
            "payment outstanding",
            "overdue invoices",
        ]
    },
    "full_workflow": {
        "description": "Run complete SO to invoice workflow",
        "bot_type": "workflow_orchestrator",
        "commands": [
            "run SO-00763",
            "status SO-00763",
        ]
    },
}


def capture_transcript(scenario: str, user: str = "administrator@yourcompany.com") -> Dict:
    """
    Capture a golden transcript for a given scenario.
    """
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario}. Available: {list(SCENARIOS.keys())}")
    
    scenario_data = SCENARIOS[scenario]
    bot_type = scenario_data["bot_type"]
    
    transcript = {
        "scenario": scenario,
        "description": scenario_data["description"],
        "captured_at": datetime.now().isoformat(),
        "user": user,
        "turns": []
    }
    
    # Get agent
    if bot_type == "sales_order_follow_up":
        agent = SalesOrderFollowupAgent(user)
    elif bot_type == "manufacturing":
        agent = ManufacturingAgent()
    elif bot_type == "payment":
        agent = PaymentAgent()
    elif bot_type == "workflow_orchestrator":
        agent = WorkflowOrchestrator()
    
    print("=" * 60)
    print(f"Capturing Golden Transcript: {scenario}")
    print(f"Description: {scenario_data['description']}")
    print("=" * 60)
    
    for command in scenario_data["commands"]:
        print(f"\n>> {user}: {command}")
        try:
            response = agent.process_command(command)
            print(f"<< Raven: {response[:200]}..." if len(str(response)) > 200 else f"<< Raven: {response}")
            
            transcript["turns"].append({
                "user_message": command,
                "bot_response": response,
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            error_msg = str(e)
            print(f"<< ERROR: {error_msg}")
            transcript["turns"].append({
                "user_message": command,
                "bot_response": f"ERROR: {error_msg}",
                "timestamp": datetime.now().isoformat(),
                "error": True
            })
    
    print("\n" + "=" * 60)
    print("Transcript capture complete!")
    print("=" * 60)
    
    return transcript


def save_transcript(transcript: Dict, filename: str, output_dir: str = "cli/golden_transcripts") -> str:
    """Save transcript to a JSON file."""
    output_path = Path(output_dir) / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    transcript["version"] = "1.0"
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(transcript, f, indent=2, ensure_ascii=False)
    
    print(f"Transcript saved to: {output_path}")
    return str(output_path)


def load_transcript(filename: str) -> Dict:
    """Load a golden transcript from file."""
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    """Entry point for CLI execution."""
    print("=" * 60)
    print("Golden Transcript Capture Tool")
    print("=" * 60)
    print(f"Available scenarios: {list(SCENARIOS.keys())}")
    print()
    
    for scenario_name in SCENARIOS.keys():
        print(f"\nCapturing: {scenario_name}")
        transcript = capture_transcript(scenario_name)
        
        filename = f"golden_transcript_{scenario_name}.json"
        save_transcript(transcript, filename)
    
    print("\n" + "=" * 60)
    print("All golden transcripts captured!")
    print("=" * 60)


def run_and_capture():
    """
    Run curated scenarios and store request/response transcripts
    as JSON and Markdown under raven_ai_agent/transcripts/.
    """
    from raven_ai_agent.cli.so_lifecycle_scenario import run_so_lifecycle_scenario, run_scenario_2
    
    SITE_USER = "runbook_user@yourcompany.com"
    CHANNEL = "Raven Golden Runs"
    
    base_path = Path(frappe.get_app_path("raven_ai_agent"))
    out_dir = base_path / "transcripts"
    out_dir.mkdir(exist_ok=True)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"golden_{ts}.json"
    md_path = out_dir / f"golden_{ts}.md"

    all_records = []
    md_lines = [
        f"# Raven Golden Transcripts ({ts})",
        "",
        f"- User: {SITE_USER}",
        f"- Channel: {CHANNEL}",
        "",
    ]

    # Scenario A: SO lifecycle (reuse existing CLI)
    md_lines.append("## Scenario A: SO Lifecycle")
    md_lines.append("")
    for msg, resp in run_so_lifecycle_scenario(user=SITE_USER, channel=CHANNEL):
        record = {
            "scenario": "so_lifecycle",
            "user": SITE_USER,
            "channel": CHANNEL,
            "message": msg,
            "response": resp,
        }
        all_records.append(record)
        md_lines.append(f"**User:** {msg}")
        md_lines.append("")
        md_lines.append(f"**Raven:** {resp}")
        md_lines.append("")

    md_lines.append("---")
    md_lines.append("")

    # Scenario B: Workflow + MFG + Payments (Scenario 2)
    md_lines.append("## Scenario B: Workflow + MFG + Payments")
    md_lines.append("")
    for msg, resp in run_scenario_2(user=SITE_USER, channel=CHANNEL):
        record = {
            "scenario": "workflow_mfg_payments",
            "user": SITE_USER,
            "channel": CHANNEL,
            "message": msg,
            "response": resp,
        }
        all_records.append(record)
        md_lines.append(f"**User:** {msg}")
        md_lines.append("")
        md_lines.append(f"**Raven:** {resp}")
        md_lines.append("")

    json_path.write_text(json.dumps(all_records, indent=2), encoding="utf-8")
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    print(f"Wrote JSON transcripts to: {json_path}")
    print(f"Wrote Markdown runbook to: {md_path}")


if __name__ == "__main__":
    run_and_capture()
