from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from maintenance_copilot.database import (
    AssetRow,
    ManualIngestJobRow,
    ManualModelBindingRow,
    SessionRow,
    WorkOrderNoteRow,
)
from maintenance_copilot.domain import (
    AssetMetadata,
    IngestManualRequest,
    ManualIngestJobRecord,
    ManualIngestJobStatus,
    ManualModelBinding,
    SessionRecord,
    SessionState,
)


class SessionRepository(Protocol):
    def get(self, session_id: str) -> SessionRecord | None:
        ...

    def create(
        self,
        *,
        tenant_id: str,
        user_id: str,
        machine_id: str,
        session_id: str | None = None,
        work_order_id: str | None = None,
    ) -> SessionRecord:
        ...

    def save(self, record: SessionRecord) -> SessionRecord:
        ...


class AssetCatalog(Protocol):
    def get(self, tenant_id: str, machine_id: str) -> AssetMetadata | None:
        ...

    def upsert(self, asset: AssetMetadata) -> AssetMetadata:
        ...


class ConversationCache(Protocol):
    def get_summary(self, session_id: str) -> str | None:
        ...

    def set_summary(self, session_id: str, summary: str) -> None:
        ...

    def set_evidence_ids(self, session_id: str, chunk_ids: list[str]) -> None:
        ...

    def ping(self) -> bool:
        ...


class ManualBindingRepository(Protocol):
    def upsert_active(
        self,
        *,
        tenant_id: str,
        machine_model: str,
        machine_family: str | None,
        doc_id: str,
        manual_version: str,
    ) -> ManualModelBinding:
        ...

    def get_active_version(
        self,
        tenant_id: str,
        machine_model: str,
        machine_family: str | None,
    ) -> str | None:
        ...


class ManualIngestJobRepository(Protocol):
    def create(self, tenant_id: str, request: IngestManualRequest) -> ManualIngestJobRecord:
        ...

    def get(self, job_id: str) -> ManualIngestJobRecord | None:
        ...

    def claim_next_pending(self) -> ManualIngestJobRecord | None:
        ...

    def mark_success(self, job_id: str, result: dict) -> ManualIngestJobRecord:
        ...

    def mark_failed(self, job_id: str, message: str) -> ManualIngestJobRecord:
        ...


class InMemorySessionRepository:
    def __init__(self) -> None:
        self._records: dict[str, SessionRecord] = {}

    def get(self, session_id: str) -> SessionRecord | None:
        record = self._records.get(session_id)
        return record.model_copy(deep=True) if record else None

    def create(
        self,
        *,
        tenant_id: str,
        user_id: str,
        machine_id: str,
        session_id: str | None = None,
        work_order_id: str | None = None,
    ) -> SessionRecord:
        now = datetime.now(UTC)
        record = SessionRecord(
            session_id=session_id or f"s_{uuid4().hex[:12]}",
            tenant_id=tenant_id,
            user_id=user_id,
            machine_id=machine_id,
            work_order_id=work_order_id,
            opened_at=now,
            updated_at=now,
        )
        self._records[record.session_id] = record
        return record.model_copy(deep=True)

    def save(self, record: SessionRecord) -> SessionRecord:
        self._records[record.session_id] = record.model_copy(deep=True)
        return record


class InMemoryBindingRepository:
    def __init__(self) -> None:
        self._bindings: dict[tuple[str, str, str | None], ManualModelBinding] = {}

    def upsert_active(
        self,
        *,
        tenant_id: str,
        machine_model: str,
        machine_family: str | None,
        doc_id: str,
        manual_version: str,
    ) -> ManualModelBinding:
        binding = ManualModelBinding(
            tenant_id=tenant_id,
            machine_model=machine_model,
            machine_family=machine_family,
            doc_id=doc_id,
            manual_version=manual_version,
            is_active=True,
            updated_at=datetime.now(UTC),
        )
        self._bindings[(tenant_id, machine_model, machine_family)] = binding
        return binding

    def get_active_version(
        self,
        tenant_id: str,
        machine_model: str,
        machine_family: str | None,
    ) -> str | None:
        binding = self._bindings.get((tenant_id, machine_model, machine_family))
        return binding.manual_version if binding else None


