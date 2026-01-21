"""
Council deliberation package.

This package provides the core logic for LLM council deliberation,
including both ranking mode and debate mode.

Public API:
    - Orchestration: run_full_council, stage1_collect_responses, stage2_collect_rankings,
                     stage3_synthesize_final, generate_conversation_title
    - Debate: run_debate_council, debate_round_critique, debate_round_defense,
              synthesize_debate
    - Streaming: debate_round_streaming, run_debate_council_streaming,
                 run_debate_token_streaming
    - ReAct: synthesize_with_react, build_react_context_ranking, build_react_context_debate
    - Parsing: parse_ranking_from_text, parse_revised_answer, extract_critiques_for_model,
               parse_react_output
    - Aggregation: calculate_aggregate_rankings
    - Utilities: execute_tool, get_date_context
"""

# Orchestrator - Stage 1-2-3 flow
from .orchestrator import (
    execute_tool,
    stage1_collect_responses,
    stage2_collect_rankings,
    stage3_synthesize_final,
    run_full_council,
    generate_conversation_title,
)

# Debate mode
from .debate import (
    debate_round_initial,
    debate_round_critique,
    debate_round_defense,
    synthesize_debate,
    run_debate_council,
)

# Streaming
from .streaming import (
    debate_round_streaming,
    run_debate_council_streaming,
    run_debate_token_streaming,
)

# ReAct chairman
from .react import synthesize_with_react

# Parsers
from .parsers import (
    parse_ranking_from_text,
    parse_revised_answer,
    extract_critiques_for_model,
    parse_react_output,
)

# Aggregation
from .aggregation import calculate_aggregate_rankings

# Prompts (for building context)
from .prompts import (
    get_date_context,
    build_react_context_ranking,
    build_react_context_debate,
    build_react_prompt,
)

__all__ = [
    # Orchestrator
    "execute_tool",
    "stage1_collect_responses",
    "stage2_collect_rankings",
    "stage3_synthesize_final",
    "run_full_council",
    "generate_conversation_title",
    # Debate
    "debate_round_initial",
    "debate_round_critique",
    "debate_round_defense",
    "synthesize_debate",
    "run_debate_council",
    # Streaming
    "debate_round_streaming",
    "run_debate_council_streaming",
    "run_debate_token_streaming",
    # ReAct
    "synthesize_with_react",
    # Parsers
    "parse_ranking_from_text",
    "parse_revised_answer",
    "extract_critiques_for_model",
    "parse_react_output",
    # Aggregation
    "calculate_aggregate_rankings",
    # Prompts
    "get_date_context",
    "build_react_context_ranking",
    "build_react_context_debate",
    "build_react_prompt",
]
