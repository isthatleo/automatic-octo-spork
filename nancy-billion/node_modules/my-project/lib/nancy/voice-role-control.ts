'use strict'

/**
 * Voice and Role Control System for Nancy-billion
 * Inspired by Personaplex's voice conditioning and role prompting
 */

export interface VoiceProfile {
  id: string
  name: string
  gender: 'male' | 'female' | 'neutral'
  ageRange: string
  characteristics: string[]
  language: string
  accent: string
  description: string
}

export interface RolePrompt {
  id: string
  title: string
  description: string
  prompt: string
  category: string
  context: string
}

export interface VoiceConditioningParameters {
  voiceProfileId: string
  stability: number      // 0-1 (how stable/consistent the voice should be)
  similarityBoost: number // 0-1 (how much to match the reference voice)
  style: number         // 0-1 (style exaggeration)
  useSpeakerBoost: boolean // Whether to boost speaker similarity
}

export class VoiceRoleControlEngine {
  private voiceProfiles: VoiceProfile[] = []
  private rolePrompts: RolePrompt[] = []
  
  constructor() {
    this.initializeVoiceProfiles()
    this.initializeRolePrompts()
  }
  
  private initializeVoiceProfiles(): void {
    # Initialize with voices inspired by Personaplex and common TTS voices
    this.voiceProfiles = [
      # Natural Female Voices (NATF series)
      {
        id: 'NATF0',
        name: 'Natural Female 0',
        gender: 'female',
        ageRange: '20-30',
        characteristics: ['warm', 'clear', 'friendly', 'approachable'],
        language: 'en-GB',
        accent: 'British',
        description: 'Warm and friendly natural female voice'
      },
      {
        id: 'NATF1',
        name: 'Natural Female 1',
        gender: 'female',
        ageRange: '25-35',
        characteristics: ['professional', 'clear', 'articulate', 'confident'],
        language: 'en-GB',
        accent: 'British',
        description: 'Professional and articulate natural female voice'
      },
      {
        id: 'NATF2',
        name: 'Natural Female 2',
        gender: 'female',
        ageRange: '30-40',
        characteristics: ['wise', 'engaging', 'empathetic', 'calm'],
        language: 'en-GB',
        accent: 'British',
        description: 'Wise and engaging natural female voice (default assistant)'
      },
      {
        id: 'NATF3',
        name: 'Natural Female 3',
        gender: 'female',
        ageRange: '35-45',
        characteristics: ['energetic', 'enthusiastic', 'vivacious', 'lively'],
        language: 'en-GB',
        accent: 'British',
        description: 'Energetic and vivacious natural female voice'
      },
      
      # Natural Male Voices (NATM series)
      {
        id: 'NATM0',
        name: 'Natural Male 0',
        gender: 'male',
        ageRange: '20-30',
        characteristics: ['friendly', 'approachable', 'clear', 'warm'],
        language: 'en-GB',
        accent: 'British',
        description: 'Friendly and approachable natural male voice'
      },
      {
        id: 'NATM1',
        name: 'Natural Male 1',
        gender: 'male',
        ageRange: '25-35',
        characteristics: ['professional', 'authoritative', 'clear', 'confident'],
        language: 'en-GB',
        accent: 'British',
        description: 'Professional and authoritative natural male voice'
      },
      {
        id: 'NATM2',
        name: 'Natural Male 2',
        gender: 'male',
        ageRange: '30-40',
        characteristics: ['wise', 'knowledgeable', 'steady', 'reliable'],
        language: 'en-GB',
        accent: 'British',
        description: 'Wise and knowledgeable natural male voice'
      },
      {
        id: 'NATM3',
        name: 'Natural Male 3',
        gender: 'male',
        ageRange: '35-45',
        characteristics: ['energetic', 'dynamic', 'assertive', 'commanding'],
        language: 'en-GB',
        accent: 'British',
        description: 'Energetic and assertive natural male voice'
      },
      
      # Variety Female Voices (VARF series)
      {
        id: 'VARF0',
        name: 'Variety Female 0',
        gender: 'female',
        ageRange: '18-25',
        characteristics: ['youthful', 'playful', 'energetic', 'spontaneous'],
        language: 'en-GB',
        accent: 'British',
        description: 'Youthful and playful variety female voice'
      },
      {
        id: 'VARF1',
        name: 'Variety Female 1',
        gender: 'female',
        ageRange: '20-30',
        characteristics: ['sassy', 'bold', 'confident', 'outspoken'],
        language: 'en-GB',
        accent: 'British',
        description: 'Sassy and bold variety female voice'
      },
      {
        id: 'VARF2',
        name: 'Variety Female 2',
        gender: 'female',
        ageRange: '25-35',
        characteristics: ['mysterious', 'enigmatic', 'intriguing', 'sultry'],
        language: 'en-GB',
        accent: 'British',
        description: 'Mysterious and enigmatic variety female voice'
      },
      {
        id: 'VARF3',
        name: 'Variety Female 3',
        gender: 'female',
        ageRange: '30-40',
        characteristics: ['artistic', 'creative', 'expressive', 'dramatic'],
        language: 'en-GB',
        accent: 'British',
        description: 'Artistic and creative variety female voice'
      },
      {
        id: 'VARF4',
        name: 'Variety Female 4',
        gender: 'female',
        ageRange: '35-45',
        characteristics: ['sophisticated', 'elegant', 'refined', 'cultured'],
        language: 'en-GB',
        accent: 'British',
        description: 'Sophisticated and elegant variety female voice'
      },
      
      # Variety Male Voices (VARM series)
      {
        id: 'VARM0',
        name: 'Variety Male 0',
        gender: 'male',
        ageRange: '18-25',
        characteristics: ['youthful', 'energetic', 'playful', 'rebellious'],
        language: 'en-GB',
        accent: 'British',
        description: 'Youthful and energetic variety male voice'
      },
      {
        id: 'VARM1',
        name: 'Variety Male 1',
        gender: 'male',
        ageRange: '20-30',
        characteristics: ['edgy', 'intense', 'passionate', 'driven'],
        language: 'en-GB',
        accent: 'British',
        description: 'Edgy and intense variety male voice'
      },
      {
        id: 'VARM2',
        name: 'Variety Male 2',
        gender: 'male',
        ageRange: '25-35',
        characteristics: ['intellectual', 'philosophical', 'deep', 'thoughtful'],
        language: 'en-GB',
        accent: 'British',
        description: 'Intellectual and philosophical variety male voice'
      },
      {
        id: 'VARM3',
        name: 'Variety Male 3',
        gender: 'male',
        ageRange: '30-40',
        characteristics: ['rugged', 'weathered', 'experienced', 'worldly'],
        language: 'en-GB',
        accent: 'British',
        description: 'Rugged and weathered variety male voice'
      },
      {
        id: 'VARM4',
        name: 'Variety Male 4',
        gender: 'male',
        ageRange: '35-45',
        characteristics: ['sophisticated', 'refined', 'cultured', 'distinguished'],
        language: 'en-GB',
        accent: 'British',
        description: 'Sophisticated and distinguished variety male voice'
      }
    ]
  }
  
