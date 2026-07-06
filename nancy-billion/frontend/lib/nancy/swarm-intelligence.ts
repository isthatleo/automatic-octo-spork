'use strict'

/**
 * Swarm Intelligence System for Nancy-billion
 * Inspired by MiroFish's multi-agent simulation capabilities
 */

export interface Agent {
  id: string
  name: string
  role: string
  personality: string
  memory: Memory[]
  beliefs: Belief[]
  goals: Goal[]
  position: { x: number; y: number; z: number }
  velocity: { x: number; y: number; z: number }
  energy: number
  age: number
}

export interface Memory {
  id: string
  content: string
  timestamp: number
  importance: number  // 0-1
  emotion: string     // joy, sadness, anger, fear, surprise, disgust
  relatedAgents: string[]  // IDs of agents involved in this memory
}

export interface Belief {
  id: string
  proposition: string
  confidence: number  // 0-1
  source: string      // how this belief was acquired
  timestamp: number
}

export interface Goal {
  id: string
  description: string
  priority: number    // 0-1
  progress: number    // 0-1
  timestamp: number
  completed: boolean
}

export interface EnvironmentalFactor {
  type: string        // resource, threat, opportunity, etc.
  intensity: number   // 0-1
  position: { x: number; y: number; z: number }
  radius: number
  timestamp: number
}

export interface SimulationState {
  agents: Agent[]
  environment: EnvironmentalFactor[]
  timestamp: number
  generation: number
  statistics: SimulationStatistics
}

export interface SimulationStatistics {
  totalAgents: number
  averageEnergy: number
  birthRate: number
  deathRate: number
  interactionRate: number
  knowledgeSharing: number
  conflictRate: number
  cooperationRate: number
}

export class SwarmIntelligenceEngine {
  private agents: Agent[] = []
  private environment: EnvironmentalFactor[] = []
  private simulationRunning = false
  private simulationInterval: NodeJS.Timeout | null = null
  private generationCount = 0
  
  // Simulation parameters
  private readonly worldSize = { x: 1000, y: 1000, z: 100 }
  private readonly maxAgents = 1000
  private readonly energyDecayRate = 0.01
  private readonly reproductionThreshold = 0.8
  private readonly starvationThreshold = 0.2
  
  constructor() {
    // Initialize with a few seed agents
    this.initializeSeedAgents()
  }
  
  private initializeSeedAgents(): void {
    // Create initial agents with different roles
    const roles = [
      { name: 'Explorer', personality: 'curious', count: 5 },
      { name: 'Builder', personality: 'diligent', count: 5 },
      { name: 'Guardian', personality: 'protective', count: 3 },
      { name: 'Trader', personality: 'social', count: 4 },
      { name: 'Researcher', personality: 'analytical', count: 3 }
    ]
    
    let agentId = 0
    for (const role of roles) {
      for (let i = 0; i < role.count; i++) {
        this.agents.push(this.createAgent(
          `${role.name}-${agentId++}`,
          role.name,
          role.personality
        ))
      }
    }
  }
  
  private createAgent(id: string, name: string, personality: string): Agent {
    return {
      id,
      name,
      role: name.split('-')[0], // Extract base role
      personality,
      memory: [],
      beliefs: [],
      goals: [],
      position: {
        x: Math.random() * this.worldSize.x,
        y: Math.random() * this.worldSize.y,
        z: Math.random() * this.worldSize.z
      },
      velocity: {
        x: (Math.random() - 0.5) * 2,
        y: (Math.random() - 0.5) * 2,
        z: (Math.random() - 0.5) * 2
      },
      energy: 0.5 + Math.random() * 0.5,
      age: 0
    }
  }
  
  /**
   * Start the swarm intelligence simulation
   */
  startSimulation(): void {
    if (this.simulationRunning) return
    
    this.simulationRunning = true
    this.simulationInterval = setInterval(() => {
      this.simulationStep()
    }, 1000) // 1 second per simulation step
    
    console.log('Swarm intelligence simulation started')
  }
  
