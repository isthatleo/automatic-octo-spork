'use strict'

/**
 * Agent Tools System for Nancy-billion
 * Inspired by Fury's tool support system
 */

export interface ToolInputSchema {
  type: 'object'
  properties: Record<string, {
    type: string
    description?: string
    enum?: string[]
    items?: {
      type: string
    }
    required?: string[]
  }>
  required?: string[]
}

export interface ToolOutputSchema {
  type: 'object'
  properties: Record<string, {
    type: string
    description?: string
  }>
  required?: string[]
}

export interface Tool {
  id: string
  name: string
  description: string
  execute: (...args: any[]) => Promise<any> | any
  inputSchema: ToolInputSchema
  outputSchema?: ToolOutputSchema
}

export class ToolRegistry {
  private tools: Map<string, Tool> = new Map()

  register(tool: Tool): void {
    this.tools.set(tool.id, tool)
    console.log(`Tool registered: ${tool.id}`)
  }

  unregister(toolId: string): void {
    this.tools.delete(toolId)
    console.log(`Tool unregistered: ${toolId}`)
  }

  get(toolId: string): Tool | undefined {
    return this.tools.get(toolId)
  }

  getAll(): Tool[] {
    return Array.from(this.tools.values())
  }

  has(toolId: string): boolean {
    return this.tools.has(toolId)
  }
}

// Export singleton instance
export const toolRegistry = new ToolRegistry()

/**
 * Built-in Nancy tools
 */

/**
 * File system tool (simulated for browser environment)
 */
export const fileSystemTool: Tool = {
  id: 'file_system',
  name: 'File System',
  description: 'Read, write, and manage files and directories',
  execute: async (operation: string, path: string, content?: string) => {
    // In a real implementation, this would interface with the actual file system
    // For browser environment, we'll simulate or use IndexedDB/localStorage
    
    switch (operation.toLowerCase()) {
      case 'read':
        // Simulate reading from localStorage
        const data = localStorage.getItem(`nancy-file-${path}`)
        return data ? JSON.parse(data) : null
        
      case 'write':
        // Simulate writing to localStorage
        localStorage.setItem(`nancy-file-${path}`, JSON.stringify(content))
        return { success: true, message: `File written to ${path}` }
        
      case 'list':
        // Simulate listing directory
        const files = []
        for (let i = 0; i < localStorage.length; i++) {
          const key = localStorage.key(i)
          if (key && key.startsWith('nancy-file-')) {
            files.push(key.substring(13)) // Remove 'nancy-file-' prefix
          }
        }
        return { files }
        
      case 'delete':
        localStorage.removeItem(`nancy-file-${path}`)
        return { success: true, message: `File deleted: ${path}` }
        
      default:
        throw new Error(`Unknown file operation: ${operation}`)
    }
  },
  inputSchema: {
    type: 'object',
    properties: {
      operation: {
        type: 'string',
        description: 'File operation to perform (read, write, list, delete)',
        enum: ['read', 'write', 'list', 'delete']
      },
      path: {
        type: 'string',
        description: 'File path'
      },
      content: {
        type: 'string',
        description: 'Content to write (for write operation)'
      }
    },
    required: ['operation', 'path']
  },
  outputSchema: {
    type: 'object',
    properties: {
      success: { type: 'boolean' },
      message: { type: 'string' },
      data: { type: ['string', 'object'] },
      files: { type: 'array', items: { type: 'string' } }
    }
  }
}

/**
 * Web search tool
 */
