// Learning and Adaptation Engine for Nancy Billion
// Continuous self-improvement through experience and feedback

export class LearningAdaptationEngine {
  constructor() {
    console.log("[LearningAdaptationEngine] Initialized");
    this.learningHistory = [];
    self.improvementMetrics = {
      accuracy: 0.8,
      responseTime: 1200, // ms
      userSatisfaction: 0.75,
      taskCompletionRate: 0.82
    };
  }
  
  learnFromInteraction(interactionData) {
    const learningEntry = {
      timestamp: Date.now(),
      interactionType: interactionData.type,
      context: interactionData.context || {},
      outcome: interactionData.outcome || "unknown",
      userFeedback: interactionData.feedback || null,
      successMetric: this.calculateSuccessMetric(interactionData)
    };
    
    this.learningHistory.push(learningEntry);
    
    // Keep only last 1000 entries to prevent memory issues
    if (this.learningHistory.length > 1000) {
      this.learningHistory = this.learningHistory.slice(-1000);
    }
    
    this.updateImprovementMetrics();
    this.generateInsights();
    
    console.log("[LearningAdaptationEngine] Learned from interaction:", interactionData.type);
  }
  
  calculateSuccessMetric(interactionData) {
    // Simple heuristic for success measurement
    // In implementation: use more sophisticated ML models
    let score = 0.5; // base score
    
    if (interactionData.userRating) {
      score = interactionData.userRating / 5; // normalize 1-5 to 0-1
    } else if (interactionData.taskCompleted !== undefined) {
      score = interactionData.taskCompleted ? 0.8 : 0.3;
    } else if (interactionData.responseTime) {
      // Faster responses are better (up to a point)
      const timeScore = Math.max(0, 1 - (interactionData.responseTime / 5000)); // 5s max
      score = Math.min(1, 0.3 + timeScore * 0.7);
    }
    
    return Math.min(1, Math.max(0, score));
  }
  
  updateImprovementMetrics() {
    // Update metrics based on recent learning history
    const recent = this.learningHistory.slice(-50); // last 50 interactions
    
    if (recent.length === 0) return;
    
    // Calculate average success rate
    const successRate = recent.reduce((sum, entry) => sum + (entry.successMetric || 0.5), 0) / recent.length;
    
    // Simulate improvement in various metrics
    this.improvementMetrics.accuracy = 0.7 + (successRate * 0.3);
    this.improvementMetrics.userSatisfaction = 0.6 + (successRate * 0.4);
    this.improvementMetrics.taskCompletionRate = 0.7 + (successRate * 0.3);
    
    // Response time improves with practice (asymptotic improvement)
    const experienceFactor = Math.min(1, this.learningHistory.length / 1000);
    this.improvementMetrics.responseTime = 1500 - (experienceFactor * 500); // 1000-1500ms range
  }
  
  generateInsights() {
    // Generate insights from learning patterns
    // In implementation: use clustering, trend analysis, etc.
    const recent = this.learningHistory.slice(-20);
    
    if (recent.length < 5) return [];
    
    const insights = [];
    
    # Time-based patterns
    const hourCounts = {};
    recent.forEach(entry => {
      const hour = new Date(entry.timestamp).getHours();
      hourCounts[hour] = (hourCounts[hour] || 0) + 1;
    });
    
    const peakHour = Object.keys(hourCounts).reduce((a, b) => 
      hourCounts[a] > hourCounts[b] ? a : b
    );
    
    if (hourCounts[parseInt(peakHour)] > 3) {
      insights.push({
        type: "temporal-pattern",
        description: f"You interact most frequently around {peakHour}:00",
        confidence: 0.7,
        actionable: true
      });
    }
    
    # Success pattern insights
    const successfulInteractions = recent.filter(e => (e.successMetric || 0) > 0.7);
    if (successfulInteractions.length > recent.length * 0.6) {
      insights.push({
        type: "performance-pattern",
        description: "Your interaction success rate is above average",
        confidence: 0.8,
        actionable: false
      });
    }
    
    return insights;
  }
  
  getInsights() {
    // Return recent insights
    return []; // Simplified for now
  }
  
  getImprovementMetrics() {
    return { ...this.improvementMetrics };
  }
  
  getLearningStatistics() {
    return {
      totalInteractions: this.learningHistory.length,
      learningPeriodDays: Math.max(1, (Date.now() - (this.learningHistory[0]?.timestamp || Date.now())) / (24 * 60 * 60 * 1000)),
      averageInteractionsPerDay: this.learningHistory.length / Math.max(1, (Date.now() - (this.learningHistory[0]?.timestamp || Date.now())) / (24 * 60 * 60 * 1000)),
      recentTrend: "improving" // simplified
    };
  }
  
  adaptPersonality(userPreferences) {
    console.log("[LearningAdaptationEngine] Adapting personality based on:", userPreferences);
    // In implementation: adjust communication style, humor, formality, etc.
    return {
      communicationStyle: userPreferences.formality || "balanced",
      humorLevel: userPreferences.humor || 0.5,
      proactivityLevel: userPreferences.initiative || 0.6
    };
  }
}

// Singleton instance
export const learningAdaptationEngine = new LearningAdaptationEngine();