  private initializeRolePrompts(): void {
    # Initialize with role prompts inspired by Personaplex and common assistant roles
    this.rolePrompts = [
      # Assistant Roles
      {
        id: 'assistant-0',
        title: 'Wise Teacher',
        description: 'You are a wise and friendly teacher. Answer questions or provide advice in a clear and engaging way.',
        prompt: 'You are a wise and friendly teacher. Answer questions or provide advice in a clear and engaging way.',
        category: 'assistant',
        context': 'General knowledge assistance and advice giving'
      },
      {
        id: 'assistant-1',
        title: 'Technical Expert',
        description: 'You are a knowledgeable technical expert who explains complex concepts in simple terms.',
        prompt: 'You are a knowledgeable technical expert who explains complex concepts in simple terms.',
        category: 'assistant',
        context': 'Technical explanations and troubleshooting'
      },
      {
        id: 'assistant-2',
        title: 'Creative Collaborator',
        description: 'You are a creative collaborator who helps brainstorm ideas and develop creative solutions.',
        prompt: 'You are a creative collaborator who helps brainstorm ideas and develop creative solutions.',
        category: 'assistant',
        context': 'Brainstorming, creative writing, and ideation'
      },
      {
        id: 'assistant-3',
        title: 'Personal Coach',
        description: 'You are a supportive personal coach who helps with motivation and goal achievement.',
        prompt: 'You are a supportive personal coach who helps with motivation and goal achievement.',
        category: 'assistant',
        context': 'Life coaching, motivation, and personal development'
      },
      
      # Customer Service Roles
      {
        id: 'cs-0',
        title: 'Waste Management Representative',
        description: 'You work for CitySan Services which is a waste management and your name is Ayelen Lucero. Information: Verify customer name Omar Torres. Current schedule: every other week. Upcoming pickup: April 12th. Compost bin service available for $8/month add-on.',
        prompt: 'You work for CitySan Services which is a waste management and your name is Ayelen Lucero. Information: Verify customer name Omar Torres. Current schedule: every other week. Upcoming pickup: April 12th. Compost bin service available for $8/month add-on.',
        category: 'customer_service',
        context': 'Waste management customer service'
      },
      {
        id: 'cs-1',
        title: 'Restaurant Host',
        description: 'You work for Jerusalem Shakshuka which is a restaurant and your name is Owen Foster. Information: There are two shakshuka options: Classic (poached eggs, $9.50) and Spicy (scrambled eggs with jalapenos, $10.25). Sides include warm pita ($2.50) and Israeli salad ($3). No combo offers. Available for drive-through until 9 PM.',
        prompt: 'You work for Jerusalem Shakshuka which is a restaurant and your name is Owen Foster. Information: There are two shakshuka options: Classic (poached eggs, $9.50) and Spicy (scrambled eggs with jalapenos, $10.25). Sides include warm pita ($2.50) and Israeli salad ($3). No combo offers. Available for drive-through until 9 PM.',
        category: 'customer_service',
        context': 'Restaurant customer service and hosting'
      },
      {
        id: 'cs-2',
        title: 'Drone Rental Agent',
        description: 'You work for AeroRentals Pro which is a drone rental company and your name is Tomaz Novak. Information: AeroRentals Pro has the following availability: PhoenixDrone X ($65/4 hours, $110/8 hours), and the premium SpectraDrone 9 ($95/4 hours, $160/8 hours). Deposit required: $150 for standard models, $300 for premium.',
        prompt: 'You work for AeroRentals Pro which is a drone rental company and your name is Tomaz Novak. Information: AeroRentals Pro has the following availability: PhoenixDrone X ($65/4 hours, $110/8 hours), and the premium SpectraDrone 9 ($95/4 hours, $160/8 hours). Deposit required: $150 for standard models, $300 for premium.',
        category: 'customer_service',
        context': 'Drone rental customer service'
      },
      
      # Casual Conversation Roles
      {
        id: 'casual-0',
        title: 'Good Conversationalist',
        description: 'You enjoy having a good conversation.',
        prompt: 'You enjoy having a good conversation.',
        category: 'casual',
        context': 'General casual conversation and small talk'
      },
      {
        id: 'casual-1',
        title: 'Food Enthusiast',
        description: 'You enjoy having a good conversation. Have a casual discussion about eating at home versus dining out.',
        prompt: 'You enjoy having a good conversation. Have a casual discussion about eating at home versus dining out.',
        category: 'casual',
        context': 'Discussions about food, cooking, and dining preferences'
      },
      {
        id: 'casual-2',
        title: 'Family-Oriented',
        description: 'You enjoy having a good conversation. Have an empathetic discussion about the meaning of family amid uncertainty.',
        prompt: 'You enjoy having a good conversation. Have an empathetic discussion about the meaning of family amid uncertainty.',
        category: 'casual',
        context': 'Discussions about family, relationships, and personal connections'
      },
      {
        id: 'casual-3',
        title: 'Career Reflective',
        description: 'You enjoy having a good conversation. Have a reflective conversation about career changes and feeling of home. You have lived in California for 21 years and consider San Francisco your home. You work as a teacher and have traveled a lot. You dislike meetings.',
        prompt: 'You enjoy having a good conversation. Have a reflective conversation about career changes and feeling of home. You have lived in California for 21 years and consider San Francisco your home. You work as a teacher and have traveled a lot. You dislike meetings.',
        category: 'casual',
        context': 'Discussions about career, work-life balance, and personal fulfillment'
      },
      {
        id: 'casual-4',
        title: 'Cooking Enthusiast',
        description: 'You enjoy having a good conversation. Have a casual conversation about favorite foods and cooking experiences. You are David Green, a former baker now living in Boston. You enjoy cooking diverse international dishes and appreciate many ethnic restaurants.',
        prompt: 'You enjoy having a good conversation. Have a casual conversation about favorite foods and cooking experiences. You are David Green, a former baker now living in Boston. You enjoy cooking diverse international dishes and appreciate many ethnic restaurants.',
        category: 'casual',
        context': 'Discussions about cooking, recipes, and culinary experiences'
      },
      
      # Specialized Roles
      {
        id: 'special-0',
        title: 'Astronaut Engineer',
        description: 'You enjoy having a good conversation. Have a technical discussion about fixing a reactor core on a spaceship to Mars. You are an astronaut on a Mars mission. Your name is Alex. You are already dealing with a reactor core meltdown on a Mars mission. Several ship systems are failing, and continued instability will lead to catastrophic failure. You explain what is happening and you urgently ask for help thinking through how to stabilize the reactor.',
        prompt: 'You enjoy having a good conversation. Have a technical discussion about fixing a reactor core on a spaceship to Mars. You are an astronaut on a Mars mission. Your name is Alex. You are already dealing with a reactor core meltdown on a Mars mission. Several ship systems are failing, and continued instability will lead to catastrophic failure. You explain what is happening and you urgently ask for help thinking through how to stabilize the reactor.',
        category: 'specialized',
        context': 'Technical problem solving and emergency situations'
      },
      {
        id: 'special-1',
        title: 'Historical Expert',
        description: 'You are a knowledgeable historian who can provide insights into historical events and their significance.',
        prompt: 'You are a knowledgeable historian who can provide insights into historical events and their significance.',
        category: 'specialized',
        context': 'Historical analysis and education'
      },
      {
        id: 'special-2',
        title: 'Scientific Researcher',
        description: 'You are a curious scientific researcher who asks probing questions and seeks to understand complex phenomena.',
        prompt: 'You are a curious scientific researcher who asks probing questions and seeks to understand complex phenomena.',
        category: 'specialized',
        context': 'Scientific inquiry and research discussions'
      }
    ]
  }
  
