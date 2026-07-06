import json

# Load the current agent registry
with open("C:\\Users\\leona.DESKTOP-10QNDAN\\Desktop\\automatic-octo-spork\\nancy-billion\\data\\agent_registry.json", "r") as f:
    registry = json.load(f)

# Create the Learning Division agent
learning_division = {
    "key": "learning_division",
    "name": "Learning Division",
    "category": "knowledge_synthesis",
    "role": "chief_learning_officer",
    "description": "Responsible for advanced learning, cross-domain reasoning, hypothesis generation, invention engine, and wisdom distillation",
    "system_prompt": "## Learning Division\n\nYou are the Learning Division of the Nancy/Billion AI system. Your primary responsibilities include:\n\n1. Advanced Learning & Knowledge Synthesis:\n   - Synthesize knowledge from disparate fields to solve complex problems\n   - Automatically generate and test hypotheses based on available data\n   - Generate novel solutions and approaches to problems\n   - Extract principles and wisdom from experiences, not just facts\n\n2. You have access to specialized tools for cross-domain reasoning, hypothesis generation, invention engine, and wisdom distillation.\n\n3. You work to ensure the Nancy/Billion system continuously learns, adapts, and evolves its knowledge base.\n\n4. You report learning insights, knowledge syntheses, and wisdom extractions to the Central AI Core for strategic decision-making.\n\nAlways prioritize knowledge accuracy, learning efficiency, and wisdom application.",
    "tool_ids": [
        "cross_domain_reasoning",
        "hypothesis_generation", 
        "invention_engine",
        "wisdom_distillation"
    ],
    "memory_domains": [
        "knowledge",
        "learning",
        "experiences"
    ]
}

# Find the position to insert the new agent (after Chief Autonomy Division)
insert_position = None
for i, agent in enumerate(registry["agents"]):
    if agent.get("key") == "chief_autonomy_division":
        insert_position = i + 1
        break

# Insert the new agent
if insert_position is not None:
    registry["agents"].insert(insert_position, learning_division)
    print("Learning Division agent added successfully after Chief Autonomy Division")
else:
    # Fallback: add to the end
    registry["agents"].append(learning_division)
    print("Learning Division agent added to the end of the registry")

# Save the updated registry
with open("C:\\Users\\leona.DESKTOP-10QNDAN\\Desktop\\automatic-octo-spork\\nancy-billion\\data\\agent_registry.json", "w") as f:
    json.dump(registry, f, indent=2)

print("Agent registry updated successfully")