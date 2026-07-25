from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import bcrypt
from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    select,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .models import Node, RunResult, Workflow, WorkflowCreate, utc_now


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(30), default="member", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class WorkspaceRow(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(140), unique=True, index=True, nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class MembershipRow(Base):
    __tablename__ = "workspace_memberships"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(30), default="member", nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class TeamRow(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    policy: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_by: Mapped[str] = mapped_column(String(40), ForeignKey("users.id"))
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


class TeamMembershipRow(Base):
    __tablename__ = "team_memberships"
    __table_args__ = (UniqueConstraint("team_id", "user_id"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    team_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("teams.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class WorkflowRow(Base):
    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    created_by: Mapped[str] = mapped_column(String(40), ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    payload: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT(), "mysql"), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, index=True)


class RunRow(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("workflows.id", ondelete="CASCADE"), index=True
    )
    workspace_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    payload: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT(), "mysql"), nullable=False)
    started_at: Mapped[str] = mapped_column(String(40), nullable=False, index=True)


class ProviderRow(Base):
    __tablename__ = "ai_providers"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    default_model: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    api_key_encrypted: Mapped[str] = mapped_column(Text, default="", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


class Store:
    def __init__(self, database: str | Path):
        if isinstance(database, Path) or "://" not in str(database):
            path = Path(database)
            path.parent.mkdir(parents=True, exist_ok=True)
            database_url = f"sqlite:///{path.as_posix()}"
            connect_args = {"check_same_thread": False}
        else:
            database_url = str(database)
            connect_args = {}
        self.engine = create_engine(
            database_url,
            pool_pre_ping=True,
            pool_recycle=1800,
            connect_args=connect_args,
        )
        if self.engine.dialect.name == "sqlite":
            @event.listens_for(self.engine, "connect")
            def enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()
        self.Session = sessionmaker(self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

    @staticmethod
    def _user_dict(row: UserRow) -> dict[str, object]:
        role = "user" if row.role in {"member", "owner"} else row.role
        return {
            "id": row.id,
            "name": row.name,
            "email": row.email,
            "role": role,
            "active": row.active,
            "created_at": row.created_at,
        }

    @staticmethod
    def _workspace_dict(row: WorkspaceRow) -> dict[str, str]:
        return {
            "id": row.id,
            "name": row.name,
            "slug": row.slug,
            "created_at": row.created_at,
        }

    def has_users(self) -> bool:
        with self.Session() as db:
            return db.scalar(select(UserRow.id).limit(1)) is not None

    def create_admin(
        self,
        *,
        name: str,
        email: str,
        password: str,
        workspace_name: str,
    ) -> tuple[dict[str, object], dict[str, str]]:
        with self.Session.begin() as db:
            if db.scalar(select(UserRow.id).limit(1)):
                raise ValueError("O administrador inicial já foi criado.")
            now = utc_now()
            user = UserRow(
                id=f"usr-{uuid4().hex[:12]}",
                name=name.strip(),
                email=email.strip().lower(),
                password_hash=bcrypt.hashpw(
                    password.encode("utf-8"), bcrypt.gensalt(rounds=12)
                ).decode("ascii"),
                role="admin",
                active=True,
                created_at=now,
            )
            workspace = WorkspaceRow(
                id=f"ws-{uuid4().hex[:12]}",
                name=workspace_name.strip(),
                slug=f"workspace-{uuid4().hex[:8]}",
                created_at=now,
            )
            db.add_all([user, workspace])
            # Without ORM relationships SQLAlchemy cannot infer unit-of-work
            # dependency ordering reliably across every dialect. Flush the
            # parent rows before inserting the membership foreign keys.
            db.flush()
            membership = MembershipRow(
                id=f"mem-{uuid4().hex[:12]}",
                workspace_id=workspace.id,
                user_id=user.id,
                role="owner",
                created_at=now,
            )
            db.add(membership)
        return self._user_dict(user), self._workspace_dict(workspace)

    def authenticate(self, email: str, password: str) -> dict[str, object] | None:
        with self.Session() as db:
            user = db.scalar(select(UserRow).where(UserRow.email == email.strip().lower()))
            if (
                not user
                or not user.active
                or not bcrypt.checkpw(
                    password.encode("utf-8"), user.password_hash.encode("ascii")
                )
            ):
                return None
            return self._user_dict(user)

    def get_user(self, user_id: str) -> dict[str, object] | None:
        with self.Session() as db:
            user = db.get(UserRow, user_id)
            return self._user_dict(user) if user and user.active else None

    def get_user_workspace(self, user_id: str) -> dict[str, str] | None:
        return self.get_accessible_workspace(user_id)

    def list_workspaces(self, user_id: str) -> list[dict[str, str]]:
        with self.Session() as db:
            user = db.get(UserRow, user_id)
            if not user:
                return []
            if user.role == "admin":
                rows = db.scalars(select(WorkspaceRow).order_by(WorkspaceRow.name)).all()
                memberships = {
                    item.workspace_id: item.role
                    for item in db.scalars(
                        select(MembershipRow).where(
                            MembershipRow.user_id == user_id
                        )
                    ).all()
                }
                return [
                    {
                        **self._workspace_dict(row),
                        "membership_role": memberships.get(row.id, "admin"),
                    }
                    for row in rows
                ]
            rows = db.execute(
                select(WorkspaceRow, MembershipRow.role)
                .join(MembershipRow, MembershipRow.workspace_id == WorkspaceRow.id)
                .where(MembershipRow.user_id == user_id)
                .order_by(WorkspaceRow.name)
            ).all()
            return [
                {**self._workspace_dict(workspace), "membership_role": role}
                for workspace, role in rows
            ]

    def get_accessible_workspace(
        self, user_id: str, workspace_id: str | None = None
    ) -> dict[str, str] | None:
        workspaces = self.list_workspaces(user_id)
        if workspace_id:
            return next((item for item in workspaces if item["id"] == workspace_id), None)
        return workspaces[0] if workspaces else None

    def list_all_users(self) -> list[dict[str, object]]:
        with self.Session() as db:
            users = db.scalars(select(UserRow).order_by(UserRow.name)).all()
            memberships = db.scalars(select(MembershipRow)).all()
            workspace_ids: dict[str, list[str]] = {}
            for membership in memberships:
                workspace_ids.setdefault(membership.user_id, []).append(
                    membership.workspace_id
                )
            return [
                {
                    **self._user_dict(user),
                    "workspace_ids": workspace_ids.get(user.id, []),
                }
                for user in users
            ]

    def create_user(
        self, *, name: str, email: str, password: str, role: str
    ) -> dict[str, object]:
        with self.Session.begin() as db:
            if db.scalar(
                select(UserRow.id).where(UserRow.email == email.strip().lower())
            ):
                raise ValueError("Já existe um usuário com este e-mail.")
            row = UserRow(
                id=f"usr-{uuid4().hex[:12]}",
                name=name.strip(),
                email=email.strip().lower(),
                password_hash=bcrypt.hashpw(
                    password.encode("utf-8"), bcrypt.gensalt(rounds=12)
                ).decode("ascii"),
                role=role,
                active=True,
                created_at=utc_now(),
            )
            db.add(row)
        return self._user_dict(row)

    def update_user(
        self, user_id: str, *, name: str, role: str, active: bool
    ) -> dict[str, object] | None:
        with self.Session.begin() as db:
            row = db.get(UserRow, user_id)
            if not row:
                return None
            row.name = name.strip()
            row.role = role
            row.active = active
        return self._user_dict(row)

    def create_workspace(self, name: str) -> dict[str, str]:
        now = utc_now()
        row = WorkspaceRow(
            id=f"ws-{uuid4().hex[:12]}",
            name=name.strip(),
            slug=f"workspace-{uuid4().hex[:8]}",
            created_at=now,
        )
        with self.Session.begin() as db:
            db.add(row)
        return self._workspace_dict(row)

    def set_workspace_membership(
        self, workspace_id: str, user_id: str, enabled: bool
    ) -> bool:
        with self.Session() as db:
            if not db.get(WorkspaceRow, workspace_id) or not db.get(UserRow, user_id):
                return False
        with self.Session.begin() as db:
            membership = db.scalar(
                select(MembershipRow).where(
                    MembershipRow.workspace_id == workspace_id,
                    MembershipRow.user_id == user_id,
                )
            )
            if enabled and not membership:
                db.add(
                    MembershipRow(
                        id=f"mem-{uuid4().hex[:12]}",
                        workspace_id=workspace_id,
                        user_id=user_id,
                        role="member",
                        created_at=utc_now(),
                    )
                )
            elif not enabled and membership:
                db.delete(membership)
                teams = db.scalars(
                    select(TeamRow.id).where(TeamRow.workspace_id == workspace_id)
                ).all()
                for team_membership in db.scalars(
                    select(TeamMembershipRow).where(
                        TeamMembershipRow.user_id == user_id,
                        TeamMembershipRow.team_id.in_(teams),
                    )
                ).all():
                    db.delete(team_membership)
        return True

    def list_users(self, workspace_id: str) -> list[dict[str, object]]:
        with self.Session() as db:
            rows = db.execute(
                select(UserRow, MembershipRow.role)
                .join(MembershipRow, MembershipRow.user_id == UserRow.id)
                .where(MembershipRow.workspace_id == workspace_id)
                .order_by(UserRow.created_at)
            ).all()
            return [
                {**self._user_dict(user), "workspace_role": role}
                for user, role in rows
            ]

    @staticmethod
    def _team_dict(
        row: TeamRow, member_ids: list[str] | None = None
    ) -> dict[str, object]:
        return {
            "id": row.id,
            "workspace_id": row.workspace_id,
            "name": row.name,
            "description": row.description,
            "policy": json.loads(row.policy or "{}"),
            "member_ids": member_ids or [],
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def list_teams(self, workspace_id: str) -> list[dict[str, object]]:
        with self.Session() as db:
            teams = db.scalars(
                select(TeamRow)
                .where(TeamRow.workspace_id == workspace_id)
                .order_by(TeamRow.name)
            ).all()
            memberships = db.scalars(select(TeamMembershipRow)).all()
            members: dict[str, list[str]] = {}
            for membership in memberships:
                members.setdefault(membership.team_id, []).append(membership.user_id)
            return [self._team_dict(team, members.get(team.id, [])) for team in teams]

    def create_team(
        self,
        *,
        workspace_id: str,
        name: str,
        description: str,
        policy: dict[str, object],
        created_by: str,
    ) -> dict[str, object]:
        now = utc_now()
        row = TeamRow(
            id=f"team-{uuid4().hex[:12]}",
            workspace_id=workspace_id,
            name=name.strip(),
            description=description.strip(),
            policy=json.dumps(policy),
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        with self.Session.begin() as db:
            db.add(row)
        return self._team_dict(row)

    def update_team(
        self,
        team_id: str,
        workspace_id: str,
        *,
        name: str,
        description: str,
        policy: dict[str, object],
    ) -> dict[str, object] | None:
        with self.Session.begin() as db:
            row = db.scalar(
                select(TeamRow).where(
                    TeamRow.id == team_id, TeamRow.workspace_id == workspace_id
                )
            )
            if not row:
                return None
            row.name = name.strip()
            row.description = description.strip()
            row.policy = json.dumps(policy)
            row.updated_at = utc_now()
        member_ids = next(
            (
                item["member_ids"]
                for item in self.list_teams(workspace_id)
                if item["id"] == team_id
            ),
            [],
        )
        return self._team_dict(row, member_ids)

    def delete_team(self, team_id: str, workspace_id: str) -> bool:
        with self.Session.begin() as db:
            row = db.scalar(
                select(TeamRow).where(
                    TeamRow.id == team_id, TeamRow.workspace_id == workspace_id
                )
            )
            if not row:
                return False
            db.delete(row)
            return True

    def set_team_members(
        self, team_id: str, workspace_id: str, user_ids: list[str]
    ) -> bool:
        with self.Session.begin() as db:
            team = db.scalar(
                select(TeamRow).where(
                    TeamRow.id == team_id, TeamRow.workspace_id == workspace_id
                )
            )
            if not team:
                return False
            allowed_users = set(
                db.scalars(
                    select(MembershipRow.user_id).where(
                        MembershipRow.workspace_id == workspace_id,
                        MembershipRow.user_id.in_(user_ids),
                    )
                ).all()
            )
            existing = db.scalars(
                select(TeamMembershipRow).where(
                    TeamMembershipRow.team_id == team_id
                )
            ).all()
            existing_ids = {item.user_id for item in existing}
            for item in existing:
                if item.user_id not in allowed_users:
                    db.delete(item)
            for user_id in allowed_users - existing_ids:
                db.add(
                    TeamMembershipRow(
                        id=f"tmem-{uuid4().hex[:12]}",
                        team_id=team_id,
                        user_id=user_id,
                        created_at=utc_now(),
                    )
                )
        return True

    def effective_permissions(
        self, user_id: str, workspace_id: str
    ) -> dict[str, object]:
        user = self.get_user(user_id)
        role = user["role"] if user else "user"
        if role == "admin":
            return {
                "create_workflows": True,
                "edit_workflows": True,
                "run_workflows": True,
                "manage_providers": True,
                "manage_teams": True,
                "allowed_node_types": None,
            }
        with self.Session() as db:
            team_rows = db.execute(
                select(TeamRow.policy)
                .join(
                    TeamMembershipRow,
                    TeamMembershipRow.team_id == TeamRow.id,
                )
                .where(
                    TeamRow.workspace_id == workspace_id,
                    TeamMembershipRow.user_id == user_id,
                )
            ).all()
        policies = [json.loads(row.policy or "{}") for row in team_rows]
        permissions: dict[str, object] = {
            "create_workflows": role == "manager",
            "edit_workflows": role == "manager",
            "run_workflows": role == "manager",
            "manage_providers": role == "manager",
            "manage_teams": role == "manager",
            "allowed_node_types": None,
        }
        for key in (
            "create_workflows",
            "edit_workflows",
            "run_workflows",
            "manage_providers",
        ):
            permissions[key] = bool(
                permissions[key] or any(policy.get(key) for policy in policies)
            )
        if (
            policies
            and role != "manager"
            and all(
                policy.get("allowed_node_types") is not None
                for policy in policies
            )
        ):
            restrictions = [
                set(policy.get("allowed_node_types") or [])
                for policy in policies
            ]
            permissions["allowed_node_types"] = sorted(set().union(*restrictions))
        return permissions

    @staticmethod
    def _provider_dict(
        row: ProviderRow, include_secret: bool = False
    ) -> dict[str, object]:
        result: dict[str, object] = {
            "id": row.id,
            "workspace_id": row.workspace_id,
            "name": row.name,
            "type": row.type,
            "base_url": row.base_url,
            "default_model": row.default_model,
            "enabled": row.enabled,
            "has_api_key": bool(row.api_key_encrypted),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        if include_secret:
            result["api_key_encrypted"] = row.api_key_encrypted
        return result

    def list_providers(self, workspace_id: str) -> list[dict[str, object]]:
        with self.Session() as db:
            rows = db.scalars(
                select(ProviderRow)
                .where(ProviderRow.workspace_id == workspace_id)
                .order_by(ProviderRow.name)
            ).all()
            return [self._provider_dict(row) for row in rows]

    def get_provider(
        self, provider_id: str, workspace_id: str, include_secret: bool = False
    ) -> dict[str, object] | None:
        with self.Session() as db:
            row = db.scalar(
                select(ProviderRow).where(
                    ProviderRow.id == provider_id,
                    ProviderRow.workspace_id == workspace_id,
                )
            )
            return self._provider_dict(row, include_secret) if row else None

    def create_provider(
        self,
        *,
        workspace_id: str,
        name: str,
        provider_type: str,
        base_url: str,
        default_model: str,
        api_key_encrypted: str,
        enabled: bool,
    ) -> dict[str, object]:
        now = utc_now()
        row = ProviderRow(
            id=f"prv-{uuid4().hex[:12]}",
            workspace_id=workspace_id,
            name=name,
            type=provider_type,
            base_url=base_url,
            default_model=default_model,
            api_key_encrypted=api_key_encrypted,
            enabled=enabled,
            created_at=now,
            updated_at=now,
        )
        with self.Session.begin() as db:
            db.add(row)
        return self._provider_dict(row)

    def update_provider(
        self,
        provider_id: str,
        workspace_id: str,
        *,
        name: str,
        provider_type: str,
        base_url: str,
        default_model: str,
        api_key_encrypted: str | None,
        enabled: bool,
    ) -> dict[str, object] | None:
        with self.Session.begin() as db:
            row = db.scalar(
                select(ProviderRow).where(
                    ProviderRow.id == provider_id,
                    ProviderRow.workspace_id == workspace_id,
                )
            )
            if not row:
                return None
            row.name = name
            row.type = provider_type
            row.base_url = base_url
            row.default_model = default_model
            if api_key_encrypted is not None:
                row.api_key_encrypted = api_key_encrypted
            row.enabled = enabled
            row.updated_at = utc_now()
        return self._provider_dict(row)

    def delete_provider(self, provider_id: str, workspace_id: str) -> bool:
        with self.Session.begin() as db:
            row = db.scalar(
                select(ProviderRow).where(
                    ProviderRow.id == provider_id,
                    ProviderRow.workspace_id == workspace_id,
                )
            )
            if not row:
                return False
            db.delete(row)
            return True

    def list_workflows(self, workspace_id: str) -> list[Workflow]:
        with self.Session() as db:
            rows = db.scalars(
                select(WorkflowRow)
                .where(WorkflowRow.workspace_id == workspace_id)
                .order_by(WorkflowRow.updated_at.desc())
            ).all()
            return [Workflow.model_validate_json(row.payload) for row in rows]

    def get_workflow(
        self, workflow_id: str, workspace_id: str | None = None
    ) -> Workflow | None:
        with self.Session() as db:
            query = select(WorkflowRow).where(WorkflowRow.id == workflow_id)
            if workspace_id:
                query = query.where(WorkflowRow.workspace_id == workspace_id)
            row = db.scalar(query)
            return Workflow.model_validate_json(row.payload) if row else None

    def find_webhook(self, webhook_id: str) -> tuple[Workflow, Node, str] | None:
        with self.Session() as db:
            rows = db.scalars(select(WorkflowRow)).all()
            for row in rows:
                workflow = Workflow.model_validate_json(row.payload)
                for node in workflow.nodes:
                    if node.type == "webhook" and node.config.get("webhook_id") == webhook_id:
                        return workflow, node, row.workspace_id
        return None

    def create_workflow(
        self, data: WorkflowCreate, workspace_id: str, created_by: str
    ) -> Workflow:
        workflow = Workflow(**data.model_dump())
        with self.Session.begin() as db:
            db.add(
                WorkflowRow(
                    id=workflow.id,
                    workspace_id=workspace_id,
                    created_by=created_by,
                    name=workflow.name,
                    description=workflow.description,
                    version=workflow.version,
                    payload=workflow.model_dump_json(),
                    created_at=workflow.created_at,
                    updated_at=workflow.updated_at,
                )
            )
        return workflow

    def update_workflow(
        self, workflow_id: str, data: WorkflowCreate, workspace_id: str
    ) -> Workflow | None:
        with self.Session.begin() as db:
            row = db.scalar(
                select(WorkflowRow).where(
                    WorkflowRow.id == workflow_id,
                    WorkflowRow.workspace_id == workspace_id,
                )
            )
            if not row:
                return None
            current = Workflow.model_validate_json(row.payload)
            workflow = Workflow(
                **data.model_dump(),
                id=current.id,
                version=current.version + 1,
                created_at=current.created_at,
                updated_at=utc_now(),
            )
            row.name = workflow.name
            row.description = workflow.description
            row.version = workflow.version
            row.payload = workflow.model_dump_json()
            row.updated_at = workflow.updated_at
        return workflow

    def delete_workflow(self, workflow_id: str, workspace_id: str) -> bool:
        with self.Session.begin() as db:
            row = db.scalar(
                select(WorkflowRow).where(
                    WorkflowRow.id == workflow_id,
                    WorkflowRow.workspace_id == workspace_id,
                )
            )
            if not row:
                return False
            db.delete(row)
            return True

    def save_run(self, run: RunResult, workspace_id: str) -> None:
        with self.Session.begin() as db:
            db.add(
                RunRow(
                    id=run.id,
                    workflow_id=run.workflow_id,
                    workspace_id=workspace_id,
                    status=run.status,
                    payload=run.model_dump_json(),
                    started_at=run.started_at,
                )
            )

    def list_runs(
        self, workflow_id: str, workspace_id: str, limit: int = 20
    ) -> list[RunResult]:
        with self.Session() as db:
            rows = db.scalars(
                select(RunRow)
                .where(
                    RunRow.workflow_id == workflow_id,
                    RunRow.workspace_id == workspace_id,
                )
                .order_by(RunRow.started_at.desc())
                .limit(limit)
            ).all()
            return [RunResult.model_validate_json(row.payload) for row in rows]