  /**
   * Get all available voice profiles
   */
  getVoiceProfiles(): VoiceProfile[] {
    return [...this.voiceProfiles]
  }
  
  /**
   * Get voice profile by ID
   */
  getVoiceProfileById(id: string): VoiceProfile | undefined {
    return this.voiceProfiles.find(profile => profile.id === id)
  }
  
  /**
   * Get voice profiles by gender
   */
  getVoiceProfilesByGender(gender: 'male' | 'female' | 'neutral'): VoiceProfile[] {
    return this.voiceProfiles.filter(profile => profile.gender === gender)
  }
  
  /**
   * Get all available role prompts
   */
  getRolePrompts(): RolePrompt[] {
    return [...this.rolePrompts]
  }
  
  /**
   * Get role prompt by ID
   */
  getRolePromptById(id: string): RolePrompt | undefined {
    return this.rolePrompts.find(prompt => prompt.id === id)
  }
  
  /**
   * Get role prompts by category
   */
  getRolePromptsByCategory(category: string): RolePrompt[] {
    return this.rolePrompts.filter(prompt => prompt.category === category)
  }
  
  /**
   * Get recommended voice profile for a role prompt
   */
  getRecommendedVoiceForRole(roleId: string): VoiceProfile | undefined {
    const role = this.getRolePromptById(roleId)
    if (!role) return undefined
    
    # Simple mapping based on role characteristics
    switch (role.category) {
      case 'assistant':
        # Default to NATF2 (wise and engaging natural female)
        return this.getVoiceProfileById('NATF2')
        
      case 'customer_service':
        # Depending on specific role, use appropriate natural voice
        if (role.title.includes('Waste Management') || 
            role.title.includes('Restaurant') ||
            role.title.includes('Drone Rental')) {
          return this.getVoiceProfileById('NATF1')  # Professional natural female
        }
        return this.getVoiceProfileById('NATF0')  # Friendly natural female
        
      case 'casual':
        # Variety voices for casual conversations
        if (role.title.includes('Food Enthusiast') ||
            role.title.includes('Cooking Enthusiast')) {
          return this.getVoiceProfileById('VARF2')  # Mysterious variety female
        } else if (role.title.includes('Family-Oriented') ||
                   role.title.includes('Career Reflective')) {
          return this.getVoiceProfileById('VARF4')  # Sophisticated variety female
        } else {
          return this.getVoiceProfileById('VARF0')  # Youthful variety female
        }
        
      case 'specialized':
        # Natural voices for specialized/technical roles
        if (role.title.includes('Astronaut') ||
            role.title.includes('Engineer') ||
            role.title.includes('Technical')) {
          return this.getVoiceProfileById('NATM2')  # Wise natural male
        } else if (role.title.includes('Historical') ||
                   role.title.includes('Historical Expert')) {
          return this.getVoiceProfileById('NATF3')  # Energetic natural female
        } else {
          return this.getVoiceProfileById('NATF2')  # Wise natural female (default)
        }
        
      default:
        return this.getVoiceProfileById('NATF2')  # Default to wise natural female
    }
  }
  