  /**
   * Stop the swarm intelligence simulation
   */
  stopSimulation(): void {
    if (!this.simulationRunning) return
    
    if (this.simulationInterval) {
      clearInterval(this.simulationInterval)
      this.simulationInterval = null
    }
    
    this.simulationRunning = false
    console.log('Swarm intelligence simulation stopped')
  }
  
  /**
   * Perform one simulation step
   */
  private simulationStep(): void {
    if (!this.simulationRunning) return
    
    this.generationCount++
    
    // Update agent states
    this.updateAgentEnergies()
    this.updateAgentPositions()
    this.facilitateAgentInteractions()
    this.processAgentGoals()
    this.handleReproductionAndDeath()
    this.updateEnvironment()
    
    // Generate statistics
    const stats = this.generateStatistics()
    
    // Optionally emit simulation state for visualization/monitoring
    this.emitSimulationState(stats)
  }
  
  private updateAgentEnergies(): void {
    for (const agent of this.agents) {
      // Basic energy decay
      agent.energy -= this.energyDecayRate
      
      // Energy gain from resting (if not moving much)
      const speed = Math.sqrt(
        agent.velocity.x ** 2 + 
        agent.velocity.y ** 2 + 
        agent.velocity.z ** 2
      )
      if (speed < 0.1) {
        agent.energy = Math.min(1.0, agent.energy + 0.005)
      }
      
      // Energy loss from aging
      agent.age += 1/3600 // Increment age by 1 second in hours
      if (agent.age > 50) { // Agents start losing energy after 50 hours
        agent.energy -= (agent.age - 50) * 0.0001
      }
      
      // Clamp energy
      agent.energy = Math.max(0, Math.min(1, agent.energy))
    }
  }
  
  private updateAgentPositions(): void {
    for (const agent of this.agents) {
      // Apply velocity
      agent.position.x += agent.velocity.x
      agent.position.y += agent.velocity.y
      agent.position.z += agent.velocity.z
      
      // Boundary conditions (wrap around)
      agent.position.x = ((agent.position.x % this.worldSize.x) + this.worldSize.x) % this.worldSize.x
      agent.position.y = ((agent.position.y % this.worldSize.y) + this.worldSize.y) % this.worldSize.y
      agent.position.z = ((agent.position.z % this.worldSize.z) + this.worldSize.z) % this.worldSize.z
      
      # Apply velocity
      agent.position.x += agent.velocity.x
      agent.position.y += agent.velocity.y
      agent.position.z += agent.velocity.z
      
      # Boundary conditions (wrap around)
      agent.position.x = ((agent.position.x % this.worldSize.x) + this.worldSize.x) % this.worldSize.x
      agent.position.y = ((agent.position.y % this.worldSize.y) + this.worldSize.y) % this.worldSize.y
      agent.position.z = ((agent.position.z % this.worldSize.z) + this.worldSize.z) % this.worldSize.z
      
      # Apply velocity
      agent.position.x += agent.velocity.x
      agent.position.y += agent.velocity.y
      agent.position.z += agent.velocity.z
      
      # Boundary conditions (wrap around)
      agent.position.x = ((agent.position.x % this.worldSize.x) + this.worldSize.x) % this.worldSize.x
      agent.position.y = ((agent.position.y % this.worldSize.y) + this.worldSize.y) % this.worldSize.y
      agent.position.z = ((agent.position.z % this.worldSize.z) + this.worldSize.z) % this.worldSize.z
      
    }
  }
  
  private facilitateAgentInteractions(): void {
    # Facilitate interactions between nearby agents
    for (let i = 0; i < this.agents.length; i++) {
      for (let j = i + 1; j < this.agents.length; j++) {
        const agent1 = this.agents[i]
        const agent2 = this.agents[j]
        
        # Calculate distance
        const dx = agent1.position.x - agent2.position.x
        const dy = agent1.position.y - agent2.position.y
        const dz = agent1.position.z - agent2.position.z
        const distance = Math.sqrt(dx*dx + dy*dy + dz*dz)
        
        # Interaction threshold
        if (distance < 10) {  # Within 10 units
          this.processInteraction(agent1, agent2, distance)
        }
      }
    }
  }
  
