// Example Usage of Specialized Agents
// Demonstrates how to integrate and use the specialized agent system

import { specializedAgentRegistry } from "./agents/specialized";

// Example: Using the Research Agent
async function researchExample() {
  // Create a research task
  const researchTask = {
    id: `res-task-${Date.now()}`,
    type: "literature-review",
    priority: "high",
    payload: {
      topic: "Artificial Intelligence in Healthcare",
      depth: "comprehensive",
      timeframe: "last 5 years"
    },
    timestamp: Date.now(),
    callback: (result) => {
      console.log("Research completed:", result);
      // Handle results - display to user, store, etc.
    }
  };
  
  // Send task to research agent
  const result = await specializedAgentRegistry.sendTaskToAgent(
    "Research Agent", 
    researchTask
  );
  
  return result;
}

// Example: Using the Coding Agent
async function codingExample() {
  // Create a coding task
  const codingTask = {
    id: `code-task-${Date.now()}`,
    type: "code-generation",
    priority: "medium",
    payload: {
      language: "javascript",
      framework: "react",
      componentType: "data-display",
      componentName: "StockChart",
      description: "A real-time stock chart component with live updates"
    },
    timestamp: Date.now(),
    callback: (result) => {
      console.log("Code generated:", result);
      // Handle generated code - display, save, etc.
    }
  };
  
  // Send task to coding agent
  const result = await specializedAgentRegistry.sendTaskToAgent(
    "Coding Agent",
    codingTask
  );
  
  return result;
}

// Example: Using the Financial Analysis Agent
async function financeExample() {
  // Create a financial analysis task
  const financeTask = {
    id: `finance-task-${Date.now()}`,
    type: "portfolio-analysis",
    priority: "high",
    payload: {
      portfolio: ["AAPL", "GOOGL", "MSFT", "TSLA"],
      timeframe: "6-months",
      riskTolerance: "moderate"
    },
    timestamp: Date.now(),
    callback: (result) => {
      console.log("Financial analysis completed:", result);
      // Handle results
    }
  };
  
  // Send task to financial analysis agent
  const result = await specializedAgentRegistry.sendTaskToAgent(
    "Financial Analysis Agent",
    financeTask
  );
  
  return result;
}

console.log("Specialized agents example functions created");

