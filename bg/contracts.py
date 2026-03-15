"""Local contract helpers shared within mumble-bg."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


def _coerce_optional_int(value: Any, *, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc


@dataclass(frozen=True)
class PilotIdentity:
    """Cross-source pilot projection used by mumble-bg workers."""

    source: str
    character_id: int
    character_name: str
    corporation_id: int | None
    corporation_name: str
    corporation_ticker: str = ""
    alliance_id: int | None = None
    alliance_name: str = ""
    alliance_ticker: str = ""
    is_main: bool | None = None
    user_id: int | None = None
    source_pk: int | str | None = None
    source_model: str | None = None
    raw: Mapping[str, Any] | None = None

    @classmethod
    def from_record(
        cls,
        source: str,
        character_id: int,
        character_name: str,
        corporation_id: int | None,
        alliance_id: int | None,
        corporation_name: str = "",
        alliance_name: str = "",
        corporation_ticker: str = "",
        alliance_ticker: str = "",
        *,
        source_pk: int | str | None = None,
        source_model: str | None = None,
        is_main: bool | None = None,
        user_id: int | None = None,
        raw: Mapping[str, Any] | None = None,
    ) -> "PilotIdentity":
        return cls(
            source=str(source),
            source_pk=source_pk,
            source_model=source_model,
            character_id=int(character_id),
            character_name=character_name or "",
            corporation_id=int(corporation_id) if corporation_id is not None else None,
            corporation_name=(corporation_name or "").strip(),
            corporation_ticker=corporation_ticker or "",
            alliance_id=int(alliance_id) if alliance_id is not None else None,
            alliance_name=(alliance_name or "").strip(),
            alliance_ticker=alliance_ticker or "",
            is_main=is_main,
            user_id=user_id,
            raw=raw,
        )


@dataclass(frozen=True)
class MurmurContract:
    """Focused contract payload shared by fg/bg control endpoints."""

    evepilot_id: int | None = None
    corporation_id: int | None = None
    alliance_id: int | None = None
    kdf_iterations: int | None = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "MurmurContract":
        return cls(
            evepilot_id=_coerce_optional_int(payload.get("evepilot_id"), field_name="evepilot_id"),
            corporation_id=_coerce_optional_int(payload.get("corporation_id"), field_name="corporation_id"),
            alliance_id=_coerce_optional_int(payload.get("alliance_id"), field_name="alliance_id"),
            kdf_iterations=_coerce_optional_int(payload.get("kdf_iterations"), field_name="kdf_iterations"),
        )

    def as_payload(self) -> dict[str, int | None]:
        return {
            "evepilot_id": self.evepilot_id,
            "corporation_id": self.corporation_id,
            "alliance_id": self.alliance_id,
            "kdf_iterations": self.kdf_iterations,
        }


@dataclass(frozen=True)
class MurmurRegistrationContractPatch:
    """Patch envelope for a registration contract mutation request."""

    evepilot_id: int | None
    corporation_id: int | None
    alliance_id: int | None
    kdf_iterations: int | None
    provided_fields: tuple[str, ...] = ()

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any], *, require_fields: bool = True) -> "MurmurRegistrationContractPatch":
        fields_present = {
            "evepilot_id": "evepilot_id" in payload,
            "corporation_id": "corporation_id" in payload,
            "alliance_id": "alliance_id" in payload,
            "kdf_iterations": "kdf_iterations" in payload,
        }
        if require_fields and not any(fields_present.values()):
            raise ValueError(
                "At least one contract field is required: "
                "evepilot_id, corporation_id, alliance_id, or kdf_iterations"
            )
        evepilot_id = (
            _coerce_optional_int(payload.get("evepilot_id"), field_name="evepilot_id")
            if fields_present["evepilot_id"]
            else None
        )
        corporation_id = (
            _coerce_optional_int(payload.get("corporation_id"), field_name="corporation_id")
            if fields_present["corporation_id"]
            else None
        )
        alliance_id = (
            _coerce_optional_int(payload.get("alliance_id"), field_name="alliance_id")
            if fields_present["alliance_id"]
            else None
        )
        kdf_iterations = (
            _coerce_optional_int(payload.get("kdf_iterations"), field_name="kdf_iterations")
            if fields_present["kdf_iterations"]
            else None
        )
        if kdf_iterations is not None and kdf_iterations <= 0:
            raise ValueError("kdf_iterations must be a positive integer")
        provided_fields = tuple(field for field, present in fields_present.items() if present)
        return cls(
            evepilot_id=evepilot_id,
            corporation_id=corporation_id,
            alliance_id=alliance_id,
            kdf_iterations=kdf_iterations,
            provided_fields=provided_fields,
        )

    def update_fields(self) -> list[str]:
        return [*self.provided_fields, "updated_at"]

    @property
    def contract(self) -> MurmurContract:
        return MurmurContract(
            evepilot_id=self.evepilot_id,
            corporation_id=self.corporation_id,
            alliance_id=self.alliance_id,
            kdf_iterations=self.kdf_iterations,
        )

    def as_payload(self) -> dict[str, int | None]:
        return self.contract.as_payload()


@dataclass(frozen=True)
class MurmurRegistrationSnapshot:
    """Snapshot row for control responses and probe payloads."""

    server_id: int
    server_name: str
    username: str
    display_name: str
    mumble_userid: int | None
    contract: MurmurContract
    is_active: bool
    is_murmur_admin: bool
    hashfn: str
    active_session_ids: tuple[int, ...] = field(default_factory=tuple)
    has_priority_speaker: bool = False
    pw_lastchanged: str | None = None
    last_authenticated: str | None = None
    last_connected: str | None = None
    last_seen: str | None = None
    last_spoke: str | None = None

    @property
    def registration_status(self) -> str:
        return "active" if self.mumble_userid else "pending"

    @property
    def admin_membership_state(self) -> str:
        return "granted" if self.is_murmur_admin else "revoked"

    @property
    def active_session_count(self) -> int:
        return len(self.active_session_ids)

    @classmethod
    def from_row(
        cls,
        row: Any,
        active_session_ids: Iterable[int] = (),
        *,
        has_priority_speaker: bool = False,
    ) -> "MurmurRegistrationSnapshot":
        session_ids = tuple(sorted(int(value) for value in active_session_ids if value is not None))
        server = getattr(row, "server", None)
        return cls(
            server_id=int(getattr(row, "server_id")),
            server_name=str(getattr(server, "name", "") or getattr(row, "server_name", "")),
            username=str(getattr(row, "username", "")).strip(),
            display_name=str(getattr(row, "display_name", "") or "").strip(),
            mumble_userid=getattr(row, "mumble_userid", None),
            contract=MurmurContract(
                evepilot_id=getattr(row, "evepilot_id", None),
                corporation_id=getattr(row, "corporation_id", None),
                alliance_id=getattr(row, "alliance_id", None),
                kdf_iterations=getattr(row, "kdf_iterations", None),
            ),
            is_active=bool(getattr(row, "is_active", False)),
            is_murmur_admin=bool(getattr(row, "is_mumble_admin", False)),
            hashfn=str(getattr(row, "hashfn", "") or ""),
            active_session_ids=session_ids,
            has_priority_speaker=bool(has_priority_speaker),
            pw_lastchanged=(
                getattr(row, "updated_at").isoformat()
                if getattr(row, "updated_at", None) is not None
                else None
            ),
            last_authenticated=(
                getattr(row, "last_authenticated").isoformat()
                if getattr(row, "last_authenticated", None) is not None
                else None
            ),
            last_connected=(
                getattr(row, "last_connected").isoformat()
                if getattr(row, "last_connected", None) is not None
                else None
            ),
            last_seen=(
                getattr(row, "last_seen").isoformat()
                if getattr(row, "last_seen", None) is not None
                else None
            ),
            last_spoke=(
                getattr(row, "last_spoke").isoformat()
                if getattr(row, "last_spoke", None) is not None
                else None
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "server_id": self.server_id,
            "server_name": self.server_name,
            "username": self.username,
            "display_name": self.display_name,
            "mumble_userid": self.mumble_userid,
            "evepilot_id": self.contract.evepilot_id,
            "corporation_id": self.contract.corporation_id,
            "alliance_id": self.contract.alliance_id,
            "kdf_iterations": self.contract.kdf_iterations,
            "registration_status": self.registration_status,
            "is_active": self.is_active,
            "is_murmur_admin": self.is_murmur_admin,
            "admin_membership_state": self.admin_membership_state,
            "hashfn": self.hashfn,
            "active_session_ids": list(self.active_session_ids),
            "active_session_count": self.active_session_count,
            "has_priority_speaker": self.has_priority_speaker,
            "pw_lastchanged": self.pw_lastchanged,
            "last_authenticated": self.last_authenticated,
            "last_connected": self.last_connected,
            "last_seen": self.last_seen,
            "last_spoke": self.last_spoke,
        }
