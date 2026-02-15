"""
Helpers for CLI chat mode and conversation context.
"""

from typing import Any

CHAT_COMMANDS = {
    "help": "Show this help",
    "history": "List saved conversations",
    "use": "Switch to a conversation by ID prefix",
    "new": "Start a new conversation",
    "debate": "Toggle debate mode (on/off)",
    "rounds": "Set debate rounds",
    "stream": "Toggle streaming mode (on/off)",
    "react": "Toggle ReAct reasoning (on/off)",
    "mode": "Show current mode",
    "exit": "Exit chat",
}

CHAT_COMMAND_ALIASES = {
    "q": "exit",
    "quit": "exit",
}


def parse_chat_command(text: str) -> tuple[str, str | None]:
    """Parse chat command into (command, argument)."""
    stripped = text.strip()
    if not stripped.startswith(("/", ":")):
        return "", None

    body = stripped[1:].strip()
    if not body:
        return "", None

    parts = body.split(maxsplit=1)
    command = parts[0].lower()
    argument = parts[1].strip() if len(parts) > 1 else None
    if command in CHAT_COMMAND_ALIASES:
        command = CHAT_COMMAND_ALIASES[command]
    return command, argument


def list_chat_commands() -> list[str]:
    """Return all supported chat commands."""
    return list(CHAT_COMMANDS.keys())


def suggest_chat_commands(prefix: str) -> list[str]:
    """Suggest commands matching a prefix."""
    prefix = prefix.lower().strip()
    if not prefix:
        return list_chat_commands()
    return [command for command in CHAT_COMMANDS if command.startswith(prefix)]


def format_chat_mode_line(
    debate_enabled: bool,
    debate_rounds: int,
    stream_enabled: bool = False,
    react_enabled: bool = True,
) -> str:
    """Format the current chat mode line for display."""
    if debate_enabled:
        mode_str = f"Debate ({debate_rounds} rounds)"
        if stream_enabled:
            mode_str += r" \[streaming]"
    else:
        mode_str = "Council (ranking)"

    if react_enabled:
        mode_str += r" \[react]"

    return f"[chat.meta]Mode:[/chat.meta] [chat.accent]{mode_str}[/chat.accent]"


def build_chat_prompt() -> str:
    """Build the chat prompt string."""
    return "[chat.prompt]council>[/chat.prompt] "


def extract_assistant_reply(message: dict[str, Any]) -> str:
    """Extract the assistant reply text from a stored message."""
    if message.get("stage3"):
        return message["stage3"].get("response", "").strip()
    if message.get("synthesis"):
        return message["synthesis"].get("response", "").strip()
    if message.get("content"):
        return message.get("content", "").strip()
    return ""


def extract_conversation_pairs(messages: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """
    Extract (user, assistant) pairs from stored conversation messages.

    Only Stage 3 (or debate synthesis) is used for assistant context.
    """
    pairs: list[tuple[str, str]] = []
    pending_user = None

    for message in messages:
        role = message.get("role")
        if role == "user":
            pending_user = message.get("content", "")
        elif role == "assistant":
            if pending_user is None:
                continue
            assistant_text = extract_assistant_reply(message)
            if assistant_text:
                pairs.append((pending_user, assistant_text))
            pending_user = None

    return pairs


def select_context_pairs(pairs: list[tuple[str, str]], max_turns: int) -> list[tuple[str, str]]:
    """
    Select the first pair plus the last N pairs, preserving order.
    """
    if max_turns <= 0 or not pairs:
        return []
    if len(pairs) <= max_turns + 1:
        return pairs
    return [pairs[0]] + pairs[-max_turns:]


def format_context_pairs(pairs: list[tuple[str, str]]) -> str:
    """Format conversation pairs into a readable context block."""
    lines = []
    for user_text, assistant_text in pairs:
        lines.append(f"User: {user_text}")
        lines.append(f"Assistant: {assistant_text}")
        lines.append("")
    return "\n".join(lines).rstrip()


def build_context_prompt(conversation: dict[str, Any], max_turns: int) -> str:
    """Build a context prompt from a conversation record."""
    messages = conversation.get("messages", [])
    pairs = extract_conversation_pairs(messages)
    selected = select_context_pairs(pairs, max_turns=max_turns)
    if not selected:
        return ""

    context_body = format_context_pairs(selected)
    return (
        "Conversation context (earliest to latest):\n"
        f"{context_body}\n\n"
        "Use the context above if it is relevant to the current question."
    )
