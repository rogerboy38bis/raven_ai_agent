"""
Phase 9 Load Test Script: Multi-Agent Concurrency Testing

This script tests the Raven multi-agent stack under concurrent load
to ensure they behave correctly when multiple agents are running simultaneously.

Usage:
    from raven_ai_agent.cli.load_test_multi_agent import run_load_test
    run_load_test()
    
Or from bench:
    bench --site <site> execute raven_ai_agent.cli.load_test_multi_agent.run_load_test
"""
import random
import threading
import time

import frappe

from raven_ai_agent.agents import SalesOrderFollowupAgent, ManufacturingAgent, PaymentAgent, WorkflowOrchestrator


SITE_USER_TEMPLATE = "loadtest_user_{i}@example.com"
CHANNEL = "Raven Load Test"
NUM_USERS = 10
COMMANDS_PER_USER = 10


def _send_command(user: str, message: str) -> str:
    """Send command to appropriate agent and return response."""
    try:
        if "list recent" in message.lower() or "status" in message.lower() or "full status" in message.lower():
            agent = SalesOrderFollowupAgent(user)
        elif "work order" in message.lower() or "mfg status" in message.lower():
            agent = ManufacturingAgent()
        elif "payment" in message.lower():
            agent = PaymentAgent()
        elif "workflow" in message.lower() or "pipeline" in message.lower():
            agent = WorkflowOrchestrator()
        else:
            agent = SalesOrderFollowupAgent(user)
        
        response = agent.process_command(message)
        text = str(response)
        print(f"[{user}] {message[:50]} -> {text[:80].replace(chr(10), ' ')}")
        return text
    except Exception as e:
        error_msg = f"ERROR: {e}"
        print(f"[{user}] {message[:50]} -> {error_msg}")
        return error_msg


def _user_thread(user_index: int):
    """Run commands for a single simulated user."""
    user = SITE_USER_TEMPLATE.format(i=user_index)
    
    commands = [
        "list recent sales orders",
        "status SO-00763-LORAND LABORATORIES",
        "full status SO-00763-LORAND LABORATORIES",
        "workflow status SO-00763-LORAND LABORATORIES",
        "pipeline status SO-00763-LORAND LABORATORIES",
        "mfg status SO-00763-LORAND LABORATORIES",
        "show work orders for SO-00763-LORAND LABORATORIES",
        "payment outstanding customer LORAND LABORATORIES LLC",
    ]

    turn_count = 0
    last_intent = None
    
    for _ in range(COMMANDS_PER_USER):
        cmd = random.choice(commands)
        _send_command(user, cmd)
        turn_count += 1
        # Track intent from command
        if "status" in cmd.lower():
            last_intent = "so_status"
        elif "payment" in cmd.lower():
            last_intent = "payment_status"
        elif "workflow" in cmd.lower() or "pipeline" in cmd.lower():
            last_intent = "workflow_status"
        elif "mfg" in cmd.lower() or "work order" in cmd.lower():
            last_intent = "mfg_status"
        else:
            last_intent = "list_orders"
        
        time.sleep(random.uniform(0.1, 0.5))

    print(f"[{user}] final state: last_intent={last_intent} turns={turn_count}")


def run_load_test(
    num_users: int = NUM_USERS,
    commands_per_user: int = COMMANDS_PER_USER,
):
    """
    Light concurrent load test for Raven multi-agent stack.

    Args:
        num_users: Number of concurrent users to simulate
        commands_per_user: Number of commands each user executes
        
    Run from bench:
        bench --site <site> execute raven_ai_agent.cli.load_test_multi_agent.run_load_test
    """
    print(
        f"=== Phase 9 Load Test: {num_users} users x {commands_per_user} commands "
        f"(channel={CHANNEL}) ==="
    )

    threads = []
    for i in range(num_users):
        t = threading.Thread(target=_user_thread, args=(i,))
        t.daemon = True
        threads.append(t)

    for t in threads:
        t.start()

    for t in threads:
        t.join()

    print("=== Load test complete ===")


def main():
    """Entry point for CLI execution."""
    run_load_test()


if __name__ == "__main__":
    main()
