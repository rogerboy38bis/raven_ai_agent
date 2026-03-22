"""
Phase 9 Scenario Script: SO Lifecycle + Manufacturing Delay + Payment Edge

This script simulates a realistic conversation flow with the Raven AI Agent
to test the multi-agent orchestration and context memory systems.

Usage:
    from raven_ai_agent.cli.so_lifecycle_scenario import run_so_lifecycle_scenario, main
    run_so_lifecycle_scenario()
    main()  # runs with default settings
"""
import frappe
from unittest.mock import MagicMock


# Default configuration - adjust for your environment
SITE_USER = "administrator@yourcompany.com"  # change if needed


def run_so_lifecycle_scenario(
    user: str = SITE_USER,
    so_name: str = "SO-00763-LORAND LABORATORIES"
) -> list:
    """
    Run the Phase 9 scenario: SO lifecycle + manufacturing delay + payment edge.
    
    This executes a sequence of commands that test:
    - Basic SO queries (list, status)
    - Multi-agent pipelines (diagnose and fix, workflow run)
    - Payment checking
    - Context memory across turns
    
    Args:
        user: The user to run as
        so_name: The Sales Order to test with (use full name from your system)
        
    Returns:
        List of (message, response) tuples for transcript capture
    """
    transcript = []
    
    def send_to_agent(bot_type: str, msg: str) -> str:
        """Send message to appropriate agent and return response."""
        print(f"\n>> {user}: {msg}")
        try:
            if bot_type == "sales_order_follow_up":
                from raven_ai_agent.agents import SalesOrderFollowupAgent
                agent = SalesOrderFollowupAgent(user)
                response = agent.process_command(msg)
            elif bot_type == "manufacturing":
                from raven_ai_agent.agents import ManufacturingAgent
                agent = ManufacturingAgent()
                response = agent.process_command(msg)
            elif bot_type == "payment":
                from raven_ai_agent.agents import PaymentAgent
                agent = PaymentAgent()
                response = agent.process_command(msg)
            elif bot_type == "workflow_orchestrator":
                from raven_ai_agent.agents import WorkflowOrchestrator
                agent = WorkflowOrchestrator()
                response = agent.process_command(msg)
            else:
                response = f"Unknown bot type: {bot_type}"
            
            # Truncate long responses for display
            if response and len(str(response)) > 500:
                print(f"<< Raven: {response[:500]}...")
            else:
                print(f"<< Raven: {response}")
            return response
        except Exception as e:
            error_msg = f"ERROR: {e}"
            print(f"<< {error_msg}")
            import traceback
            traceback.print_exc()
            return error_msg
    
    print("=" * 60)
    print("Phase 9 Scenario 1: SO lifecycle + manufacturing delay + payment edge")
    print(f"Using SO: {so_name}")
    print("=" * 60)
    
    # 1) List recent sales orders
    response = send_to_agent("sales_order_follow_up", "list recent sales orders")
    transcript.append(("@ai list recent sales orders", response))
    
    # 2) Pick a specific SO and ask status
    response = send_to_agent("sales_order_follow_up", f"status {so_name}")
    transcript.append((f"@ai status {so_name}", response))
    
    # 3) Full status
    response = send_to_agent("sales_order_follow_up", f"full status {so_name}")
    transcript.append((f"@ai full status {so_name}", response))
    
    # 4) Manufacturing - show work orders for specific SO
    response = send_to_agent("manufacturing", f"show work orders for {so_name}")
    transcript.append((f"@ai show work orders for {so_name}", response))
    
    # 5) Manufacturing - manufacturing status for specific SO
    response = send_to_agent("manufacturing", f"mfg status {so_name}")
    transcript.append((f"@ai mfg status {so_name}", response))
    
    # 6) Payment - check outstanding invoices
    response = send_to_agent("payment", "payment outstanding")
    transcript.append(("@ai payment outstanding", response))
    
    # 7) Workflow orchestrator - run workflow
    response = send_to_agent("workflow_orchestrator", f"run {so_name}")
    transcript.append((f"@ai workflow run {so_name}", response))
    
    # 8) Workflow orchestrator - pipeline status
    response = send_to_agent("workflow_orchestrator", f"status {so_name}")
    transcript.append((f"@ai pipeline status {so_name}", response))
    
    print("\n" + "=" * 60)
    print("Scenario complete!")
    print("=" * 60)
    
    return transcript


