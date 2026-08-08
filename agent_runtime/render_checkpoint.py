from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal
from uuid import uuid4


RenderMode = Literal["idea2video", "script2video", "novel2video"]
RenderStatus = Literal["awaiting_character_approval", "resuming", "completed"]
CHECKPOINT_FILENAME = "render_checkpoint.json"


@dataclass(slots=True)
class RoleVersionState:
    role_id: str
    role_version: int
    display_name: str = ""
    description: str = ""
    artifact_paths: dict[str, str] = field(default_factory=dict)
    approved: bool = False


@dataclass(slots=True)
class RenderCheckpoint:
    run_id: str
    session_id: str
    mode: RenderMode
    status: RenderStatus
    roles: dict[str, RoleVersionState]
    resume_started: bool = False

    @property
    def ready_to_resume(self) -> bool:
        return (
            self.status == "awaiting_character_approval"
            and bool(self.roles)
            and all(role.approved for role in self.roles.values())
        )

    def role(self, role_id: str, role_version: int) -> RoleVersionState:
        role = self.roles.get(role_id)
        if role is None:
            raise ValueError(f"未知角色: {role_id}")
        if role.role_version != role_version:
            raise ValueError(f"角色 {role_id} 的当前版本是 v{role.role_version}")
        return role

    def confirm(self, role_id: str, role_version: int) -> bool:
        if self.status != "awaiting_character_approval":
            raise ValueError("当前渲染不在等待角色确认")
        role = self.role(role_id, role_version)
        if role.approved:
            return False
        role.approved = True
        return True

    def replace_role_version(
        self,
        role_id: str,
        role_version: int,
        *,
        display_name: str | None = None,
        description: str | None = None,
        artifact_paths: dict[str, str] | None = None,
    ) -> RoleVersionState:
        current = self.role(role_id, role_version)
        replacement = RoleVersionState(
            role_id=role_id,
            role_version=current.role_version + 1,
            display_name=current.display_name if display_name is None else display_name,
            description=current.description if description is None else description,
            artifact_paths=dict(artifact_paths or {}),
        )
        self.roles[role_id] = replacement
        return replacement

    def begin_resume(self) -> bool:
        if not self.ready_to_resume or self.resume_started:
            return False
        self.status = "resuming"
        self.resume_started = True
        return True

    def mark_completed(self) -> None:
        self.status = "completed"


def save_checkpoint(session_root: Path, checkpoint: RenderCheckpoint) -> None:
    session_root.mkdir(parents=True, exist_ok=True)
    target = session_root / CHECKPOINT_FILENAME
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    payload = {
        "run_id": checkpoint.run_id,
        "session_id": checkpoint.session_id,
        "mode": checkpoint.mode,
        "status": checkpoint.status,
        "resume_started": checkpoint.resume_started,
        "roles": {role_id: asdict(role) for role_id, role in checkpoint.roles.items()},
    }
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def load_checkpoint(session_root: Path, run_id: str) -> RenderCheckpoint:
    target = session_root / CHECKPOINT_FILENAME
    payload = json.loads(target.read_text(encoding="utf-8"))
    if payload.get("run_id") != run_id:
        raise ValueError("checkpoint 与当前运行不匹配")
    raw_roles = payload.get("roles")
    if not isinstance(raw_roles, dict):
        raise ValueError("checkpoint 缺少角色状态")
    roles = {
        str(role_id): RoleVersionState(
            role_id=str(value.get("role_id") or role_id),
            role_version=int(value["role_version"]),
            display_name=str(value.get("display_name") or ""),
            description=str(value.get("description") or ""),
            artifact_paths={str(view): str(path) for view, path in dict(value.get("artifact_paths") or {}).items()},
            approved=bool(value.get("approved", False)),
        )
        for role_id, value in raw_roles.items()
        if isinstance(value, dict)
    }
    return RenderCheckpoint(
        run_id=str(payload["run_id"]),
        session_id=str(payload["session_id"]),
        mode=payload["mode"],
        status=payload["status"],
        roles=roles,
        resume_started=bool(payload.get("resume_started", False)),
    )
