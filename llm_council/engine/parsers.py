"""
Text parsing utilities for council responses.

Handles extraction of rankings, critiques, revised answers, and ReAct output parsing.
"""

import re


def parse_ranking_from_text(ranking_text: str) -> list[str]:
    """
    Parse the FINAL RANKING section from the model's response.

    Args:
        ranking_text: The full text response from the model

    Returns:
        List of response labels in ranked order
    """
    # Look for "FINAL RANKING:" section
    if "FINAL RANKING:" in ranking_text:
        # Extract everything after "FINAL RANKING:"
        parts = ranking_text.split("FINAL RANKING:")
        if len(parts) >= 2:
            ranking_section = parts[1]
            # Try to extract numbered list format (e.g., "1. Response A")
            # This pattern looks for: number, period, optional space, "Response X"
            numbered_matches = re.findall(r"\d+\.\s*Response [A-Z]", ranking_section)
            if numbered_matches:
                # Extract just the "Response X" part
                return [re.search(r"Response [A-Z]", m).group() for m in numbered_matches]

            # Fallback: Extract all "Response X" patterns in order
            matches = re.findall(r"Response [A-Z]", ranking_section)
            return matches

    # Fallback: try to find any "Response X" patterns in order
    matches = re.findall(r"Response [A-Z]", ranking_text)
    return matches


def parse_revised_answer(defense_response: str) -> str:
    """
    Extract the 'Revised Response' section from a defense response.

    Args:
        defense_response: Full defense text

    Returns:
        The revised answer text, or full response if section not found
    """
    # Look for "## Revised Response" section
    pattern = r"##\s*Revised Response\s*\n(.*)"
    match = re.search(pattern, defense_response, re.IGNORECASE | re.DOTALL)

    if match:
        return match.group(1).strip()

    # Fallback: return the full response
    return defense_response


def extract_critiques_for_model(target_model: str, critique_responses: list[dict]) -> str:
    """
    Extract all critiques directed at a specific model.

    Args:
        target_model: The model whose critiques we want to extract
        critique_responses: All critique responses from round 2

    Returns:
        Concatenated string of all critiques for the target model
    """
    critiques = []
    # Get just the model name without provider prefix for matching
    target_name = target_model.split("/")[-1].lower()

    for response in critique_responses:
        critic_model = response["model"]
        # Skip self-critiques (shouldn't exist, but just in case)
        if critic_model == target_model:
            continue

        content = response["response"]

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


def parse_reflection_output(text: str) -> tuple[str, str]:
    """
    Split chairman reflection output at the ``## Synthesis`` header.

    Args:
        text: Raw model output containing optional reflection and a
              ``## Synthesis`` section.

    Returns:
        Tuple of (reflection_text, synthesis_text).
        Falls back to ("", full_text) if the header is not found.
    """
    match = re.search(r"##\s*Synthesis\s*\n", text, re.IGNORECASE)
    if match:
        reflection = text[: match.start()].strip()
        synthesis = text[match.end() :].strip()
        return reflection, synthesis
    return "", text


def parse_react_output(text: str) -> tuple[str, str, str]:
    """
    Parse ReAct output to extract Thought and Action.

    Args:
        text: Raw model output in ReAct format

    Returns:
        Tuple of (thought, action_name, action_args)
        - action_name is None if no valid action found
        - action_args is None for synthesize()/respond()
    """
    thought = None
    action = None
    action_args = None

    # Extract Thought section
    thought_match = re.search(
        r"Thought:\s*(.+?)(?=\n\s*Action:|$)", text, re.DOTALL | re.IGNORECASE
    )
    if thought_match:
        thought = thought_match.group(1).strip()

    # Terminal actions (no args): synthesize() and respond()
    _TERMINAL_ACTIONS = {"synthesize", "respond"}

    # Extract Action section
    action_match = re.search(r"Action:\s*(\w+)\s*\(([^)]*)\)", text, re.IGNORECASE)
    if action_match:
        action_name = action_match.group(1).lower()
        args = action_match.group(2).strip().strip("\"'")

        # Only recognize valid actions
        if action_name == "search_web":
            action = "search_web"
            action_args = args
        elif action_name in _TERMINAL_ACTIONS:
            action = action_name
            action_args = None
    else:
        # Check for terminal actions without args
        for terminal in _TERMINAL_ACTIONS:
            if re.search(rf"Action:\s*{terminal}\s*\(\s*\)", text, re.IGNORECASE):
                action = terminal
                action_args = None
                break

    return thought, action, action_args