def run_scenario_2(
    user: str = SITE_USER,
    so_name: str = "SO-00763-LORAND LABORATORIES"
) -> list:
    """
    Phase 9 Scenario 2: Morning Briefing + Manufacturing Status + Payments
    
    This scenario focuses on:
    - Morning briefing (sales summary + pending WOs + overdue payments)
    - Manufacturing status for a specific SO with many items
    - Payment tracking
    
    All commands are pre-tuned to return concrete data instead of help text.
    Key adjustments from Scenario 1 learnings:
    - Use full SO names (not shortened)
    - Use specific phrasing that maps to concrete actions
    - Include SO name in manufacturing commands
    
    Args:
        user: The user to run as
        so_name: The Sales Order to test with
        
    Returns:
        List of (message, response) tuples
    """
    transcript = []
    
    def send_to_agent(bot_type: str, msg: str) -> str:
        """Send message to appropriate agent and return response."""
        print(f"\n>> {user}: {msg}")
        try:
            if bot_type == "sales_order_follow_up":
                from raven_ai_agent.agents import SalesOrderFollowupAgent
                agent = SalesOrderFollowupAgent(user)
                response = agent.process_command(msg)
            elif bot_type == "manufacturing":
                from raven_ai_agent.agents import ManufacturingAgent
                agent = ManufacturingAgent()
                response = agent.process_command(msg)
            elif bot_type == "payment":
                from raven_ai_agent.agents import PaymentAgent
                agent = PaymentAgent()
                response = agent.process_command(msg)
            elif bot_type == "workflow_orchestrator":
                from raven_ai_agent.agents import WorkflowOrchestrator
                agent = WorkflowOrchestrator()
                response = agent.process_command(msg)
            else:
                response = f"Unknown bot type: {bot_type}"
            
            # Truncate long responses for display
            if response and len(str(response)) > 500:
                print(f"<< Raven: {response[:500]}...")
            else:
                print(f"<< Raven: {response}")
            return response
        except Exception as e:
            error_msg = f"ERROR: {e}"
            print(f"<< {error_msg}")
            import traceback
            traceback.print_exc()
            return error_msg
    
    print("=" * 60)
    print("Phase 9 Scenario 2: Morning Briefing + MFG Status + Payments")
    print(f"Using SO: {so_name}")
    print("=" * 60)
    
    # 1) Morning briefing via workflow orchestrator
    # Pre-tuned: morning briefing should return a summary dashboard
    response = send_to_agent("workflow_orchestrator", "morning briefing")
    transcript.append(("@ai morning briefing", response))
    
    # 2) Manufacturing status for SPECIFIC SO (not generic)
    # Pre-tuned: include SO name to get concrete data instead of help
    response = send_to_agent("manufacturing", f"mfg status {so_name}")
    transcript.append((f"@ai mfg status {so_name}", response))
    
    # 3) Show work orders for specific SO
    # Pre-tuned: use "show work orders for <SO>" format
    response = send_to_agent("manufacturing", f"show work orders for {so_name}")
    transcript.append((f"@ai show work orders for {so_name}", response))
    
    # 4) Sales order status - full status
    # Pre-tuned: use "full status <SO>" for complete info
    response = send_to_agent("sales_order_follow_up", f"full status {so_name}")
    transcript.append((f"@ai full status {so_name}", response))
    
    # 5) Diagnose SO - find issues blocking the order
    # Pre-tuned: "diagnose <SO>" should return concrete issues
    response = send_to_agent("sales_order_follow_up", f"diagnose {so_name}")
    transcript.append((f"@ai diagnose {so_name}", response))
    
    # 6) Next steps for SO
    # Pre-tuned: "next steps <SO>" should return actionable items
    response = send_to_agent("sales_order_follow_up", f"next steps {so_name}")
    transcript.append((f"@ai next steps {so_name}", response))
    
    # 7) Payment status for specific SO
    # Pre-tuned: check payment status for specific SO
    response = send_to_agent("payment", f"payment status {so_name}")
    transcript.append((f"@ai payment status {so_name}", response))
    
    # 8) Workflow pipeline status
    # Pre-tuned: check workflow status for specific SO
    response = send_to_agent("workflow_orchestrator", f"status {so_name}")
    transcript.append((f"@ai pipeline status {so_name}", response))
    
    print("\n" + "=" * 60)
    print("Scenario 2 complete!")
    print("=" * 60)
    
    return transcript


def main():
    """Entry point for CLI execution."""
    print("Starting Phase 9 Scenario...")
    print(f"User: {SITE_USER}")
    print()
    
    run_so_lifecycle_scenario(user=SITE_USER)
    print("\n\n")
    run_scenario_2(user=SITE_USER)


if __name__ == "__main__":
    main()
