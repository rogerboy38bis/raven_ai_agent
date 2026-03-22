"""
Multi-Agent Router for Sequential Agent Pipelines.

Handles complex commands that require coordinating multiple agents
in sequence, aggregating their responses into a single reply.
"""

import re
import logging
from typing import Optional, List, Dict, Any, Callable

# Import with try/except for frappe dependency (Import guard as per requirements)
try:
    from raven_ai_agent.utils.context_manager import ContextStore, get_context_store
    from raven_ai_agent.utils.agent_bus import (
        AgentBus, AgentEvent, get_bus,
        EVENT_AGENT_START, EVENT_AGENT_COMPLETE, EVENT_AGENT_ERROR
    )
    CONTEXT_MANAGER_AVAILABLE = True
except ImportError:
    CONTEXT_MANAGER_AVAILABLE = False

logger = logging.getLogger(__name__)


# Multi-agent command patterns
MULTI_AGENT_PATTERNS = [
    # "workflow run SO-XXXX" - triggers sales + manufacturing + payment check
    (r'^workflow\s+run\s+SO-', 'workflow_run'),
    (r'^execute\s+workflow\s+SO-', 'workflow_run'),
    
    # "full status SO-XXXX" - sales + delivery + payment combined
    (r'^full\s+status\s+SO-', 'full_status'),
    (r'^complete\s+status\s+SO-', 'full_status'),
    (r'^detailed\s+status\s+SO-', 'full_status'),
    
    # "diagnose and fix SO-XXXX" - diagnose + suggest workflow actions
    (r'^diagnose\s+and\s+fix\s+SO-', 'diagnose_and_fix'),
    (r'^diagnose\s+&\s*fix\s+SO-', 'diagnose_and_fix'),
    
    # "morning briefing" - sales summary + pending WOs + overdue payments
    (r'^morning\s+briefing$', 'morning_briefing'),
    (r'^daily\s+briefing$', 'morning_briefing'),
    (r'^briefing$', 'morning_briefing'),
]


def is_multi_agent_command(command: str) -> bool:
    """
    Check if a command requires multiple agents.
    
    Args:
        command: The user command to check
        
    Returns:
        True if command requires multi-agent handling
    """
    command_lower = command.lower().strip()
    
    for pattern, _ in MULTI_AGENT_PATTERNS:
        if re.search(pattern, command_lower, re.IGNORECASE):
            return True
    
    return False


def _extract_so_from_command(command: str) -> Optional[str]:
    """
    Extract Sales Order name from command.
    
    Args:
        command: The command string
        
    Returns:
        The SO name if found, None otherwise
    """
    match = re.search(r'SO-[\w\-\.\s]+', command, re.IGNORECASE)
    if match:
        return match.group(0).strip()
    return None


def build_agent_pipeline(command: str) -> List[Dict[str, str]]:
    """
    Build an ordered list of agent steps for a multi-agent command.
    
    Args:
        command: The multi-agent command
        
    Returns:
        List of step dicts with 'agent' and 'sub_command' keys
    """
    command_lower = command.lower().strip()
    so_name = _extract_so_from_command(command)
    
    # Determine pipeline type
    pipeline_type = None
    for pattern, ptype in MULTI_AGENT_PATTERNS:
        if re.search(pattern, command_lower, re.IGNORECASE):
            pipeline_type = ptype
            break
    
    if pipeline_type is None:
        return []
    
    # Build pipeline based on type
    if pipeline_type == 'workflow_run':
        return [
            {"agent": "sales_order_followup", "sub_command": f"status {so_name}"},
            {"agent": "manufacturing", "sub_command": f"list open WO for SO {so_name}"},
            {"agent": "payment", "sub_command": f"check payment {so_name}"},
        ]
    
    elif pipeline_type == 'full_status':
        return [
            {"agent": "sales_order_followup", "sub_command": f"status {so_name}"},
            {"agent": "sales_order_followup", "sub_command": f"delivery status {so_name}"},
            {"agent": "payment", "sub_command": f"payment status {so_name}"},
        ]
    
    elif pipeline_type == 'diagnose_and_fix':
        return [
            {"agent": "sales_order_followup", "sub_command": f"diagnose {so_name}"},
            {"agent": "data_quality_scanner", "sub_command": f"validate {so_name}"},
            {"agent": "workflow_orchestrator", "sub_command": f"suggest actions for {so_name}"},
        ]
    
    elif pipeline_type == 'morning_briefing':
        return [
            {"agent": "sales_order_followup", "sub_command": "list sales orders summary"},
            {"agent": "manufacturing", "sub_command": "list pending work orders"},
            {"agent": "payment", "sub_command": "list overdue payments"},
        ]
    
    return []


