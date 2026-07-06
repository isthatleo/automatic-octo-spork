// Specialized Agents Registration File
// Registers all specialized agents with the global registry

// Import the framework
import { specializedAgentRegistry } from "./agent-framework";

// Import all specialized agents
import { researchAgent } from "./research-agent";
import { medicalResearchAgent } from "./medical-research-agent";
import { codingAgent } from "./coding-agent";
import { financialAnalysisAgent } from "./financial-analysis-agent";
import { newsJournalismAgent } from "./news-journalism-agent";
import { legalAgent } from "./legal-agent";
import { dataScienceAgent } from "./data-science-agent";
import { designUXAgent } from "./design-ux-agent";

// Register all agents with the global registry
specializedAgentRegistry.registerAgent(researchAgent);
specializedAgentRegistry.registerAgent(medicalResearchAgent);
specializedAgentRegistry.registerAgent(codingAgent);
specializedAgentRegistry.registerAgent(financialAnalysisAgent);
specializedAgentRegistry.registerAgent(newsJournalismAgent);
specializedAgentRegistry.registerAgent(legalAgent);
specializedAgentRegistry.registerAgent(dataScienceAgent);
specializedAgentRegistry.registerAgent(designUXAgent);

// Export the registry for use in the application
export { specializedAgentRegistry };

// Export individual agents for direct access if needed
export {
  researchAgent,
  medicalResearchAgent,
  codingAgent,
  financialAnalysisAgent,
  newsJournalismAgent,
  legalAgent,
  dataScienceAgent,
  designUXAgent
};

