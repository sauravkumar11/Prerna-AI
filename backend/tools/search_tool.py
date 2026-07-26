"""
Search tool
===========
Specialized searches beyond plain web search (see browser_tool for that).
Each of these just builds the right URL for the right service - reliable,
no scraping, no API keys needed.
"""

from __future__ import annotations

import webbrowser
from urllib.parse import quote_plus

from agent.registry import ToolResult, action

TOOL_DESCRIPTION = "Search weather, news, maps, stocks, crypto, flights, hotels, restaurants, or medicine info."


def _open(url: str, message: str) -> ToolResult:
    webbrowser.open(url)
    return ToolResult(True, message)


@action("search", "weather", "Look up the weather for a place.", required_args=["place"], tool_description=TOOL_DESCRIPTION)
def weather(place: str) -> ToolResult:
    return _open(
        f"https://www.google.com/search?q={quote_plus('weather in ' + place)}",
        f"Checking the weather in {place}.",
    )


@action("search", "news", "Search recent news on a topic.", required_args=["query"])
def news(query: str) -> ToolResult:
    return _open(
        f"https://news.google.com/search?q={quote_plus(query)}",
        f'Searching news for "{query}".',
    )


@action("search", "maps", "Search a place or get directions on Maps.", required_args=["query"])
def maps(query: str) -> ToolResult:
    return _open(
        f"https://www.google.com/maps/search/{quote_plus(query)}",
        f'Opening Maps for "{query}".',
    )


@action("search", "stocks", "Look up a stock/ticker.", required_args=["symbol"])
def stocks(symbol: str) -> ToolResult:
    return _open(
        f"https://www.google.com/search?q={quote_plus(symbol + ' stock')}",
        f"Looking up {symbol.upper()}.",
    )


@action("search", "crypto", "Look up a cryptocurrency price.", required_args=["symbol"])
def crypto(symbol: str) -> ToolResult:
    return _open(
        f"https://www.google.com/search?q={quote_plus(symbol + ' price crypto')}",
        f"Looking up {symbol.upper()}.",
    )


@action("search", "flights", "Search flights.", required_args=["query"])
def flights(query: str) -> ToolResult:
    return _open(
        f"https://www.google.com/travel/flights?q={quote_plus(query)}",
        f'Searching flights for "{query}".',
    )


@action("search", "hotels", "Search hotels in a place.", required_args=["place"])
def hotels(place: str) -> ToolResult:
    return _open(
        f"https://www.google.com/travel/hotels/{quote_plus(place)}",
        f"Searching hotels in {place}.",
    )


@action("search", "restaurants", "Search restaurants near a place.", required_args=["place"])
def restaurants(place: str) -> ToolResult:
    return _open(
        f"https://www.google.com/maps/search/{quote_plus('restaurants near ' + place)}",
        f"Searching restaurants near {place}.",
    )


@action("search", "medicine", "Look up information about a medicine.", required_args=["name"])
def medicine(name: str) -> ToolResult:
    return _open(
        f"https://www.google.com/search?q={quote_plus(name + ' medicine uses dosage')}",
        f"Looking up {name}. (For anything serious, please check with an actual doctor/pharmacist.)",
    )
