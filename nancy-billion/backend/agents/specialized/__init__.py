"""
Specialized Agents Package for Nancy Billion
Provides 29+ domain-specific AI agents with real computation and ML capabilities.
"""

from .base_specialized_agent import SpecializedAgent

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
from .neural_interface_agent import NeuralInterfaceAgent
from .holographic_display_controller import HolographicDisplayController
from .environmental_control_nexus import EnvironmentalControlNexus
from .artificial_consciousness_core import ArtificialConsciousnessCore
from .recursive_self_improvement_engine import RecursiveSelfImprovementEngine
from .ethical_governance_core import EthicalGovernanceCore
from .embodied_cognition_interface import EmbodiedCognitionInterface
from .temporal_prediction_engine import TemporalPredictionEngine
from .multi_agent_swarm_coordinator import MultiAgentSwarmCoordinator
from .quantum_reasoning_accelerator import QuantumReasoningAccelerator

from .registry import SPECIALIZED_AGENTS, get_available_agents, create_agent

__all__ = [
    "SpecializedAgent",
    "DataScienceAgent",
    "CryptoTradingAgent",
    "CommunicationAgent",
    "CreativeDesignAgent",
    "DevOpsAgent",
    "QATestAgent",
    "HealthcareAnalyticsAgent",
    "BusinessIntelligenceAgent",
    "MarketResearchAgent",
    "OperationsResearchAgent",
    "LegalComplianceAgent",
    "SystemMonitoringAgent",
    "SecurityAgent",
    "FileManagementAgent",
    "AstrophysicsAgent",
    "QuantumComputingAgent",
    "NanotechnologyAgent",
    "BioinformaticsAgent",
    "ResearchAgent",
    "NeuralInterfaceAgent",
    "HolographicDisplayController",
    "EnvironmentalControlNexus",
    "ArtificialConsciousnessCore",
    "RecursiveSelfImprovementEngine",
    "EthicalGovernanceCore",
    "EmbodiedCognitionInterface",
    "TemporalPredictionEngine",
    "MultiAgentSwarmCoordinator",
    "QuantumReasoningAccelerator",
    "SPECIALIZED_AGENTS",
    "get_available_agents",
    "create_agent",
]
