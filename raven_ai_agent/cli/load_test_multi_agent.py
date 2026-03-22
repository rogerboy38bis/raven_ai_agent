"""
Phase 9 Load Test Script: Multi-Agent Concurrency Testing

This script tests the agent_bus and context_manager under concurrent load
to ensure they behave correctly when multiple agents are running simultaneously.

Usage:
    from raven_ai_agent.cli.load_test_multi_agent import run_load_test
    run_load_test(num_commands=100, num_users=10)
"""
import frappe
import time
import threading
import random
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import MagicMock

from raven_ai_agent.agents import SalesOrderFollowupAgent, ManufacturingAgent, PaymentAgent, WorkflowOrchestrator


# Test commands that exercise different agents
TEST_COMMANDS = [
    ("sales_order_follow_up", "list recent sales orders"),
    ("sales_order_follow_up", "status SO-00763"),
    ("sales_order_follow_up", "help"),
    ("manufacturing", "show work orders"),
    ("payment", "payment outstanding"),
    ("sales_order_follow_up", "pending orders"),
]


class LoadTestMetrics:
    """Track load test results."""
    
    def __init__(self):
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.response_times: List[float] = []
        self.errors: List[str] = []
        self.lock = threading.Lock()
    
    def record_success(self, response_time: float):
        with self.lock:
            self.total_requests += 1
            self.successful_requests += 1
            self.response_times.append(response_time)
    
    def record_failure(self, error: str):
        with self.lock:
            self.total_requests += 1
            self.failed_requests += 1
            self.errors.append(error)
    
    def get_summary(self) -> Dict:
        with self.lock:
            avg_response_time = (
                sum(self.response_times) / len(self.response_times)
                if self.response_times else 0
            )
            return {
                "total_requests": self.total_requests,
                "successful": self.successful_requests,
                "failed": self.failed_requests,
                "success_rate": self.successful_requests / self.total_requests if self.total_requests > 0 else 0,
                "avg_response_time_ms": avg_response_time * 1000,
                "error_count": len(self.errors),
            }


def send_test_command(user: str, bot_type: str, command: str, metrics: LoadTestMetrics) -> None:
    """Send a single command and record metrics."""
    start_time = time.time()
    
    try:
        if bot_type == "sales_order_follow_up":
            agent = SalesOrderFollowupAgent(user)
        elif bot_type == "manufacturing":
            agent = ManufacturingAgent()
        elif bot_type == "payment":
            agent = PaymentAgent()
        elif bot_type == "workflow_orchestrator":
            agent = WorkflowOrchestrator()
        else:
            raise ValueError(f"Unknown bot type: {bot_type}")
        
        response = agent.process_command(command)
        response_time = time.time() - start_time
        metrics.record_success(response_time)
        
    except Exception as e:
        response_time = time.time() - start_time
        metrics.record_failure(str(e))
        print(f"Error: {e}")


def run_load_test(
    num_commands: int = 50,
    num_users: int = 5
) -> Dict:
    """
    Run load test with concurrent requests.
    
    Args:
        num_commands: Total number of commands to execute
        num_users: Number of concurrent users to simulate
        
    Returns:
        Dictionary with test results and metrics
    """
    print("=" * 60)
    print(f"Starting Load Test: {num_commands} commands, {num_users} users")
    print("=" * 60)
    
    metrics = LoadTestMetrics()
    
    # Prepare tasks
    tasks = []
    for i in range(num_commands):
        user = f"loadtest_user{i % num_users}@example.com"
        bot_type, command = random.choice(TEST_COMMANDS)
        tasks.append((user, bot_type, command))
    
    # Run concurrent requests
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=num_users) as executor:
        futures = []
        for user, bot_type, command in tasks:
            future = executor.submit(
                send_test_command,
                user,
                bot_type,
                command,
                metrics
            )
            futures.append(future)
        
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                metrics.record_failure(str(e))
    
    total_time = time.time() - start_time
    
    summary = metrics.get_summary()
    summary["total_time_seconds"] = total_time
    summary["requests_per_second"] = num_commands / total_time
    
    print("\n" + "=" * 60)
    print("Load Test Results")
    print("=" * 60)
    print(f"Total Requests: {summary['total_requests']}")
    print(f"Successful: {summary['successful']}")
    print(f"Failed: {summary['failed']}")
    print(f"Success Rate: {summary['success_rate']*100:.1f}%")
    print(f"Avg Response Time: {summary['avg_response_time_ms']:.2f}ms")
    print(f"Total Time: {summary['total_time_seconds']:.2f}s")
    print(f"Requests/Second: {summary['requests_per_second']:.1f}")
    print("=" * 60)
    
    return summary


def main():
    """Entry point for CLI execution."""
    print("Starting Phase 9 Load Test...")
    
    result = run_load_test(num_commands=50, num_users=5)
    
    if result["success_rate"] >= 0.8:
        print("\n✓ Load test PASSED")
    else:
        print("\n✗ Load test FAILED - success rate below 80%")


if __name__ == "__main__":
    main()
