"""Pytest configuration: ensure the vendored ``pipeline/`` directory is on
sys.path so tests can import top-level modules like ``helper_functions`` and
``fds_output_utils`` exactly as they did in the legacy CFDReportGen layout
(without modifying the test files themselves).
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPELINE_DIR = os.path.join(PROJECT_ROOT, "pipeline")

for path in (PROJECT_ROOT, PIPELINE_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)
