"""
Raven AI Agent CLI Package

Contains scenario scripts and utilities for testing and validation.

Modules:
    - so_lifecycle_scenario: Phase 9 scenario script for SO lifecycle testing
    - load_test_multi_agent: Load testing for concurrent agents
    - capture_golden_transcripts: Capture golden transcripts for regression testing
"""
from raven_ai_agent.cli.so_lifecycle_scenario import run_so_lifecycle_scenario, run_scenario_2, main as run_scenario
from raven_ai_agent.cli.load_test_multi_agent import run_load_test, main as run_load
from raven_ai_agent.cli.capture_golden_transcripts import (
    capture_transcript,
    save_transcript,
    load_transcript,
    run_and_capture,
    main as capture_golden
)

__all__ = [
    "run_so_lifecycle_scenario",
    "run_scenario_2",
    "run_scenario",
    "run_load_test",
    "run_load",
    "capture_transcript",
    "save_transcript",
    "load_transcript",
    "run_and_capture",
    "capture_golden",
]
