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
    so_name: str = "SO-00763-LORAND LABORATORIES",
    channel: str = "Raven Golden Runs"
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
        channel: The chat channel (for transcript metadata)
        
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
    so_name: str = "SO-00763-LORAND LABORATORIES",
    channel: str = "Raven Golden Runs"
) -> list:
    """
    Phase 9 Scenario 2: Workflow Status + Manufacturing + Payments
    
    This scenario focuses on:
    - Workflow status for a specific SO
    - Manufacturing status for a specific SO with many items
    - Payment tracking for the customer
    
    All commands are pre-tuned to return concrete data instead of help text.
    Key adjustments from Scenario 1 learnings:
    - Use full SO names (not shortened)
    - Use specific phrasing that maps to concrete actions
    - Use "payment outstanding customer" for specific customer payments
    
    Args:
        user: The user to run as
        so_name: The Sales Order to test with
        channel: The chat channel (for transcript metadata)
        
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
    print("Phase 9 Scenario 2: Workflow Status + MFG Status + Payments")
    print(f"Using SO: {so_name}")
    print("=" * 60)
    
    # 1) Workflow status - returns concrete pipeline data
    response = send_to_agent("workflow_orchestrator", f"workflow status {so_name}")
    transcript.append((f"@ai workflow status {so_name}", response))
    
    # 2) Manufacturing status for SPECIFIC SO
    response = send_to_agent("manufacturing", f"mfg status {so_name}")
    transcript.append((f"@ai mfg status {so_name}", response))
    
    # 3) Show work orders for specific SO
    response = send_to_agent("manufacturing", f"show work orders for {so_name}")
    transcript.append((f"@ai show work orders for {so_name}", response))
    
    # 4) Sales order - full status
    response = send_to_agent("sales_order_follow_up", f"full status {so_name}")
    transcript.append((f"@ai full status {so_name}", response))
    
    # 5) Diagnose SO - find issues blocking the order
    response = send_to_agent("sales_order_follow_up", f"diagnose {so_name}")
    transcript.append((f"@ai diagnose {so_name}", response))
    
    # 6) Next steps for SO
    response = send_to_agent("sales_order_follow_up", f"next steps {so_name}")
    transcript.append((f"@ai next steps {so_name}", response))
    
    # 7) Payment outstanding for specific customer
    response = send_to_agent("payment", "payment outstanding customer LORAND LABORATORIES LLC")
    transcript.append(("@ai payment outstanding customer LORAND LABORATORIES LLC", response))
    
    # 8) Workflow pipeline status
    response = send_to_agent("workflow_orchestrator", f"pipeline status {so_name}")
    transcript.append((f"@ai pipeline status {so_name}", response))
    
    print("\n" + "=" * 60)
    print("Scenario 2 complete!")
    print("=" * 60)
    
    return transcript


def run_quotation_scenario(
    qtn_name: str,
    user: str = SITE_USER,
    channel: str = "Raven Golden Runs"
) -> list:
    """
    Phase 9 Quotation Scenario:
    1) Validate the quotation
    2) Create SO from Quotation via workflow
    3) Inspect workflow / SO / MFG / Payments for the resulting SO

    Usage from bench console:
        from raven_ai_agent.cli.so_lifecycle_scenario import run_quotation_scenario
        run_quotation_scenario("QTN-00752")

    Args:
        qtn_name: The Quotation name to test (e.g., "QTN-00752")
        user: The user to run as
        channel: The chat channel (for transcript metadata)

    Returns:
        List of (message, response) tuples for transcript capture
    """
    from raven_ai_agent.api.router import handle_raven_message

    transcript = []

    def send(msg: str) -> str:
        print(f"\n>> {user}: {msg}")
        try:
            resp = handle_raven_message(
                user=user,
                message=msg,
                channel=channel,
            )
            # Truncate long responses for display
            if resp and len(str(resp)) > 500:
                print(f"<< Raven: {resp[:500]}...")
            else:
                print(f"<< Raven: {resp}")
            return resp
        except Exception as e:
            error_msg = f"ERROR: {e}"
            print(f"<< {error_msg}")
            import traceback
            traceback.print_exc()
            return error_msg

    print("=" * 60)
    print(f"Phase 9 Quotation Scenario for {qtn_name}")
    print("=" * 60)

    # 1) Validate pipeline for quotation
    response = send(f"@workflow validate {qtn_name}")
    transcript.append((f"@workflow validate {qtn_name}", response))

    # 2) Create Sales Order from Quotation
    response = send(f"@workflow create so from {qtn_name}")
    transcript.append((f"@workflow create so from {qtn_name}", response))

    # 3) Show workflow status for resulting SO (assuming same suffix pattern)
    #    For first pass, we just reuse the QTN suffix. Adjust once you see actual SO name.
    so_guess = qtn_name.replace("QTN", "SO")
    response = send(f"@workflow status {so_guess}")
    transcript.append((f"@workflow status {so_guess}", response))

    # 4) Full status
    response = send(f"@ai full status {so_guess}")
    transcript.append((f"@ai full status {so_guess}", response))

    # 5) Manufacturing status
    response = send(f"@ai mfg status {so_guess}")
    transcript.append((f"@ai mfg status {so_guess}", response))

    # 6) Pipeline status
    response = send(f"@ai pipeline status {so_guess}")
    transcript.append((f"@ai pipeline status {so_guess}", response))

    print("=" * 60)
    print("Quotation scenario complete!")
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
