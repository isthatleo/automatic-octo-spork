    # =============================================================================
    # Learning & Knowledge Synthesis Tools
    # =============================================================================

    add_tool(
        "cross_domain_reasoning",
        "Synthesize knowledge from disparate fields to solve complex problems through cross-domain reasoning.",
        cross_domain_reasoning_execute,
        {
            "type": "object",
            "properties": {
                "domain1": {"type": "string", "description": "First domain of knowledge (e.g., 'neuroscience', 'physics')", "default": ""},
                "domain2": {"type": "string", "description": "Second domain of knowledge (e.g., 'machine_learning', 'psychology')", "default": ""},
                "problem_statement": {"type": "string", "description": "Problem to solve using cross-domain insights", "default": ""}
            },
            "required": []
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "Cross-domain reasoning analysis in JSON format"}
            },
            "required": ["result"]
        }
    )
    
    add_tool(
        "hypothesis_generation",
        "Generate and test hypotheses based on available data and observations.",
        hypothesis_generation_execute,
        {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Domain or field of study (e.g., 'climate_science', 'finance')", "default": ""},
                "observation_data": {"type": "string", "description": "Observed data or phenomena to explain", "default": ""},
                "num_hypotheses": {"type": "integer", "description": "Number of hypotheses to generate (default: 3)", "default": 3}
            },
            "required": []
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "Generated hypotheses with evidence and testability in JSON format"}
            },
            "required": ["result"]
        }
    )
    
    add_tool(
        "invention_engine",
        "Generate novel solutions and approaches to problems using inventive thinking methods.",
        invention_engine_execute,
        {
            "type": "object",
            "properties": {
                "problem_domain": {"type": "string", "description": "Domain or area where invention is needed (e.g., 'sustainable_energy', 'healthcare')", "default": ""},
                "constraints": {"type": "string", "description": "Constraints to consider (cost, materials, time, etc.)", "default": ""},
                "goals": {"type": "string", "description": "Goals or objectives for the invention (efficiency, sustainability, etc.)", "default": ""}
            },
            "required": []
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "Generated inventions with novelty, feasibility, and impact scores in JSON format"}
            },
            "required": ["result"]
        }
    )
    
    add_tool(
        "wisdom_distillation",
        "Extract principles and wisdom from experiences, not just facts, through reflective analysis.",
        wisdom_distillation_experience,
        {
            "type": "object",
            "properties": {
                "experience_description": {"type": "string", "description": "Description of the experience to analyze", "default": ""},
                "context": {"type": "string", "description": "Context or circumstances surrounding the experience", "default": ""},
                "timeframe": {"type": "string", "description": "Time period or duration of the experience", "default": ""}
            },
            "required": []
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "Extracted wisdom principles and insights in JSON format"}
            },
            "required": ["result"]
        }
    )