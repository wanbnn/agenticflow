from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import bcrypt
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, create_engine, select
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

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(30), default="member", nullable=False)
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
        self.Session = sessionmaker(self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

    @staticmethod
    def _user_dict(row: UserRow) -> dict[str, object]:
        return {
            "id": row.id,
            "name": row.name,
            "email": row.email,
            "role": row.role,
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
            membership = MembershipRow(
                id=f"mem-{uuid4().hex[:12]}",
                workspace_id=workspace.id,
                user_id=user.id,
                role="owner",
                created_at=now,
            )
            db.add_all([user, workspace, membership])
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
        with self.Session() as db:
            row = db.execute(
                select(WorkspaceRow, MembershipRow.role)
                .join(MembershipRow, MembershipRow.workspace_id == WorkspaceRow.id)
                .where(MembershipRow.user_id == user_id)
                .limit(1)
            ).first()
            if not row:
                return None
            workspace, membership_role = row
            return {**self._workspace_dict(workspace), "membership_role": membership_role}

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