  private processInteraction(agent1: Agent, agent2: Agent, distance: number): void {
    # Determine interaction type based on personalities and roles
    let interactionType: 'knowledge_sharing' | 'trade' | 'conflict' | 'cooperation' = 'knowledge_sharing'
    
    # Simple heuristic for interaction type
    if (agent1.personality === 'curious' || agent2.personality === 'curious') {
      interactionType = 'knowledge_sharing'
    } else if (agent1.role === 'Guardian' || agent2.role === 'Guardian') {
      interactionType = Math.random() > 0.5 ? 'conflict' : 'cooperation'
    } else if (agent1.role === 'Trader' || agent2.role === 'Trader') {
      interactionType = 'trade'
    } else {
      interactionType = Math.random() > 0.7 ? 'cooperation' : 'conflict'
    }
    
    # Process the interaction
    switch (interactionType) {
      case 'knowledge_sharing':
        # Share memories and beliefs
        if (agent1.memory.length > 0 && Math.random() > 0.7) {
          const memoryToShare = agent1.memory[Math.floor(Math.random() * agent1.memory.length)]
          agent2.memory.push({
            ...memoryToShare,
            id: `shared-${Date.now()}-${Math.random()}`,
            timestamp: Date.now()
          })
        }
        
        if (agent2.memory.length > 0 && Math.random() > 0.7) {
          const memoryToShare = agent2.memory[Math.floor(Math.random() * agent2.memory.length)]
          agent1.memory.push({
            ...memoryToShare,
            id: `shared-${Date.now()}-${Math.random()}`,
            timestamp: Date.now()
          })
        }
        break
        
      case 'trade':
        # Exchange energy or resources
        if (agent1.energy > 0.6 && agent2.energy < 0.4) {
          const transfer = Math.min(0.2, agent1.energy - 0.5, 0.5 - agent2.energy)
          agent1.energy -= transfer
          agent2.energy += transfer
        } else if (agent2.energy > 0.6 && agent1.energy < 0.4) {
          const transfer = Math.min(0.2, agent2.energy - 0.5, 0.5 - agent1.energy)
          agent2.energy -= transfer
          agent1.energy += transfer
        }
        break
        
      case 'conflict':
        # Reduce energy of both agents
        const damage = 0.1 * (1 + Math.random())
        agent1.energy = Math.max(0, agent1.energy - damage)
        agent2.energy = Math.max(0, agent2.energy - damage)
        break
        
      case 'cooperation':
        # Increase energy of both agents slightly
        const bonus = 0.05
        agent1.energy = Math.min(1, agent1.energy + bonus)
        agent2.energy = Math.min(1, agent2.energy + bonus)
        break
    }
    
    # Create shared memory of interaction
    const interactionMemory: Memory = {
      id: `interaction-${Date.now()}-${Math.random()}`,
      content: `${agent1.name} interacted with ${agent2.name} (${interactionType})`,
      timestamp: Date.now(),
      importance: 0.3,
      emotion: interactionType === 'conflict' ? 'anger' : 
               interactionType === 'cooperation' ? 'joy' : 'neutral',
      relatedAgents: [agent1.id, agent2.id]
    }
    
    agent1.memory.push(interactionMemory)
    agent2.memory.push(interactionMemory)
  }
  
  private processAgentGoals(): void {
    for (const agent of this.agents) {
      # Process each agent's goals
      for (const goal of agent.goals) {
        if (!goal.completed) {
          # Simple goal progression based on agent energy and activity
          const progressIncrement = 0.001 * (0.5 + agent.energy)
          goal.progress = Math.min(1, goal.progress + progressIncrement)
          
          # Check if goal is completed
          if (goal.progress >= 1.0) {
            goal.completed = true
            # Goal completion might give energy boost or create new goals
            agent.energy = Math.min(1, agent.energy + 0.1)
          }
        }
      }
      
      # Generate new goals occasionally
      if (Math.random() < 0.001 && agent.energy > 0.3) {  # 0.1% chance per step
        agent.goals.push({
          id: `goal-${Date.now()}-${Math.random()}`,
          description: this.generateRandomGoal(agent.role, agent.personality),
          priority: 0.3 + Math.random() * 0.7,
          progress: 0,
          timestamp: Date.now(),
          completed: false
        })
      }
    }
  }
  
