"""Fun / games — the playful Vector-style party tricks. Each returns a spoken line + an emote."""
from __future__ import annotations

import random
from typing import Any, Callable

_EIGHT_BALL = [
    "It is certain.",
    "Without a doubt.",
    "Yes, definitely.",
    "Signs point to yes.",
    "Reply hazy, try again.",
    "Ask again later.",
    "Don't count on it.",
    "My reply is no.",
    "Outlook not so good.",
]
_JOKES = [
    "Why did the robot go on vacation? It needed to recharge.",
    "I'd tell you a UDP joke, but you might not get it.",
    "Why was the robot angry? Someone kept pushing its buttons.",
    "I'm reading a book about anti-gravity. It's impossible to put down.",
]
_FORTUNES = [
    "A pleasant surprise is waiting for you.",
    "Today is a good day to ship code.",
    "Your battery is full of potential.",
    "Good things come to those who automate.",
]


def play_dice() -> dict[str, Any]:
    n = random.randint(1, 6)
    return {"text": f"I rolled a {n}!", "emote": "happy" if n >= 5 else "curious", "value": n}


def play_coin() -> dict[str, Any]:
    side = random.choice(["heads", "tails"])
    return {"text": f"It's {side}!", "emote": "yes" if side == "heads" else "no", "value": side}


def play_eightball() -> dict[str, Any]:
    return {"text": random.choice(_EIGHT_BALL), "emote": "curious"}


def play_joke() -> dict[str, Any]:
    return {"text": random.choice(_JOKES), "emote": "happy"}


def play_fortune() -> dict[str, Any]:
    return {"text": random.choice(_FORTUNES), "emote": "love"}


GAMES: dict[str, Callable[[], dict[str, Any]]] = {
    "dice": play_dice,
    "coin": play_coin,
    "8ball": play_eightball,
    "joke": play_joke,
    "fortune": play_fortune,
}


def game_names() -> list[str]:
    return list(GAMES)
