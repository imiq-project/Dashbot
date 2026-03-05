"""
Package exports for LLM prompt templates. Exposes prompt builders and validators for all agents.
"""

from .router_prompts import (
    ROUTER_SYSTEM_PROMPT,
    ROUTER_OUTPUT_SCHEMA,
    FEW_SHOT_EXAMPLES,
    build_router_prompt,
    validate_router_output
)

from .neo4j_prompts import (
    NEO4J_SYSTEM_PROMPT,
    NEO4J_OUTPUT_SCHEMA,
    NEO4J_FUNCTIONS,
    NEO4J_FEW_SHOT_EXAMPLES,
    build_neo4j_prompt,
    validate_neo4j_output
)

from .fiware_prompts import (
    FIWARE_SYSTEM_PROMPT,
    FIWARE_OUTPUT_SCHEMA,
    FIWARE_ENTITY_TYPES,
    FIWARE_FEW_SHOT_EXAMPLES,
    build_fiware_prompt,
    validate_fiware_output
)

from .synthesizer_prompts import (
    SYNTHESIZER_SYSTEM_PROMPT,
    SYNTHESIZER_FEW_SHOT_EXAMPLES,
    build_synthesizer_prompt,
    validate_synthesizer_output
)

from .dialogue_prompts import (
    DIALOGUE_SYSTEM_PROMPT,
    DIALOGUE_USER_TEMPLATE,
    build_dialogue_prompt
)

__all__ = [
    "ROUTER_SYSTEM_PROMPT",
    "ROUTER_OUTPUT_SCHEMA",
    "FEW_SHOT_EXAMPLES",
    "build_router_prompt",
    "validate_router_output",
    "NEO4J_SYSTEM_PROMPT",
    "NEO4J_OUTPUT_SCHEMA",
    "NEO4J_FUNCTIONS",
    "NEO4J_FEW_SHOT_EXAMPLES",
    "build_neo4j_prompt",
    "validate_neo4j_output",
    "FIWARE_SYSTEM_PROMPT",
    "FIWARE_OUTPUT_SCHEMA",
    "FIWARE_ENTITY_TYPES",
    "FIWARE_FEW_SHOT_EXAMPLES",
    "build_fiware_prompt",
    "validate_fiware_output",
    "SYNTHESIZER_SYSTEM_PROMPT",
    "SYNTHESIZER_FEW_SHOT_EXAMPLES",
    "build_synthesizer_prompt",
    "validate_synthesizer_output",
    "DIALOGUE_SYSTEM_PROMPT",
    "DIALOGUE_USER_TEMPLATE",
    "build_dialogue_prompt"
]