  private generateRandomGoal(role: string, personality: string): string {
    const goalsByRole: Record<string, string[]> = {
      Explorer: [
        'Explore uncharted territory',
        'Discover new resources',
        'Map the surrounding area',
        'Find signs of other intelligences'
      ],
      Builder: [
        'Construct shelter',
        'Improve existing structures',
        'Create tools',
        'Expand living space'
      ],
      Guardian: [
        'Patrol the perimeter',
        'Protect vulnerable agents',
        'Monitor for threats',
        'Establish watch rotations'
      ],
      Trader: [
        'Establish trade routes',
        'Negotiate with other groups',
        'Accumulate resources',
        'Improve trade efficiency'
      ],
      Researcher: [
        'Study the environment',
        'Analyze patterns in data',
        'Develop theories',
        'Share findings with group'
      ]
    }
    
    const goals = goalsByRole[role] || ['Survive and thrive']
    return goals[Math.floor(Math.random() * goals.length)]
  }
  
  private handleReproductionAndDeath(): void {
    # Handle agent death from starvation or old age
    this.agents = this.agents.filter(agent => {
      # Death from starvation
      if (agent.energy < this.starvationThreshold) {
        return false
      }
      
      # Death from old age (very rare in this simulation)
      if (agent.age > 200 && Math.random() < 0.0001) {  # 0.01% chance per hour after 200 hours
        return false
      }
      
      return true
    })
    
    # Handle reproduction
    const newAgents: Agent[] = []
    for (const agent of this.agents) {
      # Reproduction chance based on energy and age
      if (agent.energy > this.reproductionThreshold && agent.age > 10 && agent.age < 100) {
        if (Math.random() < 0.0005) {  # 0.05% chance per step
          # Create offspring with slight mutations
          const offspring = this.createAgent(
            `offspring-${agent.id}-${Date.now()}`,
            agent.role.split('-')[0],  # Base role
            agent.personality
          )
          
          # Slightly different position and energy
          offspring.position = {
            x: agent.position.x + (Math.random() - 0.5) * 10,
            y: agent.position.y + (Math.random() - 0.5) * 10,
            z: agent.position.z + (Math.random() - 0.5) * 5
          }
          offspring.energy = 0.3 + Math.random() * 0.4
          
          newAgents.push(offspring)
          
          # Parent loses some energy for reproduction
          agent.energy = Math.max(0.1, agent.energy - 0.2)
        }
      }
    }
    
    # Add new agents if we haven't exceeded max population
    if (this.agents.length + newAgents.length <= this.maxAgents) {
      this.agents.push(...newAgents)
    }
  }
  
  private updateEnvironment(): void {
    # Update environmental factors
    # Add new factors occasionally
    if (Math.random() < 0.01) {  # 1% chance per step
      const factorTypes = ['resource', 'threat', 'opportunity', ' hazard']
      const type = factorTypes[Math.floor(Math.random() * factorTypes.length)]
      
      this.environment.push({
        type,
        intensity: 0.3 + Math.random() * 0.7,
        position: {
          x: Math.random() * this.worldSize.x,
          y: Math.random() * this.worldSize.y,
          z: Math.random() * this.worldSize.z
        },
        radius: 5 + Math.random() * 15,
        timestamp: Date.now()
      })
    }
    
    # Remove old factors
    this.environment = this.environment.filter(factor => 
      Date.now() - factor.timestamp < 3600000  # 1 hour
    )
  }
  
