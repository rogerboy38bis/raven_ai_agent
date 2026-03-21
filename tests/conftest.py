"""
Pytest configuration for raven_ai_agent unit tests.

This conftest.py fixes the import path collision issue where pytest picks up
the outer __init__.py (apps/raven_ai_agent/__init__.py) instead of the inner
package (apps/raven_ai_agent/raven_ai_agent/).

CRITICAL: This MUST be loaded before any test decorators are evaluated.
"""
import sys
import os
from pathlib import Path


def pytest_configure(config):
    """
    Fix sys.path BEFORE any test imports happen.
    
    This runs before @patch decorators are evaluated, ensuring the correct
    raven_ai_agent package is used.
    """
    # Find the actual project root (where raven_ai_agent package is)
    current_file = Path(__file__).resolve()
    tests_dir = current_file.parent
    
    # The project structure is:
    # raven_ai_agent/
    #   tests/
    #     conftest.py
    #   raven_ai_agent/
    #     agents/
    #       *.py
    
    project_root = tests_dir.parent
    
    # Remove any incorrect paths that might cause import collisions
    paths_to_remove = []
    for p in sys.path:
        if 'apps/raven_ai_agent' in p and p != str(project_root):
            paths_to_remove.append(p)
    
    for p in paths_to_remove:
        sys.path.remove(p)
    
    # Ensure the inner package path is first
    inner_package = str(project_root / 'raven_ai_agent')
    if inner_package not in sys.path:
        sys.path.insert(0, inner_package)
    
    # Ensure project root is also in path for imports like 'from raven_ai_agent.agents...'
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))


def pytest_collection_modifyitems(config, items):
    """
    Ensure conftest is loaded before any test runs.
    This is a safety measure.
    """
    pass
