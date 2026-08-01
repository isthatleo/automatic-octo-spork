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
from .weather_climate_agent import WeatherClimateAgent
from .economics_agent import EconomicsAgent
from .materials_science_agent import MaterialsScienceAgent
from .personal_finance_agent import PersonalFinanceAgent
from .energy_grid_agent import EnergyGridAgent
from .mathematics_agent import MathematicsAgent
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
# Real ML training lifecycle: MLAgent owns the scikit-learn model artifact,
# ModelTrainingAgent owns the training/dataset/personalization lifecycle.
from .ml_agent import MLAgent
from .model_training_agent import ModelTrainingAgent
# Additional real-computation domain agents.
from .network_diagnostics_agent import NetworkDiagnosticsAgent
from .cryptography_agent import CryptographyAgent
from .geospatial_agent import GeospatialAgent
from .image_processing_agent import ImageProcessingAgent
from .audio_analysis_agent import AudioAnalysisAgent
from .game_theory_agent import GameTheoryAgent
from .sports_analytics_agent import SportsAnalyticsAgent
from .risk_management_agent import RiskManagementAgent
from .accessibility_agent import AccessibilityAgent
from .carbon_footprint_agent import CarbonFootprintAgent
from .database_admin_agent import DatabaseAdminAgent
from .psychometrics_agent import PsychometricsAgent
from .linguistics_agent import LinguisticsAgent
from .timezone_scheduling_agent import TimezoneSchedulingAgent
from .code_complexity_agent import CodeComplexityAgent
# Proactive, self-directed task generation + delegation (distinct from the
# reactive DispatcherAgent above) -- the real engine behind "every agent is
# always doing something" (see main_new.py's proactive-agent scheduling).
from .task_orchestrator_agent import TaskOrchestratorAgent
# Real income-research agents: crypto market intelligence, an honest mining-
# profitability calculator, and e-commerce trend research/drafting (never
# auto-publishing or auto-spending -- see ecommerce_research_agent.py).
from .crypto_intelligence_agent import CryptoIntelligenceAgent
from .mining_profitability_agent import MiningProfitabilityAgent
from .ecommerce_research_agent import EcommerceResearchAgent
# Real TLS inspection, hypothesis testing, and loan amortization -- each a
# distinct real-computation vertical not covered by any existing agent.
from .ssl_certificate_agent import SslCertificateAgent
from .statistical_testing_agent import StatisticalTestingAgent
from .loan_calculator_agent import LoanCalculatorAgent

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
    "weather_climate":        WeatherClimateAgent,
    "economics":              EconomicsAgent,
    "materials_science":      MaterialsScienceAgent,
    "personal_finance":       PersonalFinanceAgent,
    "energy_grid":            EnergyGridAgent,
    "mathematics":            MathematicsAgent,
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
    # ---- Real ML training lifecycle ----
    "machine_learning":         MLAgent,
    "model_training":           ModelTrainingAgent,
    # ---- Additional real-computation domain agents ----
    "network_diagnostics":      NetworkDiagnosticsAgent,
    "cryptography":             CryptographyAgent,
    "geospatial":                GeospatialAgent,
    "image_processing":         ImageProcessingAgent,
    "audio_analysis":           AudioAnalysisAgent,
    "game_theory":              GameTheoryAgent,
    "sports_analytics":         SportsAnalyticsAgent,
    "risk_management":          RiskManagementAgent,
    "accessibility":            AccessibilityAgent,
    "carbon_footprint":         CarbonFootprintAgent,
    "database_admin":           DatabaseAdminAgent,
    "psychometrics":            PsychometricsAgent,
    "linguistics":              LinguisticsAgent,
    "timezone_scheduling":      TimezoneSchedulingAgent,
    "code_complexity":          CodeComplexityAgent,
    # ---- Proactive task generation + delegation ----
    "task_orchestration":       TaskOrchestratorAgent,
    # ---- Real income-research agents ----
    "crypto_intelligence":      CryptoIntelligenceAgent,
    "mining_profitability":     MiningProfitabilityAgent,
    "ecommerce_research":       EcommerceResearchAgent,
    # ---- Additional real-computation domain agents ----
    "ssl_certificate":          SslCertificateAgent,
    "statistical_testing":      StatisticalTestingAgent,
    "loan_calculator":          LoanCalculatorAgent,
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

