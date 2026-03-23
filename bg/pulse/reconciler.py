from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import logging

from bg.ice import load_ice_module
from bg.state.models import MumbleServer, MumbleUser

logger = logging.getLogger(__name__)


class MurmurReconcileError(RuntimeError):
    """Raised when the Murmur reconciliation engine cannot continue."""


class MurmurReconcileAction(str, Enum):
    """Supported Murmur action verbs in a plan."""

    CREATE = "create"
    DELETE = "delete"


@dataclass(frozen=True)
class MurmurDesiredAction:
    """A user-level action against one Murmur server."""

    action: MurmurReconcileAction
    server: MumbleServer
    user_id: int | None
    username: str


@dataclass(frozen=True)
class MurmurReconcilePlan:
    """Planned reconciliation actions for one server."""

    server: MumbleServer
    actions: tuple[MurmurDesiredAction, ...]
    errors: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.actions

    @property
    def create_count(self) -> int:
        return sum(1 for action in self.actions if action.action == MurmurReconcileAction.CREATE)

    @property
    def delete_count(self) -> int:
        return sum(1 for action in self.actions if action.action == MurmurReconcileAction.DELETE)


@dataclass(frozen=True)
class MurmurReconcileResult:
    """Execution summary for one server."""

    server_id: int
    server_name: str
    planned_create_count: int
    planned_delete_count: int
    created_count: int
    deleted_count: int
    failed_count: int
    dry_run: bool
    errors: tuple[str, ...] = ()

    @property
    def changed_count(self) -> int:
        return self.created_count + self.deleted_count

    def to_dict(self) -> dict[str, object]:
        return {
            "server_id": self.server_id,
            "server_name": self.server_name,
            "dry_run": self.dry_run,
            "planned_create_count": self.planned_create_count,
            "planned_delete_count": self.planned_delete_count,
            "created_count": self.created_count,
            "deleted_count": self.deleted_count,
            "failed_count": self.failed_count,
            "changed_count": self.changed_count,
            "errors": list(self.errors),
        }


class _MurmurServerAdapter:
    """Thin ICE wrapper for a single Murmur server row."""

    def __init__(self, server: MumbleServer):
        self._server = server
        self._communicator = None
        self._M = None
        self._server_proxy = None

    def __enter__(self):
        self._open()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def close(self) -> None:
        if self._communicator is not None:
            try:
                self._communicator.destroy()
            except Exception:
                logger.exception("Failed to close ICE communicator for %s", self._server.name)
            self._communicator = None
            self._M = None
            self._server_proxy = None

    @property
    def _connected(self) -> bool:
        return self._server_proxy is not None

    def list_registered_usernames(self) -> list[str]:
        if not self._connected:
            self._open()
        assert self._server_proxy is not None
        users = self._server_proxy.getRegisteredUsers("")
        return [str(name).strip() for _, name in (users or {}).items() if str(name or "").strip()]

    def create_or_update_user(self, mumble_user: MumbleUser) -> int:
        if not self._connected:
            self._open()
        assert self._server_proxy is not None and self._M is not None

        existing_userid = self._find_userid(mumble_user.username)
        info = _build_registration_info(self._M, mumble_user)
        if existing_userid is None:
            target_userid = int(self._server_proxy.registerUser(info))
            if target_userid < 0:
                raise MurmurReconcileError(
                    f"Failed to create Murmur user {mumble_user.username} on {self._server.name}"
                )
            return target_userid

        self._server_proxy.updateRegistration(int(existing_userid), info)
        return int(existing_userid)

    def delete_user(self, username: str) -> bool:
        if not self._connected:
            self._open()
        assert self._server_proxy is not None

        user_id = self._find_userid(username)
        if user_id is None:
            return False
        self._server_proxy.unregisterUser(int(user_id))
        return True

    def _find_userid(self, username: str) -> int | None:
        target = _normalize_username(username)
        if not target:
            return None
        for user_id, registered_name in (self._server_proxy.getRegisteredUsers("") or {}).items():
            current = _normalize_username(registered_name)
            if current == target:
                return int(user_id)
        return None

    def _open(self) -> None:
        if self._server_proxy is not None:
            return

        try:
            import Ice  # type: ignore
        except Exception as exc:
            raise MurmurReconcileError("ZeroC ICE is not installed in this environment") from exc

        M = load_ice_module()
        communicator = Ice.initialize(["--Ice.ImplicitContext=Shared", "--Ice.Default.EncodingVersion=1.0"])
        try:
            if self._server.ice_secret:
                communicator.getImplicitContext().put("secret", self._server.ice_secret)

            proxy = communicator.stringToProxy(
                f"Meta:tcp -h {self._server.ice_host} -p {self._server.ice_port}"
            )
            meta = M.MetaPrx.checkedCast(proxy)
            if not meta:
                raise MurmurReconcileError(
                    f"Failed to connect to ICE Meta on {self._server.ice_host}:{self._server.ice_port}"
                )

            booted_servers = meta.getBootedServers()
            if not booted_servers:
                raise MurmurReconcileError(
                    f"No booted Murmur servers found on {self._server.ice_host}:{self._server.ice_port}"
                )

            target = None
            if self._server.virtual_server_id is not None:
                for booted_server in booted_servers:
                    if booted_server.id() == self._server.virtual_server_id:
                        target = booted_server
                        break
                if target is None:
                    raise MurmurReconcileError(
                        f"Configured virtual_server_id={self._server.virtual_server_id} not found "
                        f"on {self._server.ice_host}:{self._server.ice_port}"
                    )
            elif len(booted_servers) == 1:
                target = booted_servers[0]
            else:
                raise MurmurReconcileError(
                    "Multiple virtual servers are booted on this ICE endpoint; "
                    "configure virtual_server_id on bg MumbleServer rows"
                )

            self._server_proxy = target.ice_context({"secret": self._server.ice_secret}) if self._server.ice_secret else target
            self._communicator = communicator
            self._M = M
        except Exception:
            try:
                communicator.destroy()
            except Exception:
                pass
            raise