def _execute_single_step(
    step: Dict[str, str],
    context: Dict[str, Any],
    event_bus: Optional[Any] = None,
    correlation_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Execute a single pipeline step.
    
    Args:
        step: Dict with 'agent' and 'sub_command'
        context: Context from previous steps
        event_bus: Optional event bus for publishing events
        correlation_id: Correlation ID for tracing
        
    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    agent_name = step.get('agent', '')
    sub_command = step.get('sub_command', '')
    
    # Publish start event
    if event_bus and CONTEXT_MANAGER_AVAILABLE:
        try:
            event_bus.publish_and_dispatch(AgentEvent(
                event_type=EVENT_AGENT_START,
                source_agent=agent_name,
                payload={'command': sub_command, 'context': context},
                correlation_id=correlation_id,
            ))
        except Exception:
            pass
    
    # Import agent dynamically to avoid frappe dependency at module level
    result = None
    error = None
    
    try:
        # Import the router to use existing routing logic
        from raven_ai_agent.api.router import handle_raven_message
        
        # Build the full message for routing
        full_message = sub_command
        
        # Execute via router - this calls the actual agent
        # Note: In real execution, this would need a user context
        response = handle_raven_message(full_message, "System")
        result = response
        
    except Exception as e:
        error = str(e)
        logger.error(f"Error executing step {agent_name}: {e}")
        
        # Publish error event
        if event_bus and CONTEXT_MANAGER_AVAILABLE:
            try:
                event_bus.publish_and_dispatch(AgentEvent(
                    event_type=EVENT_AGENT_ERROR,
                    source_agent=agent_name,
                    payload={'command': sub_command, 'error': error},
                    correlation_id=correlation_id,
                ))
            except Exception:
                pass
    
    # Publish complete event
    if event_bus and CONTEXT_MANAGER_AVAILABLE:
        try:
            event_bus.publish_and_dispatch(AgentEvent(
                event_type=EVENT_AGENT_COMPLETE,
                source_agent=agent_name,
                payload={'command': sub_command, 'result': result, 'success': result is not None},
                correlation_id=correlation_id,
            ))
        except Exception:
            pass
    
    return {
        'success': result is not None,
        'result': result,
        'error': error,
        'agent': agent_name,
    }


def execute_pipeline(
    pipeline: List[Dict[str, str]],
    user: str,
    context: Optional[Any] = None
) -> str:
    """
    Execute a pipeline of agent steps in order.
    
    Args:
        pipeline: List of step dicts from build_agent_pipeline
        user: The user executing the pipeline
        context: Session context from ContextStore
        
    Returns:
        Aggregated response from all steps
    """
    if not pipeline:
        return "No pipeline steps to execute."
    
    # Get event bus
    event_bus = None
    correlation_id = None
    
    if CONTEXT_MANAGER_AVAILABLE:
        try:
            event_bus = get_bus()
            # Generate correlation ID for this pipeline
            import uuid
            correlation_id = str(uuid.uuid4())
        except Exception:
            pass
    
    # Initialize accumulated context
    accumulated_context = {
        'user': user,
        'previous_results': [],
    }
    
    results = []
    
    for i, step in enumerate(pipeline):
        logger.info(f"Executing pipeline step {i+1}/{len(pipeline)}: {step}")
        
        # Execute step
        step_result = _execute_single_step(
            step=step,
            context=accumulated_context,
            event_bus=event_bus,
            correlation_id=correlation_id,
        )
        
        results.append(step_result)
        
        # Add to accumulated context (non-fatal - continue on error)
        if step_result.get('result'):
            accumulated_context['previous_results'].append({
                'agent': step_result['agent'],
                'result': step_result['result'],
            })
    
    # Update context store if available
    if CONTEXT_MANAGER_AVAILABLE and context:
        try:
            store = get_context_store()
            ctx = store.get_or_create(user)
            ctx.update(
                intent='pipeline',
                agent='multi_agent_router',
                command='multi_agent_pipeline',
            )
        except Exception:
            pass
    
    # Format aggregated response
    return _format_pipeline_response(results, pipeline)


def _format_pipeline_response(
    results: List[Dict[str, Any]],
    pipeline: List[Dict[str, str]]
) -> str:
    """
    Format pipeline results into a single response.
    
    Args:
        results: List of step results
        pipeline: Original pipeline steps
        
    Returns:
        Formatted response string
    """
    if not results:
        return "No results to display."
    
    lines = ["📋 **Pipeline Execution Results**\n"]
    
    for i, (step, result) in enumerate(zip(pipeline, results), 1):
        agent = step.get('agent', 'unknown')
        command = step.get('sub_command', '')
        
        lines.append(f"### Step {i}: {agent}")
        lines.append(f"Command: `{command}`")
        
        if result.get('success'):
            lines.append("Status: ✅ Success")
            result_text = result.get('result', '')
            if result_text:
                lines.append(f"Result: {result_text}")
        else:
            lines.append("Status: ❌ Failed")
            error = result.get('error')
            if error:
                lines.append(f"Error: {error}")
        
        lines.append("")  # Empty line between steps
    
    # Summary
    successful = sum(1 for r in results if r.get('success'))
    total = len(results)
    lines.append(f"**Summary:** {successful}/{total} steps completed successfully.")
    
    return "\n".join(lines)


def handle_multi_agent_command(command: str, user: str) -> Optional[str]:
    """
    Entry point for handling multi-agent commands.
    
    Args:
        command: The user command
        user: The user identifier
        
    Returns:
        Result string if handled, None if not a multi-agent command
    """
    # Check if this is a multi-agent command
    if not is_multi_agent_command(command):
        return None
    
    # Build the pipeline
    pipeline = build_agent_pipeline(command)
    
    if not pipeline:
        logger.warning(f"Could not build pipeline for command: {command}")
        return None
    
    # Get context if available
    context = None
    if CONTEXT_MANAGER_AVAILABLE:
        try:
            store = get_context_store()
            context = store.get_or_create(user)
        except Exception:
            pass
    
    # Execute pipeline
    result = execute_pipeline(pipeline, user, context)
    
    return result