export const webSearchTool: Tool = {
  id: 'web_search',
  name: 'Web Search',
  description: 'Search the web for information',
  execute: async (query: string, numResults: number = 5) => {
    // In a real implementation, this would call a search API
    // For now, we'll return simulated results
    
    return {
      query,
      results: Array.from({ length: Math.min(numResults, 3) }, (_, i) => ({
        title: `Search result ${i+1} for "${query}"`,
        snippet: `This is a simulated search result for query "${query}". In a full implementation, this would connect to a search API like Google, Bing, or DuckDuckGo.`,
        url: `https://example.com/result/${i+1}`,
        rank: i + 1
      })),
      timestamp: Date.now()
    }
  },
  inputSchema: {
    type: 'object',
    properties: {
      query: {
        type: 'string',
        description: 'Search query'
      },
      numResults: {
        type: 'integer',
        description: 'Number of results to return (default: 5)',
        minimum: 1,
        maximum: 50
      }
    },
    required: ['query']
  },
  outputSchema: {
    type: 'object',
    properties: {
      query: { type: 'string' },
      results: {
        type: 'array',
        items: {
          type: 'object',
          properties: {
            title: { type: 'string' },
            snippet: { type: 'string' },
            url: { type: 'string' },
            rank: { type: 'integer' }
          }
        }
      },
      timestamp: { type: 'integer' }
    }
  }
}

/**
 * System information tool
 */
export const systemInfoTool: Tool = {
  id: 'system_info',
  name: 'System Information',
  description: 'Get system information and metrics',
  execute: async () => {
    return {
      platform: navigator.userAgent,
      language: navigator.language,
      online: navigator.onLine,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      viewport: {
        width: window.innerWidth,
        height: window.innerHeight
      },
      timestamp: Date.now(),
      memory: (window as any).performance?.memory ? {
        usedJSHeapSize: (window as any).performance.memory.usedJSHeapSize,
        totalJSHeapSize: (window as any).performance.memory.totalJSHeapSize,
        jsHeapSizeLimit: (window as any).performance.memory.jsHeapSizeLimit
      } : undefined
    }
  },
  inputSchema: {
    type: 'object',
    properties: {}
  },
  outputSchema: {
    type: 'object',
    properties: {
      platform: { type: 'string' },
      language: { type: 'string' },
      online: { type: 'boolean' },
      timezone: { type: 'string' },
      viewport: {
        type: 'object',
        properties: {
          width: { type: 'integer' },
          height: { type: 'integer' }
        }
      },
      timestamp: { type: 'integer' },
      memory: {
        type: 'object',
        properties: {
          usedJSHeapSize: { type: 'integer' },
          totalJSHeapSize: { type: 'integer' },
          jsHeapSizeLimit: { type: 'integer' }
        }
      }
    }
  }
}

/**
 * Calculator tool
 */
export const calculatorTool: Tool = {
  id: 'calculator',
  name: 'Calculator',
  description: 'Perform mathematical calculations',
  execute: async (expression: string) => {
    try {
      // In a production environment, use a proper math expression parser
      // For simplicity and safety, we'll use a restricted eval with whitelisted operations
      const sanitized = expression.replace(/[^0-9+\-*/().\s]/g, '')
      if (!sanitized || sanitized.trim() === '') {
        throw new Error('Invalid expression')
      }
      
      // Simple safety check - only allow basic math
      if (/[^\d+\-*/().\s]/.test(sanitized)) {
        throw new Error('Expression contains invalid characters')
      }
      
      const result = Function(`'use strict'; return (${sanitized})`)()
      return {
        expression: expression,
        result: result,
        success: true
      }
    } catch (error) {
      return {
        expression: expression,
        error: error.message,
        success: false
      }
    }
  },
  inputSchema: {
    type: 'object',
    properties: {
      expression: {
        type: 'string',
        description: 'Mathematical expression to evaluate'
      }
    },
    required: ['expression']
  },
  outputSchema: {
    type: 'object',
    properties: {
      expression: { type: 'string' },
      result: { type: ['number', 'string'] },
      error: { type: 'string' },
      success: { type: 'boolean' }
    }
  }
}

/**
 * Register all built-in tools
 */
export function registerBuiltInTools(): void {
  toolRegistry.register(fileSystemTool)
  toolRegistry.register(webSearchTool)
  toolRegistry.register(systemInfoTool)
  toolRegistry.register(calculatorTool)
  
  console.log('Built-in Nancy tools registered')
}