from __future__ import annotations

import logging
from typing import Iterable

from .ice_client import ICEClient


def ensure_corp_channels(ice: ICEClient, corp_tickers: Iterable[str], parent_channel_id: int) -> None:
    """
    Placeholder for creating corp channels under the Corps parent channel.

    This currently logs intent only; real ICE channel creation is future work.
    """
    logger = logging.getLogger(__name__)
    for ticker in corp_tickers:
        logger.info("ICE create: corp channel %s (placeholder)", ticker)
    _ = (ice, corp_tickers, parent_channel_id)
    return None


def remove_corp_channel(ice: ICEClient, corp_ticker: str, parent_channel_id: int) -> None:
    """
    Placeholder for deleting a corp channel when a corp leaves the alliance.

    This currently logs intent only; real ICE channel deletion is future work.
    """
    logger = logging.getLogger(__name__)
    logger.info("ICE delete: corp channel %s (placeholder)", corp_ticker)
    _ = (ice, corp_ticker, parent_channel_id)
    return None