class InMemoryAssetCatalog:
    def __init__(self, binding_repo: ManualBindingRepository | None = None) -> None:
        self._assets: dict[tuple[str, str], AssetMetadata] = {}
        self._binding_repo = binding_repo or InMemoryBindingRepository()

    def get(self, tenant_id: str, machine_id: str) -> AssetMetadata | None:
        asset = self._assets.get((tenant_id, machine_id.lower()))
        if not asset:
            return None
        manual_version = self._binding_repo.get_active_version(
            tenant_id,
            asset.machine_model,
            asset.machine_family,
        )
        if manual_version:
            asset = asset.model_copy(update={"active_manual_version": manual_version})
        return asset

    def upsert(self, asset: AssetMetadata) -> AssetMetadata:
        self._assets[(asset.tenant_id, asset.machine_id.lower())] = asset
        return asset


class InMemoryConversationCache:
    def __init__(self) -> None:
        self._summaries: dict[str, str] = {}
        self._evidence_ids: dict[str, list[str]] = {}

    def get_summary(self, session_id: str) -> str | None:
        return self._summaries.get(session_id)

    def set_summary(self, session_id: str, summary: str) -> None:
        self._summaries[session_id] = summary

    def set_evidence_ids(self, session_id: str, chunk_ids: list[str]) -> None:
        self._evidence_ids[session_id] = chunk_ids

    def ping(self) -> bool:
        return True


class InMemoryManualIngestJobRepository:
    def __init__(self) -> None:
        self._jobs: dict[str, ManualIngestJobRecord] = {}

    def create(self, tenant_id: str, request: IngestManualRequest) -> ManualIngestJobRecord:
        now = datetime.now(UTC)
        job = ManualIngestJobRecord(
            job_id=f"job_{uuid4().hex[:12]}",
            tenant_id=tenant_id,
            status=ManualIngestJobStatus.PENDING,
            request=request,
            created_at=now,
            updated_at=now,
        )
        self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> ManualIngestJobRecord | None:
        return self._jobs.get(job_id)

    def claim_next_pending(self) -> ManualIngestJobRecord | None:
        for job in self._jobs.values():
            if job.status == ManualIngestJobStatus.PENDING:
                job.status = ManualIngestJobStatus.RUNNING
                job.started_at = datetime.now(UTC)
                job.updated_at = datetime.now(UTC)
                job.attempts += 1
                return job
        return None

    def mark_success(self, job_id: str, result: dict) -> ManualIngestJobRecord:
        job = self._jobs[job_id]
        job.status = ManualIngestJobStatus.SUCCEEDED
        job.result = result
        job.finished_at = datetime.now(UTC)
        job.updated_at = datetime.now(UTC)
        return job

    def mark_failed(self, job_id: str, message: str) -> ManualIngestJobRecord:
        job = self._jobs[job_id]
        job.status = ManualIngestJobStatus.FAILED
        job.error_message = message
        job.finished_at = datetime.now(UTC)
        job.updated_at = datetime.now(UTC)
        return job


class PostgresSessionRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def get(self, session_id: str) -> SessionRecord | None:
        with self.session_factory() as db:
            row = db.get(SessionRow, session_id)
            return self._to_model(row) if row else None

    def create(
        self,
        *,
        tenant_id: str,
        user_id: str,
        machine_id: str,
        session_id: str | None = None,
        work_order_id: str | None = None,
    ) -> SessionRecord:
        now = datetime.now(UTC)
        record = SessionRecord(
            session_id=session_id or f"s_{uuid4().hex[:12]}",
            tenant_id=tenant_id,
            user_id=user_id,
            machine_id=machine_id,
            work_order_id=work_order_id,
            opened_at=now,
            updated_at=now,
        )
        return self.save(record)

    def save(self, record: SessionRecord) -> SessionRecord:
        with self.session_factory() as db:
            row = db.get(SessionRow, record.session_id)
            if row is None:
                row = SessionRow(
                    session_id=record.session_id,
                    tenant_id=record.tenant_id,
                    user_id=record.user_id,
                    machine_id=record.machine_id,
                    work_order_id=record.work_order_id,
                    opened_at=record.opened_at,
                    updated_at=record.updated_at,
                    state=record.state.model_dump(mode="json"),
                    last_context_summary=record.last_context_summary,
                )
                db.add(row)
            else:
                row.tenant_id = record.tenant_id
                row.user_id = record.user_id
                row.machine_id = record.machine_id
                row.work_order_id = record.work_order_id
                row.opened_at = record.opened_at
                row.updated_at = record.updated_at
                row.state = record.state.model_dump(mode="json")
                row.last_context_summary = record.last_context_summary
            db.commit()
        return record

    def _to_model(self, row: SessionRow) -> SessionRecord:
        return SessionRecord(
            session_id=row.session_id,
            tenant_id=row.tenant_id,
            user_id=row.user_id,
            machine_id=row.machine_id,
            work_order_id=row.work_order_id,
            opened_at=row.opened_at,
            updated_at=row.updated_at,
            state=SessionState.model_validate(row.state),
            last_context_summary=row.last_context_summary,
        )


class PostgresBindingRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def upsert_active(
        self,
        *,
        tenant_id: str,
        machine_model: str,
        machine_family: str | None,
        doc_id: str,
        manual_version: str,
    ) -> ManualModelBinding:
        now = datetime.now(UTC)
        with self.session_factory() as db:
            rows = db.scalars(
                select(ManualModelBindingRow).where(
                    ManualModelBindingRow.tenant_id == tenant_id,
                    ManualModelBindingRow.machine_model == machine_model,
                )
            ).all()
            for row in rows:
                row.is_active = False
            row = ManualModelBindingRow(
                tenant_id=tenant_id,
                machine_model=machine_model,
                machine_family=machine_family,
                doc_id=doc_id,
                manual_version=manual_version,
                is_active=True,
                updated_at=now,
            )
            db.add(row)
            db.commit()
            return self._to_model(row)

    def get_active_version(
        self,
        tenant_id: str,
        machine_model: str,
        machine_family: str | None,
    ) -> str | None:
        with self.session_factory() as db:
            row = db.scalars(
                select(ManualModelBindingRow).where(
                    ManualModelBindingRow.tenant_id == tenant_id,
                    ManualModelBindingRow.machine_model == machine_model,
                    ManualModelBindingRow.is_active.is_(True),
                )
            ).first()
            return row.manual_version if row else None

    def _to_model(self, row: ManualModelBindingRow) -> ManualModelBinding:
        return ManualModelBinding(
            tenant_id=row.tenant_id,
            machine_model=row.machine_model,
            machine_family=row.machine_family,
            doc_id=row.doc_id,
            manual_version=row.manual_version,
            is_active=row.is_active,
            updated_at=row.updated_at,
        )


class PostgresAssetCatalog:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        binding_repo: ManualBindingRepository,
    ) -> None:
        self.session_factory = session_factory
        self.binding_repo = binding_repo

    def get(self, tenant_id: str, machine_id: str) -> AssetMetadata | None:
        with self.session_factory() as db:
            row = db.scalars(
                select(AssetRow).where(
                    AssetRow.tenant_id == tenant_id,
                    AssetRow.machine_id == machine_id,
                )
            ).first()
            if not row:
                return None
            asset = AssetMetadata(
                tenant_id=row.tenant_id,
                site_id=row.site_id,
                machine_id=row.machine_id,
                machine_model=row.machine_model,
                machine_family=row.machine_family,
                criticality=row.criticality,  # type: ignore[arg-type]
                active_manual_version=row.active_manual_version,
                aliases=list(row.aliases or []),
            )
            manual_version = self.binding_repo.get_active_version(
                tenant_id,
                asset.machine_model,
                asset.machine_family,
            )
            if manual_version:
                asset.active_manual_version = manual_version
            return asset

    def upsert(self, asset: AssetMetadata) -> AssetMetadata:
        with self.session_factory() as db:
            row = db.scalars(
                select(AssetRow).where(
                    AssetRow.tenant_id == asset.tenant_id,
                    AssetRow.machine_id == asset.machine_id,
                )
            ).first()
            if row is None:
                row = AssetRow(
                    tenant_id=asset.tenant_id,
                    site_id=asset.site_id,
                    machine_id=asset.machine_id,
                    machine_model=asset.machine_model,
                    machine_family=asset.machine_family,
                    criticality=asset.criticality,
                    active_manual_version=asset.active_manual_version,
                    aliases=asset.aliases,
                )
                db.add(row)
            else:
                row.site_id = asset.site_id
                row.machine_model = asset.machine_model
                row.machine_family = asset.machine_family
                row.criticality = asset.criticality
                row.active_manual_version = asset.active_manual_version
                row.aliases = asset.aliases
            db.commit()
        return asset


class PostgresManualIngestJobRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def create(self, tenant_id: str, request: IngestManualRequest) -> ManualIngestJobRecord:
        now = datetime.now(UTC)
        row = ManualIngestJobRow(
            job_id=f"job_{uuid4().hex[:12]}",
            tenant_id=tenant_id,
            status=ManualIngestJobStatus.PENDING.value,
            request_json=request.model_dump(mode="json"),
            created_at=now,
            updated_at=now,
            attempts=0,
        )
        with self.session_factory() as db:
            db.add(row)
            db.commit()
        return self._to_model(row)

    def get(self, job_id: str) -> ManualIngestJobRecord | None:
        with self.session_factory() as db:
            row = db.get(ManualIngestJobRow, job_id)
            return self._to_model(row) if row else None

    def claim_next_pending(self) -> ManualIngestJobRecord | None:
        with self.session_factory() as db:
            row = db.scalars(
                select(ManualIngestJobRow)
                .where(ManualIngestJobRow.status == ManualIngestJobStatus.PENDING.value)
                .order_by(ManualIngestJobRow.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            ).first()
            if row is None:
                return None
            row.status = ManualIngestJobStatus.RUNNING.value
            row.started_at = datetime.now(UTC)
            row.updated_at = datetime.now(UTC)
            row.attempts += 1
            db.commit()
            return self._to_model(row)

    def mark_success(self, job_id: str, result: dict) -> ManualIngestJobRecord:
        with self.session_factory() as db:
            row = db.get(ManualIngestJobRow, job_id)
            if row is None:
                raise ValueError(f"unknown manual ingest job {job_id}")
            row.status = ManualIngestJobStatus.SUCCEEDED.value
            row.result_json = result
            row.finished_at = datetime.now(UTC)
            row.updated_at = datetime.now(UTC)
            db.commit()
            return self._to_model(row)

    def mark_failed(self, job_id: str, message: str) -> ManualIngestJobRecord:
        with self.session_factory() as db:
            row = db.get(ManualIngestJobRow, job_id)
            if row is None:
                raise ValueError(f"unknown manual ingest job {job_id}")
            row.status = ManualIngestJobStatus.FAILED.value
            row.error_message = message
            row.finished_at = datetime.now(UTC)
            row.updated_at = datetime.now(UTC)
            db.commit()
            return self._to_model(row)

    def _to_model(self, row: ManualIngestJobRow) -> ManualIngestJobRecord:
        return ManualIngestJobRecord(
            job_id=row.job_id,
            tenant_id=row.tenant_id,
            status=ManualIngestJobStatus(row.status),
            request=IngestManualRequest.model_validate(row.request_json),
            created_at=row.created_at,
            updated_at=row.updated_at,
            started_at=row.started_at,
            finished_at=row.finished_at,
            attempts=row.attempts,
            error_message=row.error_message,
            result=row.result_json,
        )


class RedisConversationCache:
    def __init__(self, redis_url: str) -> None:
        import redis

        self._client = redis.Redis.from_url(redis_url, decode_responses=True)

    def get_summary(self, session_id: str) -> str | None:
        return self._client.get(f"copilot:summary:{session_id}")

    def set_summary(self, session_id: str, summary: str) -> None:
        self._client.set(f"copilot:summary:{session_id}", summary, ex=60 * 60 * 24)

    def set_evidence_ids(self, session_id: str, chunk_ids: list[str]) -> None:
        self._client.set(
            f"copilot:evidence:{session_id}",
            json.dumps(chunk_ids),
            ex=60 * 60 * 24,
        )

    def ping(self) -> bool:
        return bool(self._client.ping())


class LocalWorkOrderNoteWriter:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def write(
        self,
        work_order_id: str,
        note: str,
        *,
        tenant_id: str,
        session_id: str | None,
    ) -> None:
        row = WorkOrderNoteRow(
            note_id=f"note_{uuid4().hex[:12]}",
            tenant_id=tenant_id,
            work_order_id=work_order_id,
            session_id=session_id,
            note=note,
            created_at=datetime.now(UTC),
        )
        with self.session_factory() as db:
            db.add(row)
            db.commit()