  private generateStatistics(): SimulationStatistics {
    const totalAgents = this.agents.length
    if (totalAgents === 0) {
      return {
        totalAgents: 0,
        averageEnergy: 0,
        birthRate: 0,
        deathRate: 0,
        interactionRate: 0,
        knowledgeSharing: 0,
        conflictRate: 0,
        cooperationRate: 0
      }
    }
    
    const averageEnergy = this.agents.reduce((sum, agent) => sum + agent.energy, 0) / totalAgents
    
    # Simplified rate calculations
    const interactionOpportunities = totalAgents * (totalAgents - 1) / 2
    const actualInteractions = this.countRecentInteractions()
    const interactionRate = interactionOpportunities > 0 ? actualInteractions / interactionOpportunities : 0
    
    # Count different interaction types from recent memories
    let knowledgeSharingCount = 0
    let conflictCount = 0
    let cooperationCount = 0
    
    const recentMemories = this.getRecentMemories(60000)  # Last minute
    for (const memory of recentMemories) {
      if (memory.content.includes('interacted')) {
        if (memory.emotion === 'anger') {
          conflictCount++
        } else if (memory.emotion === 'joy') {
          cooperationCount++
        } else {
          knowledgeSharingCount++
        }
      }
    }
    
    return {
      totalAgents,
      averageEnergy: Number(averageEnergy.toFixed(3)),
      birthRate: this.calculateBirthRate(),
      deathRate: this.calculateDeathRate(),
      interactionRate: Number(interactionRate.toFixed(3)),
      knowledgeSharing: Number((knowledgeSharingCount / Math.max(1, recentMemories.length)).toFixed(3)),
      conflict: Number((conflictCount / Math.max(1, recentMemories.length)).toFixed(3)),
      cooperation: Number((cooperationCount / Math.max(1, recentMemories.length)).toFixed(3))
    }
  }
  
  private countRecentInteractions(): number {
    # Simplified - in reality would track actual interactions
    return Math.floor(this.agents.length * 0.1)
  }
  
  private calculateBirthRate(): number {
    # Simplified birth rate calculation
    return this.agents.length > 0 ? Math.min(0.1, this.agents.length / 1000) : 0
  }
  
  private calculateDeathRate(): number {
    # Simplified death rate calculation
    return this.agents.length > 0 ? Math.max(0, 0.05 - this.agents.length / 2000) : 0
  }
  
  private getRecentMemories(milliseconds: number): Memory[] {
    const cutoff = Date.now() - milliseconds
    let recent: Memory[] = []
    
    for (const agent of this.agents) {
      recent = recent.concat(
        agent.memory.filter(m => m.timestamp >= cutoff)
      )
    }
    
    return recent
  }
  
  private emitSimulationState(stats: SimulationStatistics): void {
    # In a real implementation, this would send data to visualization components
    # For now, we'll just log occasionally
    if (this.generationCount % 100 === 0) {  # Every 100 seconds
      console.log(`Swarm Simulation - Generation: ${this.generationCount}, ` +
                  `Agents: ${stats.totalAgents}, ` +
                  `Avg Energy: ${stats.averageEnergy}, ` +
                  `Interactions: ${stats.interactionRate.toFixed(2)}`)
    }
  }
  
  /**
   * Get current simulation state
   */
  getState(): SimulationState {
    return {
      agents: [...this.agents],
      environment: [...this.environment],
      timestamp: Date.now(),
      generation: this.generationCount,
      statistics: this.generateStatistics()
    }
  }
  
  /**
   * Add a custom environmental factor
   */
  addEnvironmentalFactor(factor: Omit<EnvironmentalFactor, 'timestamp'>): void {
    this.environment.push({
      ...factor,
      timestamp: Date.now()
    })
  }
  
  /**
   * Get agent by ID
   */
  getAgentById(id: string): Agent | undefined {
    return this.agents.find(agent => agent.id === id)
  }
  
  /**
   * Get agents in a specific area
   */
  getAgentsInArea(center: { x: number; y: number; z: number }, radius: number): Agent[] {
    return this.agents.filter(agent => {
      const dx = agent.position.x - center.x
      const dy = agent.position.y - center.y
      const dz = agent.position.z - center.z
      const distance = Math.sqrt(dx*dx + dy*dy + dz*dz)
      return distance <= radius
    })
  }
}

// Export singleton instance
export const swarmEngine = new SwarmIntelligenceEngine()