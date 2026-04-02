"""Build a RosterSet from EVE and Mumble data sources."""

from __future__ import annotations

import logging

from ..models.eve import EveAlliance, EvePilot, EveRepository
from ..models.roster import RosterSet
from .ice_client import ICEClient

logger = logging.getLogger(__name__)


def build_roster(
    eve_repo: EveRepository,
    ice: ICEClient,
    focus: EveAlliance,
) -> RosterSet:
    """
    Partition EVE mains and Mumble users into three sets.

    main0 — pilots present in AUTH/CUBE but absent from Mumble.
    main1 — pilots present in both AUTH/CUBE and Mumble.
    mumble1 — Mumble usernames with no matching pilot.
    """
    pilot_by_label: dict[str, EvePilot] = {
        p.label: p
        for p in eve_repo.list_mains(alliance_id=focus.id)
        if p.alliance_id == focus.id
    }

    try:
        mumble_names: set[str] = set(ice.get_users())
        logger.debug("ICE: %d registered users", len(mumble_names))
    except NotImplementedError:
        mumble_names = set()
        logger.debug(
            "ICE.get_users not implemented; treating Mumble as empty"
        )

    main0: list[EvePilot] = []
    main1: list[EvePilot] = []
    for label, pilot in pilot_by_label.items():
        if label in mumble_names:
            main1.append(pilot)
        else:
            main0.append(pilot)

    mumble1: list[str] = [
        name for name in mumble_names if name not in pilot_by_label
    ]

    logger.info(
        "Roster: focus=%s main0=%d main1=%d mumble1=%d",
        focus.name,
        len(main0),
        len(main1),
        len(mumble1),
    )

    return RosterSet(
        focus=focus,
        main0=tuple(main0),
        main1=tuple(main1),
        mumble1=tuple(mumble1),
    )
