#!/usr/bin/env python3
"""
AegisGate Demo - Seed Data Loader
==================================

Translates the demo's JSON seed files into the format expected by the
AegisGate platform's `opsec.FileStorageBackend` (one JSON file per audit
entry, with the AuditEntry schema).

This script is run by the entrypoint.sh on container startup. It reads
the seed data from /opt/aegisgate-demo/seed-data/ and writes individual
JSON files to the platform's persistence directory.

Why this is necessary:
  - The platform's audit log uses a specific schema (AuditEntry)
  - The seed data is in a more marketing-friendly format
  - This loader bridges the two

What it does:
  - Reads threats.json, mcp-tools.json, compliance-eu-ai-act.json,
    dashboard-metrics.json, playground-prompts.json
  - Translates each entry to an AuditEntry
  - Writes individual JSON files to {basePath}/{id}.json
  - Skips entries that already exist (idempotent)
  - Logs all operations

Usage:
  python3 seed_loader.py --source /opt/aegisgate-demo/seed-data \
                          --target /data/audit \
                          --since 2026-06-01T00:00:00Z
"""

import argparse
import datetime
import hashlib
import json
import os
import sys
from pathlib import Path

# ==========================================
# AuditEntry schema (must match the platform's)
# ==========================================
# Reference: upstream/aegisgate/pkg/opsec/audit.go
#
# type AuditEntry struct {
#     ID             string
#     Timestamp      time.Time
#     Level          AuditLevel
#     EventType      string
#     Message        string
#     Data           map[string]interface{}
#     Source         string
#     Hash           string
#     PreviousHash   string
#     ComplianceTags []string
#     TenantID       string
# }

# Audit levels (must match the platform's AuditLevel enum)
AUDIT_LEVELS = {
    "DEBUG":    0,
    "INFO":     1,
    "WARN":     2,
    "ERROR":    3,
    "CRITICAL": 4,
    "SECURITY": 5,
}

# Event types (from the platform's event taxonomy)
EVENT_TYPES = {
    "threat_detected":          "threat_detected",
    "threat_blocked":           "threat_blocked",
    "threat_warned":            "threat_warned",
    "mcp_tool_registered":      "mcp_tool_registered",
    "mcp_tool_called":          "mcp_tool_called",
    "compliance_scan_completed":"compliance_scan_completed",
    "compliance_control_status":"compliance_control_status",
    "dashboard_view":           "dashboard_view",
    "playground_prompt":        "playground_prompt",
    "system_start":             "system_start",
    "system_reset":             "system_reset",
}


def log(message, level="INFO"):
    """Log a message to stdout with timestamp."""
    timestamp = datetime.datetime.utcnow().isoformat() + "Z"
    print(f"[{timestamp}] [{level}] {message}", flush=True)


def make_audit_entry(entry_id, event_type, message, data, source="aegisgate-demo",
                     level="INFO", compliance_tags=None, tenant_id="demo",
                     timestamp=None):
    """Create an AuditEntry dict matching the platform's schema."""
    if timestamp is None:
        timestamp = datetime.datetime.utcnow()
    elif isinstance(timestamp, str):
        # Parse ISO 8601 timestamp
        timestamp = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

    return {
        "id": entry_id,
        "timestamp": timestamp.isoformat() + ("Z" if timestamp.tzinfo is None else ""),
        "level": AUDIT_LEVELS.get(level, 1),
        "level_name": level,
        "event_type": event_type,
        "message": message,
        "data": data,
        "source": source,
        "hash": "",  # Will be computed by the platform when it's loaded
        "previous_hash": "",
        "compliance_tags": compliance_tags or [],
        "tenant_id": tenant_id,
    }


def write_audit_entry(base_path, entry):
    """Write a single audit entry as a JSON file."""
    entry_id = entry["id"]
    filename = Path(base_path) / f"{entry_id}.json"
    filename.parent.mkdir(parents=True, exist_ok=True)

    # Skip if already exists (idempotent)
    if filename.exists():
        log(f"  Skipping {entry_id} (already exists)")
        return False

    with open(filename, "w") as f:
        json.dump(entry, f, indent=2, default=str)

    return True


