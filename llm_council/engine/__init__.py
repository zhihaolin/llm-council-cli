"""
Council deliberation package.

This package provides the core logic for LLM council deliberation,
including both ranking mode and debate mode.

Public API:
    - Orchestration: run_full_council, stage1_collect_responses, stage2_collect_rankings,
                     generate_conversation_title
    - Debate: ExecuteRound, RoundConfig, build_round_config,
              run_debate, debate_round_parallel, debate_round_streaming
    - Reflection: synthesize_with_reflection, parse_reflection_output
    - Council ReAct: council_react_loop
    - Chairman context: build_chairman_context_ranking,
                        build_chairman_context_debate
    - Parsing: parse_ranking_from_text, parse_revised_answer, extract_critiques_for_model,
               parse_react_output
    - Aggregation: calculate_aggregate_rankings
    - Utilities: execute_tool, get_date_context
"""

# Aggregation
from .aggregation import calculate_aggregate_rankings

# Debate mode (RoundConfig, async strategies, and orchestration)
from .debate import (
    ExecuteRound,
    RoundConfig,
    build_round_config,
    debate_round_parallel,
    debate_round_streaming,
    run_debate,
)

# Parsers
from .parsers import (
    extract_critiques_for_model,
    parse_ranking_from_text,
    parse_react_output,
    parse_reflection_output,
    parse_revised_answer,
)

# Prompts (for building chairman context)
from .prompts import (
    build_chairman_context_debate,
    build_chairman_context_ranking,
    get_date_context,
)
from .ranking import (
    execute_tool,
    generate_conversation_title,
    run_full_council,
    stage1_collect_responses,
    stage2_collect_rankings,
)

# Council member ReAct loop
from .react import council_react_loop

# Reflection chairman
from .reflection import synthesize_with_reflection

__all__ = [
    # Orchestrator
    "execute_tool",
    "stage1_collect_responses",
    "stage2_collect_rankings",
    "run_full_council",
    "generate_conversation_title",
    # Debate
    "ExecuteRound",
    "RoundConfig",
    "build_round_config",
    "debate_round_parallel",
    "debate_round_streaming",
    "run_debate",
    # Council ReAct
    "council_react_loop",
    # Reflection
    "synthesize_with_reflection",
    "parse_reflection_output",
    # Parsers
    "parse_ranking_from_text",
    "parse_revised_answer",
    "extract_critiques_for_model",
    "parse_react_output",
    # Aggregation
    "calculate_aggregate_rankings",
    # Prompts
    "get_date_context",
    "build_chairman_context_ranking",
    "build_chairman_context_debate",
]
