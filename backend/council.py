"""3-stage LLM Council orchestration."""

import asyncio
from typing import List, Dict, Any, Tuple
from .openrouter import query_models_parallel, query_model, query_model_with_tools
from .config import COUNCIL_MODELS, CHAIRMAN_MODEL
from .search import SEARCH_TOOL, search_web, format_search_results


async def execute_tool(tool_name: str, tool_args: Dict[str, Any]) -> str:
    """
    Execute a tool and return the result as a string.

    Args:
        tool_name: Name of the tool to execute
        tool_args: Arguments to pass to the tool

    Returns:
        String result of tool execution
    """
    if tool_name == "search_web":
        query = tool_args.get("query", "")
        search_response = await search_web(query)
        return format_search_results(search_response)
    else:
        return f"Unknown tool: {tool_name}"


async def stage1_collect_responses(user_query: str) -> List[Dict[str, Any]]:
    """
    Stage 1: Collect individual responses from all council models.

    Models have access to web search tool and can decide when to use it.

    Args:
        user_query: The user's question

    Returns:
        List of dicts with 'model', 'response', and optionally 'tool_calls_made' keys
    """
    messages = [{"role": "user", "content": user_query}]
    tools = [SEARCH_TOOL]

    # Query all models in parallel with tool support
    async def query_single_model(model: str) -> tuple:
        response = await query_model_with_tools(
            model=model,
            messages=messages,
            tools=tools,
            tool_executor=execute_tool
        )
        return model, response

    # Create tasks for all models
    tasks = [query_single_model(model) for model in COUNCIL_MODELS]
    results = await asyncio.gather(*tasks)

    # Format results
    stage1_results = []
    for model, response in results:
        if response is not None:  # Only include successful responses
            result = {
                "model": model,
                "response": response.get('content', '')
            }
            # Include tool calls info if any were made
            if response.get('tool_calls_made'):
                result['tool_calls_made'] = response['tool_calls_made']
            stage1_results.append(result)

    return stage1_results