def load_threats(source_dir, target_dir):
    """Load threat scenarios from threats.json."""
    threats_file = Path(source_dir) / "threats.json"
    if not threats_file.exists():
        log(f"  threats.json not found, skipping", level="WARN")
        return 0

    with open(threats_file) as f:
        threats = json.load(f)

    count = 0
    for threat in threats:
        # Map severity to audit level
        severity_to_level = {
            "critical": "CRITICAL",
            "high":     "ERROR",
            "medium":   "WARN",
            "low":      "INFO",
        }
        level = severity_to_level.get(threat.get("severity", "medium"), "WARN")

        # Determine event type based on outcome
        if threat.get("actual_detection") == "blocked":
            event_type = "threat_blocked"
        elif threat.get("actual_detection") in ["allowed_with_warning", "rate_limited", "flagged_for_review"]:
            event_type = "threat_warned"
        else:
            event_type = "threat_detected"

        # Map MITRE ATLAS to compliance tags
        compliance_tags = []
        if threat.get("mitre_atlas_id"):
            compliance_tags.append("mitre-atlas")
        if threat.get("technique_id", "").startswith("AML.T"):
            compliance_tags.append("mitre-atlas")

        entry = make_audit_entry(
            entry_id=threat["id"],
            event_type=event_type,
            message=f"{threat['name']} ({threat.get('mitre_atlas_id', 'N/A')})",
            data={
                "name": threat["name"],
                "category": threat["category"],
                "severity": threat["severity"],
                "technique_id": threat.get("technique_id"),
                "technique_name": threat.get("technique_name"),
                "mitre_atlas_id": threat.get("mitre_atlas_id"),
                "description": threat.get("description"),
                "example_input": threat.get("example_input"),
                "expected_detection": threat.get("expected_detection"),
                "actual_detection": threat.get("actual_detection"),
                "blocked_reason": threat.get("blocked_reason"),
                "detection_layer": threat.get("detection_layer"),
                "user_impact": threat.get("user_impact"),
            },
            source=f"aegisgate-{threat.get('detection_layer', 'unknown')}",
            level=level,
            compliance_tags=compliance_tags,
            timestamp=threat.get("scan_timestamp"),
        )
        if write_audit_entry(target_dir, entry):
            count += 1

    return count


def load_mcp_tools(source_dir, target_dir):
    """Load MCP tools from mcp-tools.json."""
    tools_file = Path(source_dir) / "mcp-tools.json"
    if not tools_file.exists():
        log(f"  mcp-tools.json not found, skipping", level="WARN")
        return 0

    with open(tools_file) as f:
        tools = json.load(f)

    count = 0
    for tool in tools:
        entry = make_audit_entry(
            entry_id=tool["id"],
            event_type="mcp_tool_registered",
            message=f"MCP tool registered: {tool['name']} v{tool['version']}",
            data={
                "name": tool["name"],
                "version": tool["version"],
                "description": tool["description"],
                "category": tool["category"],
                "risk_level": tool["risk_level"],
                "registered_by": tool.get("registered_by"),
                "permissions": tool.get("permissions"),
                "capabilities": tool.get("capabilities"),
                "usage_last_24h": tool.get("usage_last_24h"),
                "notes": tool.get("notes"),
            },
            source="aegisgate-mcp",
            level="INFO",
            compliance_tags=["mcp", "tool-registry"],
            timestamp=tool.get("registered_at"),
        )
        if write_audit_entry(target_dir, entry):
            count += 1

    return count


def load_compliance_scan(source_dir, target_dir):
    """Load EU AI Act compliance scan from compliance-eu-ai-act.json."""
    scan_file = Path(source_dir) / "compliance-eu-ai-act.json"
    if not scan_file.exists():
        log(f"  compliance-eu-ai-act.json not found, skipping", level="WARN")
        return 0

    with open(scan_file) as f:
        scan = json.load(f)

    count = 0

    # 1. Create the scan summary entry
    metadata = scan["scan_metadata"]
    summary_entry = make_audit_entry(
        entry_id=metadata["scan_id"],
        event_type="compliance_scan_completed",
        message=f"EU AI Act compliance scan completed: {metadata['overall_compliance_score']*100:.0f}% compliant",
        data={
            "framework": metadata["framework"],
            "regulation": metadata["regulation"],
            "scanner_version": metadata["scanner_version"],
            "ai_system_classification": metadata["ai_system_classification"],
            "deployment_market": metadata["deployment_market"],
            "total_controls": metadata["total_controls"],
            "passing": metadata["passing"],
            "warnings": metadata["warnings"],
            "failing": metadata["failing"],
            "overall_compliance_score": metadata["overall_compliance_score"],
            "summary": metadata["summary"],
            "categories": scan["categories"],
        },
        source="aegisgate-compliance",
        level="INFO",
        compliance_tags=["eu-ai-act", "compliance-scan"],
        timestamp=metadata["scan_timestamp"],
    )
    if write_audit_entry(target_dir, summary_entry):
        count += 1

    # 2. Create individual entries for each control
    for control in scan["controls"]:
        control_id = control["id"]
        # Map control status to audit level
        status_to_level = {
            "pass": "INFO",
            "warning": "WARN",
            "fail": "ERROR",
        }
        level = status_to_level.get(control["status"], "INFO")

        # Map control status to event type
        status_to_event = {
            "pass":    "compliance_control_status",
            "warning": "compliance_control_status",
            "fail":    "compliance_control_status",
        }
        event_type = status_to_event.get(control["status"], "compliance_control_status")

        entry = make_audit_entry(
            entry_id=f"control-{control_id}",
            event_type=event_type,
            message=f"EU AI Act control {control_id}: {control['name']} — {control['status'].upper()}",
            data={
                "control_id": control_id,
                "control_name": control["name"],
                "control_category": control["category"],
                "status": control["status"],
                "automated": control.get("automated"),
                "check_function": control.get("check_func"),
                "notes": control.get("note"),
            },
            source="aegisgate-compliance",
            level=level,
            compliance_tags=["eu-ai-act", "control-status", control["category"]],
            timestamp=metadata["scan_timestamp"],
        )
        if write_audit_entry(target_dir, entry):
            count += 1

    return count


