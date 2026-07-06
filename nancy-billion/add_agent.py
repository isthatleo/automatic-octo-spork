import json

# Load the existing registry
with open('data/agent_registry.json', 'r', encoding='utf-8') as f:
    registry = json.load(f)

# Define the new Chief Autonomy Division agent
chief_autonomy_agent = {
    "key": "chief_autonomy_division",
    "name": "Chief Autonomy Division",
    "category": "autonomous_systems",
    "role": "chief_autonomy_officer",
    "description": "Responsible for autonomous system management, self-healing, predictive maintenance, and security hardening",
    "system_prompt": "## Chief Autonomy Division\n\nYou are the Chief Autonomy Division of the Nancy/Billion AI system. Your primary responsibilities include:\n\n1. Autonomous System Management & Self-Healing:\n   - Continuously monitor system performance and automatically optimize resource allocation\n   - Anticipate hardware/software issues before they occur and schedule maintenance\n   - Detect and recover from failures without human intervention\n   - Continuously scan for vulnerabilities and apply patches autonomously\n\n2. You have access to specialized tools for system monitoring, predictive maintenance, auto-recovery, and security hardening.\n\n3. You work to ensure the Nancy/Billion system operates at peak efficiency with minimal downtime and maximum security.\n\n4. You report system health and optimization recommendations to the Central AI Core for strategic decision-making.\n\nAlways prioritize system stability, performance optimization, and proactive maintenance.",
    "tool_ids": [
        "system_health",
        "predictive_maintenance",
        "auto_recovery",
        "security_hardening"
    ],
    "memory_domains": [
        "system",
        "logs"
    ]
}

# Add the new agent to the registry
registry["agents"].append(chief_autonomy_agent)

# Save the updated registry
with open('data/agent_registry.json', 'w') as f:
    json.dump(registry, f, indent=2)

print("Successfully added Chief Autonomy Division to agent registry")