async def stage2_collect_rankings(
    user_query: str,
    stage1_results: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """
    Stage 2: Each model ranks the anonymized responses.

    Args:
        user_query: The original user query
        stage1_results: Results from Stage 1

    Returns:
        Tuple of (rankings list, label_to_model mapping)
    """
    # Create anonymized labels for responses (Response A, Response B, etc.)
    labels = [chr(65 + i) for i in range(len(stage1_results))]  # A, B, C, ...

    # Create mapping from label to model name
    label_to_model = {
        f"Response {label}": result['model']
        for label, result in zip(labels, stage1_results)
    }

    # Build the ranking prompt
    responses_text = "\n\n".join([
        f"Response {label}:\n{result['response']}"
        for label, result in zip(labels, stage1_results)
    ])

    ranking_prompt = f"""You are evaluating different responses to the following question:

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

    messages = [{"role": "user", "content": ranking_prompt}]

    # Get rankings from all council models in parallel
    responses = await query_models_parallel(COUNCIL_MODELS, messages)

    # Format results
    stage2_results = []
    for model, response in responses.items():
        if response is not None:
            full_text = response.get('content', '')
            parsed = parse_ranking_from_text(full_text)
            stage2_results.append({
                "model": model,
                "ranking": full_text,
                "parsed_ranking": parsed
            })

    return stage2_results, label_to_model


async def stage3_synthesize_final(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Stage 3: Chairman synthesizes final response.

    Args:
        user_query: The original user query
        stage1_results: Individual model responses from Stage 1
        stage2_results: Rankings from Stage 2

    Returns:
        Dict with 'model' and 'response' keys
    """
    # Build comprehensive context for chairman
    stage1_text = "\n\n".join([
        f"Model: {result['model']}\nResponse: {result['response']}"
        for result in stage1_results
    ])

    stage2_text = "\n\n".join([
        f"Model: {result['model']}\nRanking: {result['ranking']}"
        for result in stage2_results
    ])

    chairman_prompt = f"""You are the Chairman of an LLM Council. Multiple AI models have provided responses to a user's question, and then ranked each other's responses.

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

    messages = [{"role": "user", "content": chairman_prompt}]

    # Query the chairman model
    response = await query_model(CHAIRMAN_MODEL, messages)

    if response is None:
        # Fallback if chairman fails
        return {
            "model": CHAIRMAN_MODEL,
            "response": "Error: Unable to generate final synthesis."
        }

    return {
        "model": CHAIRMAN_MODEL,
        "response": response.get('content', '')
    }


def parse_ranking_from_text(ranking_text: str) -> List[str]:
    """
    Parse the FINAL RANKING section from the model's response.

    Args:
        ranking_text: The full text response from the model

    Returns:
        List of response labels in ranked order
    """
    import re

    # Look for "FINAL RANKING:" section
    if "FINAL RANKING:" in ranking_text:
        # Extract everything after "FINAL RANKING:"
        parts = ranking_text.split("FINAL RANKING:")
        if len(parts) >= 2:
            ranking_section = parts[1]
            # Try to extract numbered list format (e.g., "1. Response A")
            # This pattern looks for: number, period, optional space, "Response X"
            numbered_matches = re.findall(r'\d+\.\s*Response [A-Z]', ranking_section)
            if numbered_matches:
                # Extract just the "Response X" part
                return [re.search(r'Response [A-Z]', m).group() for m in numbered_matches]

            # Fallback: Extract all "Response X" patterns in order
            matches = re.findall(r'Response [A-Z]', ranking_section)
            return matches

    # Fallback: try to find any "Response X" patterns in order
    matches = re.findall(r'Response [A-Z]', ranking_text)
    return matches


def calculate_aggregate_rankings(
    stage2_results: List[Dict[str, Any]],
    label_to_model: Dict[str, str]
) -> List[Dict[str, Any]]:
    """
    Calculate aggregate rankings across all models.

    Args:
        stage2_results: Rankings from each model
        label_to_model: Mapping from anonymous labels to model names

    Returns:
        List of dicts with model name and average rank, sorted best to worst
    """
    from collections import defaultdict

    # Track positions for each model
    model_positions = defaultdict(list)

    for ranking in stage2_results:
        ranking_text = ranking['ranking']

        # Parse the ranking from the structured format
        parsed_ranking = parse_ranking_from_text(ranking_text)

        for position, label in enumerate(parsed_ranking, start=1):
            if label in label_to_model:
                model_name = label_to_model[label]
                model_positions[model_name].append(position)

    # Calculate average position for each model
    aggregate = []
    for model, positions in model_positions.items():
        if positions:
            avg_rank = sum(positions) / len(positions)
            aggregate.append({
                "model": model,
                "average_rank": round(avg_rank, 2),
                "rankings_count": len(positions)
            })

    # Sort by average rank (lower is better)
    aggregate.sort(key=lambda x: x['average_rank'])

    return aggregate


async def generate_conversation_title(user_query: str) -> str:
    """
    Generate a short title for a conversation based on the first user message.

    Args:
        user_query: The first user message

    Returns:
        A short title (3-5 words)
    """
    title_prompt = f"""Generate a very short title (3-5 words maximum) that summarizes the following question.
The title should be concise and descriptive. Do not use quotes or punctuation in the title.

Question: {user_query}

Title:"""

    messages = [{"role": "user", "content": title_prompt}]

    # Use gemini-2.5-flash for title generation (fast and cheap)
    response = await query_model("google/gemini-2.5-flash", messages, timeout=30.0)

    if response is None:
        # Fallback to a generic title
        return "New Conversation"

    title = response.get('content', 'New Conversation').strip()

    # Clean up the title - remove quotes, limit length
    title = title.strip('"\'')

    # Truncate if too long
    if len(title) > 50:
        title = title[:47] + "..."

    return title


async def run_full_council(user_query: str) -> Tuple[List, List, Dict, Dict]:
    """
    Run the complete 3-stage council process.

    Args:
        user_query: The user's question

    Returns:
        Tuple of (stage1_results, stage2_results, stage3_result, metadata)
    """
    # Stage 1: Collect individual responses
    stage1_results = await stage1_collect_responses(user_query)

    # If no models responded successfully, return error
    if not stage1_results:
        return [], [], {
            "model": "error",
            "response": "All models failed to respond. Please try again."
        }, {}

    # Stage 2: Collect rankings
    stage2_results, label_to_model = await stage2_collect_rankings(user_query, stage1_results)

    # Calculate aggregate rankings
    aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)

    # Stage 3: Synthesize final answer
    stage3_result = await stage3_synthesize_final(
        user_query,
        stage1_results,
        stage2_results
    )

    # Prepare metadata
    metadata = {
        "label_to_model": label_to_model,
        "aggregate_rankings": aggregate_rankings
    }

    return stage1_results, stage2_results, stage3_result, metadata


# ============================================================================
# DEBATE MODE FUNCTIONS
# ============================================================================


async def debate_round_critique(
    user_query: str,
    initial_responses: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Debate Round 2: Each model critiques all other models' responses.

    Args:
        user_query: The original user query
        initial_responses: Results from round 1 (initial answers)

    Returns:
        List of dicts with 'model' and 'response' containing critiques
    """
    # Build the list of all responses for critique
    responses_text = "\n\n".join([
        f"**{result['model']}:**\n{result['response']}"
        for result in initial_responses
    ])

    async def get_critique(model: str, own_response: str) -> Tuple[str, Dict]:
        """Get critique from a single model."""
        critique_prompt = f"""You are participating in a multi-model debate on the following question:

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

        messages = [{"role": "user", "content": critique_prompt}]
        response = await query_model(model, messages)
        return model, response

    # Query all models in parallel
    tasks = [
        get_critique(result['model'], result['response'])
        for result in initial_responses
    ]
    results = await asyncio.gather(*tasks)

    # Format results
    critique_results = []
    for model, response in results:
        if response is not None:
            critique_results.append({
                "model": model,
                "response": response.get('content', '')
            })

    return critique_results


def extract_critiques_for_model(
    target_model: str,
    critique_responses: List[Dict[str, Any]]
) -> str:
    """
    Extract all critiques directed at a specific model.

    Args:
        target_model: The model whose critiques we want to extract
        critique_responses: All critique responses from round 2

    Returns:
        Concatenated string of all critiques for the target model
    """
    import re

    critiques = []
    # Get just the model name without provider prefix for matching
    target_name = target_model.split('/')[-1].lower()

    for response in critique_responses:
        critic_model = response['model']
        # Skip self-critiques (shouldn't exist, but just in case)
        if critic_model == target_model:
            continue

        content = response['response']

        # Try to extract the section about this model
        # Look for "## Critique of [model]" pattern
        pattern = rf"##\s*Critique of\s*[^\n]*{re.escape(target_name)}[^\n]*\n(.*?)(?=##\s*Critique of|\Z)"
        matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)

        if matches:
            critique_text = matches[0].strip()
            critiques.append(f"**From {critic_model}:**\n{critique_text}")
        else:
            # Fallback: try matching just the model name in header
            pattern_simple = rf"##[^\n]*{re.escape(target_name)}[^\n]*\n(.*?)(?=##|\Z)"
            matches_simple = re.findall(pattern_simple, content, re.IGNORECASE | re.DOTALL)
            if matches_simple:
                critique_text = matches_simple[0].strip()
                critiques.append(f"**From {critic_model}:**\n{critique_text}")

    if not critiques:
        return "(No specific critiques were extracted for this model)"

    return "\n\n".join(critiques)


async def debate_round_defense(
    user_query: str,
    initial_responses: List[Dict[str, Any]],
    critique_responses: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Debate Round 3+: Each model defends/revises based on critiques received.

    Args:
        user_query: The original user query
        initial_responses: Results from round 1
        critique_responses: Critiques from round 2

    Returns:
        List of dicts with 'model', 'response', and 'revised_answer' keys
    """
    async def get_defense(model: str, original_response: str) -> Tuple[str, Dict]:
        """Get defense/revision from a single model."""
        # Extract critiques specifically directed at this model
        critiques_for_me = extract_critiques_for_model(model, critique_responses)

        defense_prompt = f"""You are participating in a multi-model debate on the following question:

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

        messages = [{"role": "user", "content": defense_prompt}]
        response = await query_model(model, messages)
        return model, response

    # Get the original response for each model
    model_to_response = {r['model']: r['response'] for r in initial_responses}

    # Query all models in parallel
    tasks = [
        get_defense(result['model'], model_to_response[result['model']])
        for result in initial_responses
        if result['model'] in model_to_response
    ]
    results = await asyncio.gather(*tasks)

    # Format results
    defense_results = []
    for model, response in results:
        if response is not None:
            content = response.get('content', '')
            defense_results.append({
                "model": model,
                "response": content,
                "revised_answer": parse_revised_answer(content)
            })

    return defense_results


def parse_revised_answer(defense_response: str) -> str:
    """
    Extract the 'Revised Response' section from a defense response.

    Args:
        defense_response: Full defense text

    Returns:
        The revised answer text, or full response if section not found
    """
    import re

    # Look for "## Revised Response" section
    pattern = r"##\s*Revised Response\s*\n(.*)"
    match = re.search(pattern, defense_response, re.IGNORECASE | re.DOTALL)

    if match:
        return match.group(1).strip()

    # Fallback: return the full response
    return defense_response


async def synthesize_debate(
    user_query: str,
    rounds: List[Dict[str, Any]],
    num_rounds: int
) -> Dict[str, Any]:
    """
    Chairman synthesizes based on the full debate transcript.

    Args:
        user_query: The original user query
        rounds: List of round data dicts
        num_rounds: Number of debate rounds completed

    Returns:
        Dict with 'model' and 'response' keys
    """
    # Build the debate transcript
    transcript_parts = []

    for round_data in rounds:
        round_num = round_data['round_number']
        round_type = round_data['round_type']

        transcript_parts.append(f"\n{'='*60}")
        transcript_parts.append(f"ROUND {round_num}: {round_type.upper()}")
        transcript_parts.append('='*60)

        for response in round_data['responses']:
            model = response['model']
            content = response['response']
            transcript_parts.append(f"\n**{model}:**\n{content}")

    debate_transcript = "\n".join(transcript_parts)

    chairman_prompt = f"""You are the Chairman of an LLM Council. Multiple AI models have participated in a structured debate to answer a user's question. The debate consisted of {num_rounds} rounds:

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

    messages = [{"role": "user", "content": chairman_prompt}]

    # Query the chairman model
    response = await query_model(CHAIRMAN_MODEL, messages)

    if response is None:
        return {
            "model": CHAIRMAN_MODEL,
            "response": "Error: Unable to generate debate synthesis."
        }

    return {
        "model": CHAIRMAN_MODEL,
        "response": response.get('content', '')
    }


async def run_debate_council(
    user_query: str,
    max_rounds: int = 2
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Orchestrate the complete debate flow.

    Args:
        user_query: The user's question
        max_rounds: Number of debate rounds (2 = initial + critique + defense)

    Returns:
        Tuple of (rounds list, synthesis result)
        Each round is: {round_number, round_type, responses}
    """
    rounds = []

    # Round 1: Initial responses (reuse stage1 function)
    initial_responses = await stage1_collect_responses(user_query)

    if len(initial_responses) < 2:
        # Not enough models to have a debate
        return [], {
            "model": "error",
            "response": "Not enough models responded to conduct a debate. Need at least 2 models."
        }

    rounds.append({
        "round_number": 1,
        "round_type": "initial",
        "responses": initial_responses
    })

    # Round 2: Critiques
    critique_responses = await debate_round_critique(user_query, initial_responses)

    if len(critique_responses) < 2:
        # Continue with partial results
        pass

    rounds.append({
        "round_number": 2,
        "round_type": "critique",
        "responses": critique_responses
    })

    # Round 3: Defense/Revision
    defense_responses = await debate_round_defense(
        user_query,
        initial_responses,
        critique_responses
    )

    rounds.append({
        "round_number": 3,
        "round_type": "defense",
        "responses": defense_responses
    })

    # Additional rounds if requested (alternating critique/defense)
    current_responses = defense_responses
    for round_num in range(4, max_rounds + 2):  # +2 because max_rounds=2 means 3 actual rounds
        if round_num % 2 == 0:
            # Even rounds: critique
            critique_responses = await debate_round_critique(user_query, current_responses)
            rounds.append({
                "round_number": round_num,
                "round_type": "critique",
                "responses": critique_responses
            })
        else:
            # Odd rounds: defense
            defense_responses = await debate_round_defense(
                user_query,
                current_responses,
                critique_responses
            )
            rounds.append({
                "round_number": round_num,
                "round_type": "defense",
                "responses": defense_responses
            })
            current_responses = defense_responses

    # Chairman synthesis
    synthesis = await synthesize_debate(user_query, rounds, len(rounds))

    return rounds, synthesis