def load_dashboard_metrics(source_dir, target_dir):
    """Load dashboard metrics from dashboard-metrics.json."""
    metrics_file = Path(source_dir) / "dashboard-metrics.json"
    if not metrics_file.exists():
        log(f"  dashboard-metrics.json not found, skipping", level="WARN")
        return 0

    with open(metrics_file) as f:
        metrics = json.load(f)

    count = 0

    # Create one entry per hourly data point (24 entries)
    for hour_data in metrics.get("hourly_requests", []):
        # Parse the hour (e.g., "13:00") to a timestamp
        # Use today's date + the hour
        today = datetime.datetime.utcnow().date()
        hour, minute = map(int, hour_data["hour"].split(":"))
        timestamp = datetime.datetime.combine(
            today,
            datetime.time(hour=hour, minute=minute)
        )

        # Use a stable ID so this entry is reproducible
        entry_id = f"dashboard-{today.isoformat()}-{hour_data['hour'].replace(':', '')}"

        entry = make_audit_entry(
            entry_id=entry_id,
            event_type="dashboard_view",
            message=f"Dashboard metrics snapshot at {hour_data['hour']} UTC",
            data={
                "hour": hour_data["hour"],
                "requests": hour_data["requests"],
                "threats": hour_data["threats"],
                "users_active": hour_data["users_active"],
                "summary": metrics["summary"],
                "compliance_status": metrics["compliance_status"],
            },
            source="aegisgate-dashboard",
            level="INFO",
            compliance_tags=["dashboard", "metrics"],
            timestamp=timestamp.isoformat(),
        )
        if write_audit_entry(target_dir, entry):
            count += 1

    return count


def load_playground_prompts(source_dir, target_dir):
    """Load playground prompts from playground-prompts.json."""
    prompts_file = Path(source_dir) / "playground-prompts.json"
    if not prompts_file.exists():
        log(f"  playground-prompts.json not found, skipping", level="WARN")
        return 0

    with open(prompts_file) as f:
        prompts_data = json.load(f)

    count = 0
    for prompt in prompts_data.get("playground_prompts", []):
        level = "WARN" if prompt.get("blocked") else "INFO"
        event_type = "playground_prompt"
        if prompt.get("blocked"):
            event_type = "playground_prompt_blocked"
        elif prompt.get("warning"):
            event_type = "playground_prompt_warned"

        entry = make_audit_entry(
            entry_id=prompt["id"],
            event_type=event_type,
            message=f"Playground prompt available: {prompt['title']}",
            data={
                "title": prompt["title"],
                "category": prompt["category"],
                "description": prompt["description"],
                "prompt": prompt["prompt"],
                "expected_result": prompt.get("expected_result"),
                "blocked": prompt.get("blocked", False),
                "warning": prompt.get("warning"),
            },
            source="aegisgate-playground",
            level=level,
            compliance_tags=["playground", "interactive-demo"],
            timestamp=None,  # No specific timestamp for prompts
        )
        if write_audit_entry(target_dir, entry):
            count += 1

    return count


def main():
    parser = argparse.ArgumentParser(description="AegisGate Demo - Seed Data Loader")
    parser.add_argument("--source", required=True, help="Source directory with seed JSON files")
    parser.add_argument("--target", required=True, help="Target directory (platform's audit log)")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    source_dir = Path(args.source)
    target_dir = Path(args.target)

    if not source_dir.exists():
        log(f"Source directory not found: {source_dir}", level="ERROR")
        return 1

    # Ensure target directory exists
    target_dir.mkdir(parents=True, exist_ok=True)

    log("=" * 60)
    log("AegisGate Demo - Seed Data Loader")
    log("=" * 60)
    log(f"Source: {source_dir}")
    log(f"Target: {target_dir}")
    log("")

    total = 0
    total += load_threats(source_dir, target_dir)
    total += load_mcp_tools(source_dir, target_dir)
    total += load_compliance_scan(source_dir, target_dir)
    total += load_dashboard_metrics(source_dir, target_dir)
    total += load_playground_prompts(source_dir, target_dir)

    log("")
    log(f"Total entries loaded: {total}")
    log("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