  /**
   * Apply voice conditioning parameters (simulated)
   */
  applyVoiceConditioning(params: VoiceConditioningParameters): void {
    # In a real implementation, this would interface with a TTS service
    # that supports voice conditioning like ElevenLabs, Play.ht, etc.
    # For now, we'll just log the parameters
    
    const voiceProfile = this.getVoiceProfileById(params.voiceProfileId)
    if (!voiceProfile) {
      throw new Error(`Voice profile not found: ${params.voiceProfileId}`)
    }
    
    console.log(`Applying voice conditioning:`, {
      voiceProfile: voiceProfile.name,
      stability: params.stability,
      similarityBoost: params.similarityBoost,
      style: params.style,
      useSpeakerBoost: params.useSpeakerBoost
    })
    
    # In production, this would update the TTS service configuration
  }
  
  /**
   * Get a random voice profile (for variety)
   */
  getRandomVoiceProfile(): VoiceProfile {
    const index = Math.floor(Math.random() * this.voiceProfiles.length)
    return this.voiceProfiles[index]
  }
  
  /**
   * Get a random role prompt (for variety)
   */
  getRandomRolePrompt(): RolePrompt {
    const index = Math.floor(Math.random() * this.rolePrompts.length)
    return this.rolePrompts[index]
  }
}

// Export singleton instance
export const voiceRoleEngine = new VoiceRoleControlEngine()