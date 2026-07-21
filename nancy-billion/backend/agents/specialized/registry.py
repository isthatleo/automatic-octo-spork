"""
Specialized Agents Registry for Nancy Billion
Includes all agents including Phase 1 enhancements and Phase 2 Advanced Agents.
"""
from .data_science_agent import DataScienceAgent
from .crypto_trading_agent import CryptoTradingAgent
from .communication_agent import CommunicationAgent
from .creative_design_agent import CreativeDesignAgent
from .devops_agent import DevOpsAgent
from .qa_test_agent import QATestAgent
from .healthcare_analytics_agent import HealthcareAnalyticsAgent
from .business_intelligence_agent import BusinessIntelligenceAgent
from .market_research_agent import MarketResearchAgent
from .operations_research_agent import OperationsResearchAgent
from .legal_compliance_agent import LegalComplianceAgent
from .system_monitoring_agent import SystemMonitoringAgent
from .security_agent import SecurityAgent
from .file_management_agent import FileManagementAgent
from .astrophysics_agent import AstrophysicsAgent
from .quantum_computing_agent import QuantumComputingAgent
from .nanotechnology_agent import NanotechnologyAgent
from .bioinformatics_agent import BioinformaticsAgent
from .research_agent import ResearchAgent
from .science_research_agent import ScienceResearchAgent
from .general_research_agent import GeneralResearchAgent
from .nuclear_research_agent import NuclearResearchAgent
# Phase 1 Enhancement Agents
from .neural_interface_agent import NeuralInterfaceAgent
from .holographic_display_controller import HolographicDisplayController
from .environmental_control_nexus import EnvironmentalControlNexus
# Phase 2 Advanced Cognitive & Physical Agents
from .artificial_consciousness_core import ArtificialConsciousnessCore
from .recursive_self_improvement_engine import RecursiveSelfImprovementEngine
from .ethical_governance_core import EthicalGovernanceCore
from .embodied_cognition_interface import EmbodiedCognitionInterface
from .temporal_prediction_engine import TemporalPredictionEngine
from .multi_agent_swarm_coordinator import MultiAgentSwarmCoordinator
from .quantum_reasoning_accelerator import QuantumReasoningAccelerator
# Real LLM-backed planning/orchestration agents
from .planning_agent import PlanningAgent
from .dispatcher_agent import DispatcherAgent
# Real analogues of Claude Code's own subagent types
from .explore_agent import ExploreAgent
from .llm_utility_agents import GeneralPurposeAgent, ClaudeAgent, ClaudeCodeGuideAgent
from .statusline_setup_agent import StatuslineSetupAgent
# Meta-agent: creates and deploys new specialized agents (writes to agents/specialized/dynamic/)
from .agent_creator_agent import AgentCreatorAgent

# Registry of all available specialized agents
SPECIALIZED_AGENTS = {
    # ---- Core domain agents ----
    "data_science":           DataScienceAgent,
    "crypto_trading":         CryptoTradingAgent,
    "communication":          CommunicationAgent,
    "creative_design":        CreativeDesignAgent,
    "devops":                 DevOpsAgent,
    "qa_testing":             QATestAgent,
    "healthcare_analytics":   HealthcareAnalyticsAgent,
    "business_intelligence":  BusinessIntelligenceAgent,
    "market_research":        MarketResearchAgent,
    "operations_research":    OperationsResearchAgent,
    "legal_compliance":       LegalComplianceAgent,
    "system_monitoring":      SystemMonitoringAgent,
    "security":               SecurityAgent,
    "file_management":        FileManagementAgent,
    "astrophysics":           AstrophysicsAgent,
    "quantum_computing":      QuantumComputingAgent,
    "nanotechnology":         NanotechnologyAgent,
    "bioinformatics":         BioinformaticsAgent,
    "research":               ResearchAgent,
    "science_research":       ScienceResearchAgent,
    "general_research":       GeneralResearchAgent,
    "nuclear_research":       NuclearResearchAgent,
    # ---- Phase 1 Enhancement Agents ----
    "neural_interface":       NeuralInterfaceAgent,
    "holographic_display":    HolographicDisplayController,
    "environmental_control":  EnvironmentalControlNexus,
    # ---- Phase 2 Advanced Cognitive & Physical Agents ----
    "artificial_consciousness": ArtificialConsciousnessCore,
    "self_improvement":         RecursiveSelfImprovementEngine,
    "ethical_governance":       EthicalGovernanceCore,
    "embodied_cognition":       EmbodiedCognitionInterface,
    "temporal_prediction":      TemporalPredictionEngine,
    "swarm_coordinator":        MultiAgentSwarmCoordinator,
    "quantum_reasoning":        QuantumReasoningAccelerator,
    # ---- Real LLM-backed planning/orchestration agents ----
    "planning":                 PlanningAgent,
    "dispatcher":               DispatcherAgent,
    # ---- Real analogues of Claude Code's own subagent types ----
    "explore":                  ExploreAgent,
    "general_purpose":          GeneralPurposeAgent,
    "claude":                   ClaudeAgent,
    "claude_code_guide":        ClaudeCodeGuideAgent,
    "statusline_setup":         StatuslineSetupAgent,
    # ---- Meta-agent: creates and deploys new specialized agents ----
    "agent_creator":            AgentCreatorAgent,
}

def get_available_agents():
    """Get list of all available agent types"""
    return list(SPECIALIZED_AGENTS.keys())

def create_agent(agent_type, settings):
    """Create an instance of the specified agent type"""
    if agent_type not in SPECIALIZED_AGENTS:
        raise ValueError(f"Unknown agent type: {agent_type}")
    cls = SPECIALIZED_AGENTS[agent_type]
    if cls is None:
        raise ValueError(f"Agent type '{agent_type}' is not available (missing module)")
    return cls(settings)

