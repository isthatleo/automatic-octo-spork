// Specialized Agent Framework for Nancy Billion
// Base classes and registry for domain-specific AI agents

export interface AgentCapabilities {
  name: string;
  domain: string;
  description: string;
  version: string;
  confidence: number; // 0-1
  specializations: string[];
  tools: string[];
  isActive: boolean;
}

export interface AgentTask {
  id: string;
  type: string;
  priority: "low" | "medium" | "high" | "urgent";
  payload: any;
  timestamp: number;
  deadline?: number;
  callback?: (result: any) => void;
}

export interface AgentResult {
  taskId: string;
  success: boolean;
  data: any;
  confidence: number;
  executionTime: number;
  metadata?: Record<string, any>;
}

export abstract class SpecializedAgent {
  protected capabilities: AgentCapabilities;
  protected taskQueue: AgentTask[] = [];
  protected isProcessing = false;
  
  constructor(capabilities: AgentCapabilities) {
    this.capabilities = capabilities;
  }
  
  abstract processTask(task: AgentTask): Promise<AgentResult>;
  
  addTask(task: AgentTask) {
    this.taskQueue.push(task);
    this.taskQueue.sort((a, b) => 
      (b.priority === "urgent" ? 4 : b.priority === "high" ? 3 : b.priority === "medium" ? 2 : 1) -
      (a.priority === "urgent" ? 4 : a.priority === "high" ? 3 : a.priority === "medium" ? 2 : 1)
    );
    
    if (!this.isProcessing) {
      this.processQueue();
    }
  }
  
  private async processQueue() {
    if (this.isProcessing || this.taskQueue.length === 0) return;
    
    this.isProcessing = true;
    
    while (this.taskQueue.length > 0) {
      const task = this.taskQueue.shift();
      if (!task) continue;
      
      try {
        const startTime = Date.now();
        const result = await this.processTask(task);
        result.executionTime = Date.now() - startTime;
        
        if (task.callback) {
          task.callback(result);
        }
      } catch (error) {
        console.error(`[${this.capabilities.name}] Error processing task:`, error);
        
        if (task.callback) {
          task.callback({
            taskId: task.id,
            success: false,
            data: null,
            confidence: 0,
            executionTime: 0,
            metadata: { error: error.message }
          });
        }
      }
    }
    
    this.isProcessing = false;
  }
  
  getStatus() {
    return {
      ...this.capabilities,
      queueLength: this.taskQueue.length,
      isProcessing: this.isProcessing
    };
  }
}

// Agent Registry
export class SpecializedAgentRegistry {
  private agents: Map<string, SpecializedAgent> = new Map();
  
  registerAgent(agent: SpecializedAgent) {
    this.agents.set(agent.capabilities.name.toLowerCase(), agent);
    console.log(`[SpecializedAgentRegistry] Registered agent: ${agent.capabilities.name}`);
  }
  
  getAgent(name: string): SpecializedAgent | null {
    return this.agents.get(name.toLowerCase()) || null;
  }
  
  getAllAgents(): SpecializedAgent[] {
    return Array.from(this.agents.values());
  }
  
  getAgentsByDomain(domain: string): SpecializedAgent[] {
    return Array.from(this.agents.values())
      .filter(agent => agent.capabilities.domain.toLowerCase() === domain.toLowerCase());
  }
  
  sendTaskToAgent(agentName: string, task: AgentTask): Promise<AgentResult> {
    const agent = this.getAgent(agentName);
    if (!agent) {
      return Promise.resolve({
        taskId: task.id,
        success: false,
        data: null,
        confidence: 0,
        executionTime: 0,
        metadata: { error: `Agent ${agentName} not found` }
      });
    }
    
    return new Promise((resolve) => {
      const completableTask = { ...task, callback: resolve };
      agent.addTask(completableTask);
    });
  }
}

// Global registry instance
export const specializedAgentRegistry = new SpecializedAgentRegistry();

