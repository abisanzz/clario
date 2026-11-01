"""How Clario names its AI on screen. Records saved before the product voice was adopted say "Claude"; they are
shown as "Clario AI" without changing what was saved."""

AI_NAME = "Clario AI"


def product_voice(text: str) -> str:
    return text.replace("Claude", AI_NAME) if text else text
