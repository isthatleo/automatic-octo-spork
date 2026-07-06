// Phase 3 Coordinator for Nancy Billion
// Orchestrates all advanced AI consciousness systems

import { useEffect, useState } from "react";
import { enhancedProactiveAssistant } from "@/lib/nancy/proactive-assistant-enhanced";
import { emotionalIntelligenceEngine } from "@/lib/nancy/emotional-intelligence";
import { environmentalAwarenessSystem } from "@/lib/nancy/environmental-awareness";
import { learningAdaptationEngine } from "@/lib/nancy/learning-adaptation";

export function Phase3Coordinator() {
  const [status, setStatus] = useState({
    proactive: "idle",
    emotional: "idle", 
    environmental: "idle",
    learning: "idle"
  });

  useEffect(() => {
    // Initialize all Phase 3 systems
    initializePhase3Systems();
    
    return () => {
      // Cleanup on unmount
      shutdownPhase3Systems();
    };
  }, []);

  const initializePhase3Systems = () => {
    try {
      // Start proactive assistance system
      enhancedProactiveAssistant.start();
      setStatus(prev => ({ ...prev, proactive: "active" }));
      
      // Initialize emotional intelligence
      emotionalIntelligenceEngine.initialize?.();
      setStatus(prev => ({ ...prev, emotional: "active" }));
      
      // Start environmental awareness
      environmentalAwarenessSystem.startMonitoring?.();
      setStatus(prev => ({ ...prev, environmental: "active" }));
      
      // Begin learning cycle
      learningAdaptationEngine.startLearningCycle?.();
      setStatus(prev => ({ ...prev, learning: "active" }));
      
      console.log("[Phase3Coordinator] All systems initialized");
    } catch (error) {
      console.error("[Phase3Coordinator] Initialization error:", error);
      setStatus(prev => ({ ...prev, error: error.message }));
    }
  };

  const shutdownPhase3Systems = () => {
    try {
      enhancedProactiveAssistant.stop();
      environmentalAwarenessSystem.stopMonitoring?.();
      learningAdaptationEngine.stopLearningCycle?.();
      console.log("[Phase3Coordinator] All systems shutdown");
    } catch (error) {
      console.error("[Phase3Coordinator] Shutdown error:", error);
    }
  };

  const getSystemStatus = () => {
    return {
      proactive: enhancedProactiveAssistant.getStatus ? enhancedProactiveAssistant.getStatus() : "unknown",
      emotional: emotionalIntelligenceEngine.getStatus ? emotionalIntelligenceEngine.getStatus() : "unknown", 
      environmental: environmentalAwarenessSystem.getStatus ? environmentalAwarenessSystem.getStatus() : "unknown",
      learning: learningAdaptationEngine.getStatus ? learningAdaptationEngine.getStatus() : "unknown",
      timestamp: Date.now()
    };
  };

  return (
    <div className="fixed bottom-4 right-4 space-x-2 z-50">
      {/* System Status Indicators */}
      <div 
        title="Proactive Assistance" 
        className={`p-2 rounded ${status.proactive === "active" ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"} text-xs`}
      >
        🤖
      </div>
      
      <div 
        title="Emotional Intelligence" 
        className={`p-2 rounded ${status.emotional === "active" ? "bg-blue-500/20 text-blue-400" : "bg-red-500/20 text-red-400"} text-xs`}
      >
        ❤️
      </div>
      
      <div 
        title="Environmental Awareness" 
        className={`p-2 rounded ${status.environmental === "active" ? "bg-purple-500/20 text-purple-400" : "bg-red-500/20 text-red-400"} text-xs`}
      >
        🌍
      </div>
      
      <div 
        title="Learning & Adaptation" 
        className={`p-2 rounded ${status.learning === "active" ? "bg-orange-500/20 text-orange-400" : "bg-red-500/20 text-orange-400"} text-xs`}
      >
        🧠
      </div>
    </div>
  );
}

// Export enhanced Nancy Orb with Phase 3 capabilities
export { enhancedProactiveAssistant, emotionalIntelligenceEngine, environmentalAwarenessSystem, learningAdaptationEngine };
export default Phase3Coordinator;
