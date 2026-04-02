from html import escape


def format_login_name(alliance_ticker: str | None, corp_ticker: str | None, character_name: str) -> str:
    """
    Format a Murmur login name using optional alliance/corp tickers.
    """
    safe_alliance = (alliance_ticker or "").strip()
    safe_corp = (corp_ticker or "").strip()
    prefix = " ".join(part for part in [safe_alliance, safe_corp] if part)
    prefix = f"[{prefix}]" if prefix else ""
    display = f"{prefix} {character_name}".strip()
    return escape(display)
