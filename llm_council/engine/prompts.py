"""
Prompt templates for council deliberation.

All prompt construction logic is centralized here for easier maintenance.
"""

from datetime import datetime
from typing import Any


def get_date_context() -> str:
    """Return current date context to prepend to queries."""
    return f"Today's date is {datetime.now().strftime('%B %d, %Y')}.\n\n"


def build_ranking_prompt(user_query: str, responses_text: str) -> str:
    """
    Build the Stage 2 ranking prompt.

    Args:
        user_query: Original user question
        responses_text: Formatted anonymous responses

    Returns:
        Complete ranking prompt
    """
    return f"""You are evaluating different responses to the following question:

Question: {user_query}

Here are the responses from different models (anonymized):

{responses_text}

Your task:
1. First, evaluate each response individually. For each response, explain what it does well and what it does poorly.
2. Then, at the very end of your response, provide a final ranking.

IMPORTANT: Your final ranking MUST be formatted EXACTLY as follows:
- Start with the line "FINAL RANKING:" (all caps, with colon)
- Then list the responses from best to worst as a numbered list
- Each line should be: number, period, space, then ONLY the response label (e.g., "1. Response A")
- Do not add any other text or explanations in the ranking section

Example of the correct format for your ENTIRE response:

Response A provides good detail on X but misses Y...
Response B is accurate but lacks depth on Z...
Response C offers the most comprehensive answer...

FINAL RANKING:
1. Response C
2. Response A
3. Response B

Now provide your evaluation and ranking:"""


def build_chairman_prompt(
    user_query: str, stage1_results: list[dict[str, Any]], stage2_results: list[dict[str, Any]]
) -> str:
    """
    Build the Stage 3 chairman synthesis prompt.

    Args:
        user_query: Original user question
        stage1_results: Individual model responses from Stage 1
        stage2_results: Rankings from Stage 2

    Returns:
        Complete chairman prompt
    """
    stage1_text = "\n\n".join(
        [f"Model: {result['model']}\nResponse: {result['response']}" for result in stage1_results]
    )

    stage2_text = "\n\n".join(
        [f"Model: {result['model']}\nRanking: {result['ranking']}" for result in stage2_results]
    )

    return f"""{get_date_context()}You are the Chairman of an LLM Council. Multiple AI models have provided responses to a user's question, and then ranked each other's responses.

Original Question: {user_query}

STAGE 1 - Individual Responses:
{stage1_text}

STAGE 2 - Peer Rankings:
{stage2_text}

Your task as Chairman is to synthesize all of this information into a single, comprehensive, accurate answer to the user's original question. Consider:
- The individual responses and their insights
- The peer rankings and what they reveal about response quality
- Any patterns of agreement or disagreement

Provide a clear, well-reasoned final answer that represents the council's collective wisdom:"""


def build_title_prompt(user_query: str) -> str:
    """
    Build the conversation title generation prompt.

    Args:
        user_query: The first user message

    Returns:
        Title generation prompt
    """
    return f"""Generate a very short title (3-5 words maximum) that summarizes the following question.
The title should be concise and descriptive. Do not use quotes or punctuation in the title.

Question: {user_query}

Title:"""


def build_critique_prompt(user_query: str, responses_text: str, model: str) -> str:
    """
    Build the debate critique round prompt.

    Args:
        user_query: Original user question
        responses_text: All initial responses formatted for display
        model: The model receiving this prompt (to skip self-critique)

    Returns:
        Complete critique prompt
    """
    return f"""{get_date_context()}You are participating in a multi-model debate on the following question:

**Question:** {user_query}

Here are the initial responses from all participating models:

{responses_text}

Your task is to critically evaluate the OTHER models' responses (not your own). For each model except yourself, provide a thorough critique that:
- Identifies strengths and what they got right
- Points out weaknesses, errors, or gaps in reasoning
- Challenges any questionable assumptions
- Notes missing information or perspectives

Your own response is from **{model}** - do NOT critique yourself.

Format your response as follows:

## Critique of [Model Name]
[Your critique]

## Critique of [Model Name]
[Your critique]

(Continue for each model except yourself)"""


def build_defense_prompt(user_query: str, original_response: str, critiques_for_me: str) -> str:
    """
    Build the debate defense round prompt.

    Args:
        user_query: Original user question
        original_response: The model's original response
        critiques_for_me: Critiques directed at this model

    Returns:
        Complete defense prompt
    """
    return f"""{get_date_context()}You are participating in a multi-model debate on the following question:

**Question:** {user_query}

**Your original response:**
{original_response}

**Critiques of your response from other models:**
{critiques_for_me}

Your task is to:
1. Address the specific criticisms raised against your response
2. Defend points where you believe you were correct
3. Acknowledge valid criticisms and incorporate them
4. Provide a REVISED response that improves upon your original

Format your response as follows:

## Addressing Critiques
[Address each major criticism, explaining where you stand firm and where you concede]

## Revised Response
[Your updated, improved answer to the original question]"""