def _normalize_username(value: object | None) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text.casefold()


def _build_registration_info(M, mumble_user: MumbleUser):
    info = {
        M.UserInfo.UserName: mumble_user.username,
    }
    if mumble_user.certhash:
        info[M.UserInfo.UserHash] = mumble_user.certhash
    if mumble_user.display_name:
        info[M.UserInfo.UserComment] = mumble_user.display_name
    return info


class MurmurRegistrationReconciler:
    """Build and apply plans that align Murmur registrations to bg MumbleUser rows."""

    def __init__(self, server_id: int | None = None):
        self._server_id = server_id

    def _load_servers(self) -> list[MumbleServer]:
        qs = MumbleServer.objects.filter(is_active=True).order_by("display_order", "name")
        if self._server_id is not None:
            qs = qs.filter(pk=self._server_id)
        return list(qs)

    def _load_desired_users(self, server: MumbleServer) -> list[MumbleUser]:
        return list(
            MumbleUser.objects.filter(
                is_active=True,
                server=server,
                server__is_active=True,
            )
            .exclude(username="")
            .order_by("username")
        )

    def build_plans(self) -> list[MurmurReconcilePlan]:
        servers = self._load_servers()
        if not servers:
            raise MurmurReconcileError("No active MumbleServer rows matched for reconciliation")

        plans: list[MurmurReconcilePlan] = []
        for server in servers:
            desired_rows = self._load_desired_users(server)
            desired_by_name = {
                _normalize_username(row.username): row
                for row in desired_rows
                if _normalize_username(row.username)
            }

            plan_errors: tuple[str, ...] = ()
            try:
                with _MurmurServerAdapter(server) as adapter:
                    live_names = {_normalize_username(name) for name in adapter.list_registered_usernames()}
            except Exception as exc:
                message = f"plan {server.name}: {exc}"
                logger.exception("Failed to build reconcile plan for server_row=%s (%s)", server.id, server.name)
                plans.append(
                    MurmurReconcilePlan(
                        server=server,
                        actions=tuple(),
                        errors=(message,),
                    )
                )
                continue

            create_actions: list[MurmurDesiredAction] = []
            for normalized_name, row in desired_by_name.items():
                if normalized_name not in live_names:
                    create_actions.append(
                        MurmurDesiredAction(
                            action=MurmurReconcileAction.CREATE,
                            server=server,
                            user_id=row.pk,
                            username=row.username,
                        )
                    )

            delete_actions: list[MurmurDesiredAction] = []
            for live_name in live_names:
                if live_name not in desired_by_name:
                    delete_actions.append(
                        MurmurDesiredAction(
                            action=MurmurReconcileAction.DELETE,
                            server=server,
                            user_id=None,
                            username=live_name,
                        )
                    )

            plans.append(
                MurmurReconcilePlan(
                    server=server,
                    actions=tuple(
                        sorted(
                            create_actions,
                            key=lambda action: action.username.lower(),
                        )
                        + sorted(
                            delete_actions,
                            key=lambda action: action.username.lower(),
                        )
                    ),
                    errors=plan_errors,
                )
            )

        return plans

    def reconcile(self, *, dry_run: bool = True) -> list[MurmurReconcileResult]:
        plans = self.build_plans()
        results: list[MurmurReconcileResult] = []

        create_by_id: dict[int, MumbleUser] = {
            row.pk: row
            for row in MumbleUser.objects.filter(is_active=True, server__is_active=True)
        }

        for plan in plans:
            created_count = 0
            deleted_count = 0
            failed_count = len(plan.errors)
            errors: list[str] = list(plan.errors)

            if plan.is_empty:
                results.append(
                    MurmurReconcileResult(
                        server_id=plan.server.pk,
                        server_name=plan.server.name,
                        planned_create_count=0,
                        planned_delete_count=0,
                        created_count=0,
                        deleted_count=0,
                        failed_count=failed_count,
                        dry_run=dry_run,
                        errors=tuple(errors),
                    )
                )
                continue

            with _MurmurServerAdapter(plan.server) as adapter:
                for action in plan.actions:
                    try:
                        if action.action == MurmurReconcileAction.CREATE:
                            if dry_run:
                                created_count += 1
                                continue
                            mumble_user = create_by_id.get(action.user_id or 0)
                            if mumble_user is None:
                                failed_count += 1
                                errors.append(f"Create failed for {action.username}: user row missing")
                                continue
                            adapter.create_or_update_user(mumble_user)
                            created_count += 1
                        else:
                            if dry_run:
                                deleted_count += 1
                                continue
                            if adapter.delete_user(action.username):
                                deleted_count += 1
                    except Exception as exc:
                        failed_count += 1
                        errors.append(f"{action.action.value} {action.username}: {exc}")
                        logger.exception("Failed to reconcile action for %s", action.username)

            results.append(
                MurmurReconcileResult(
                    server_id=plan.server.pk,
                    server_name=plan.server.name,
                    planned_create_count=plan.create_count,
                    planned_delete_count=plan.delete_count,
                    created_count=created_count,
                    deleted_count=deleted_count,
                    failed_count=failed_count,
                    dry_run=dry_run,
                    errors=tuple(errors),
                )
            )

        return results