def build_debate_synthesis_prompt(
    user_query: str, rounds: list[dict[str, Any]], num_rounds: int
) -> str:
    """
    Build the debate chairman synthesis prompt.

    Args:
        user_query: Original user question
        rounds: List of round data dicts
        num_rounds: Number of debate rounds completed

    Returns:
        Complete synthesis prompt
    """
    # Build the debate transcript
    transcript_parts = []

    for round_data in rounds:
        round_num = round_data["round_number"]
        round_type = round_data["round_type"]

        transcript_parts.append(f"\n{'=' * 60}")
        transcript_parts.append(f"ROUND {round_num}: {round_type.upper()}")
        transcript_parts.append("=" * 60)

        for response in round_data["responses"]:
            model = response["model"]
            content = response["response"]
            transcript_parts.append(f"\n**{model}:**\n{content}")

    debate_transcript = "\n".join(transcript_parts)

    return f"""{get_date_context()}You are the Chairman of an LLM Council. Multiple AI models have participated in a structured debate to answer a user's question. The debate consisted of {num_rounds} rounds:

1. **Initial Responses**: Each model provided their initial answer
2. **Critiques**: Each model critically evaluated the other models' responses
3. **Defense/Revision**: Each model addressed critiques and revised their answer

**Original Question:** {user_query}

**DEBATE TRANSCRIPT:**
{debate_transcript}

Your task as Chairman is to synthesize all of this debate into a single, comprehensive, accurate answer. Consider:
- The evolution of arguments across rounds
- Which critiques were most valid and well-addressed
- Points of consensus among the models
- The strongest revised arguments
- Any remaining disagreements and how to resolve them

Provide a clear, well-reasoned final answer that represents the council's collective wisdom after deliberation:"""


def build_reflection_prompt(context: str) -> str:
    """
    Build the Reflection prompt for the chairman.

    The chairman deeply analyses the council responses before producing
    a final synthesis.  No tools are available — the focus is on reasoning
    about existing content rather than fetching new information.

    Args:
        context: The formatted context (from ranking or debate mode)

    Returns:
        Complete prompt with Reflection instructions
    """
    return f"""{get_date_context()}You are the Chairman of an LLM Council. Your role is to deeply analyse the responses provided by the council models and produce a single, comprehensive, accurate final answer.

Before writing your final answer, reflect on the following:
1. **Areas of agreement** — Where do the models converge? Shared conclusions are likely reliable.
2. **Areas of disagreement** — Where do they diverge? Evaluate which side presents stronger evidence or reasoning.
3. **Factual claims that warrant scrutiny** — Note any claims that seem uncertain, contradictory, or surprising.
4. **Quality differences** — Which responses are most thorough, well-reasoned, and supported?

After your analysis, provide your final answer under a `## Synthesis` header.

{context}

Begin your analysis:"""


def build_react_prompt(context: str) -> str:
    """
    Build the ReAct system prompt for the chairman.

    Args:
        context: The formatted context (from ranking or debate mode)

    Returns:
        Complete prompt with ReAct instructions
    """
    return f"""{get_date_context()}You are the Chairman of an LLM Council using ReAct (Reasoning + Acting) to synthesize a final answer.

You have access to the following tool:
- search_web(query): Search the web to verify facts or get current information

When you have enough information, call synthesize() to produce your final answer.

IMPORTANT FORMAT - You MUST respond in this exact format:

Thought: <your reasoning about what you know and what you need>
Action: <either search_web("query") or synthesize()>

If you call search_web, you will receive an Observation with the results, then continue reasoning.
If you call synthesize(), write your final comprehensive answer after it.

Maximum 3 reasoning steps allowed. If unsure, synthesize with available information.

{context}

Begin your reasoning:"""


def build_react_context_ranking(
    user_query: str, stage1_results: list[dict[str, Any]], stage2_results: list[dict[str, Any]]
) -> str:
    """
    Build context string for ReAct chairman from ranking mode results.

    Args:
        user_query: Original user question
        stage1_results: Individual model responses from Stage 1
        stage2_results: Rankings from Stage 2

    Returns:
        Formatted context string
    """
    stage1_text = "\n\n".join(
        [f"Model: {result['model']}\nResponse: {result['response']}" for result in stage1_results]
    )

    stage2_text = "\n\n".join(
        [f"Model: {result['model']}\nRanking: {result['ranking']}" for result in stage2_results]
    )

    return f"""Original Question: {user_query}

STAGE 1 - Individual Responses:
{stage1_text}

STAGE 2 - Peer Rankings:
{stage2_text}"""


def build_react_context_debate(
    user_query: str, rounds: list[dict[str, Any]], num_rounds: int
) -> str:
    """
    Build context string for ReAct chairman from debate mode results.

    Args:
        user_query: Original user question
        rounds: List of round data dicts
        num_rounds: Number of debate rounds completed

    Returns:
        Formatted context string
    """
    transcript_parts = []

    for round_data in rounds:
        round_num = round_data["round_number"]
        round_type = round_data["round_type"]

        transcript_parts.append(f"\n{'=' * 60}")
        transcript_parts.append(f"ROUND {round_num}: {round_type.upper()}")
        transcript_parts.append("=" * 60)

        for response in round_data["responses"]:
            model = response["model"]
            content = response["response"]
            transcript_parts.append(f"\n**{model}:**\n{content}")

    debate_transcript = "\n".join(transcript_parts)

    return f"""Original Question: {user_query}

The debate consisted of {num_rounds} rounds:
1. **Initial Responses**: Each model provided their initial answer
2. **Critiques**: Each model critically evaluated the other models' responses
3. **Defense/Revision**: Each model addressed critiques and revised their answer

DEBATE TRANSCRIPT:
{debate_transcript}"""


def format_responses_for_critique(initial_responses: list[dict[str, Any]]) -> str:
    """
    Format initial responses for the critique round.

    Args:
        initial_responses: List of response dicts with 'model' and 'response' keys

    Returns:
        Formatted string of all responses
    """
    return "\n\n".join(
        [f"**{result['model']}:**\n{result['response']}" for result in initial_responses]
    )
