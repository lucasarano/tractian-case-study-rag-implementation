from __future__ import annotations

import json
import logging
import os
from contextlib import ExitStack, asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

import tempfile

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import text

from maintenance_copilot.config import Settings, get_settings
from maintenance_copilot.database import build_session_factory
from maintenance_copilot.domain import (
    AnswerEnvelope,
    AnswerRequest,
    AssetMetadata,
    CreateSessionRequest,
    HealthResponse,
    IngestLogRequest,
    IngestManualRequest,
    IngestResult,
    ManualIngestJobRecord,
    ReadinessResponse,
    SessionRecord,
    VerifiedIdentity,
)
from maintenance_copilot.ingest import (
    LogIngestPipeline,
    ManualIngestJobProcessor,
    ManualIngestPipeline,
)
from maintenance_copilot.orchestration import CitationFirstAnswerComposer, DeterministicCopilot
from maintenance_copilot.providers import (
    DocumentAiLayoutParser,
    GeminiAnswerGenerator,
    GeminiIncidentNormalizer,
    GeminiVisualSummarizer,
    HashTextEmbedder,
    HeuristicReranker,
    InMemoryVectorStore,
    OktaJWTVerifier,
    PineconeVectorStore,
    StaticTokenVerifier,
    VertexRankingReranker,
    VertexTextEmbedder,
)
from maintenance_copilot.retrieval import RetrievalService
from maintenance_copilot.sessions import (
    InMemoryAssetCatalog,
    InMemoryBindingRepository,
    InMemoryConversationCache,
    InMemoryManualIngestJobRepository,
    InMemorySessionRepository,
    LocalWorkOrderNoteWriter,
    PostgresAssetCatalog,
    PostgresBindingRepository,
    PostgresManualIngestJobRepository,
    PostgresSessionRepository,
    RedisConversationCache,
)

logger = logging.getLogger(__name__)

MANUALS_DIR = Path("fixtures/manuals")
MANUAL_SOURCE_PDF = MANUALS_DIR / "kohler_generator_manual.pdf"
MANUAL_SUBSET_PAGE_COUNT = 50
MANUAL_SUBSET_PDF = MANUALS_DIR / f"kohler_generator_manual_first_{MANUAL_SUBSET_PAGE_COUNT}_pages.pdf"


def ensure_manual_subset() -> Path:
    if MANUAL_SUBSET_PDF.exists():
        return MANUAL_SUBSET_PDF
    if not MANUAL_SOURCE_PDF.exists():
        raise FileNotFoundError(f"manual source PDF not found at {MANUAL_SOURCE_PDF}")

    import fitz

    document = fitz.open(MANUAL_SOURCE_PDF)
    subset = fitz.open()
    last_page = min(document.page_count, MANUAL_SUBSET_PAGE_COUNT)
    subset.insert_pdf(document, from_page=0, to_page=last_page - 1)
    subset.save(MANUAL_SUBSET_PDF)
    subset.close()
    document.close()
    return MANUAL_SUBSET_PDF


@dataclass(slots=True)
class Container:
    settings: Settings
    token_verifier: Any
    session_repo: Any
    asset_catalog: Any
    cache: Any
    manual_job_repo: Any
    manual_ingest: ManualIngestPipeline
    manual_job_processor: ManualIngestJobProcessor
    log_ingest: LogIngestPipeline
    retrieval: RetrievalService
    copilot: DeterministicCopilot
    session_factory: Any | None = None
    checkpointer: Any | None = None

    def readiness(self) -> ReadinessResponse:
        checks: dict[str, str] = {
            "runtime_env": self.settings.runtime_env,
            "auth_mode": self.settings.auth_mode,
            "vector_backend": self.settings.vector_backend,
            "generation_backend": self.settings.generation_backend,
        }
        try:
            if self.session_factory is None:
                checks["database"] = "in_memory"
            else:
                with self.session_factory() as db:
                    db.execute(text("SELECT 1"))
                checks["database"] = "ok"
        except Exception as exc:  # pragma: no cover - defensive external check
            checks["database"] = f"error:{exc}"
        try:
            checks["redis"] = "ok" if self.cache.ping() else "error:ping-failed"
        except Exception as exc:  # pragma: no cover - defensive external check
            checks["redis"] = f"error:{exc}"
        checks["langgraph_checkpointer"] = "ok" if self.checkpointer else "disabled"
        status = "ready"
        if any(value.startswith("error:") for value in checks.values()):
            status = "not_ready"
        return ReadinessResponse(status=status, checks=checks)


def configure_logging(settings: Settings) -> None:
    if logging.getLogger().handlers:
        return
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def configure_observability(app: FastAPI, settings: Settings) -> None:
    if not settings.enable_otel or settings.runtime_env == "test":
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ModuleNotFoundError:  # pragma: no cover - optional dependency safety
        logger.warning("OpenTelemetry packages are not installed; tracing disabled")
        return

    provider = TracerProvider(
        resource=Resource.create({"service.name": settings.otel_service_name})
    )
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)


def load_seed_assets(asset_catalog: Any, path: str) -> None:
    seed_path = Path(path)
    if not seed_path.exists():
        return
    payload = json.loads(seed_path.read_text())
    assets = payload["assets"] if isinstance(payload, dict) and "assets" in payload else payload
    for raw_asset in assets:
        asset_catalog.upsert(AssetMetadata.model_validate(raw_asset))


def build_container(settings: Settings, *, exit_stack: ExitStack) -> Container:
    configure_logging(settings)
    if not settings.is_test:
        settings.validate_startup()

    if settings.is_test:
        binding_repo = InMemoryBindingRepository()
        asset_catalog = InMemoryAssetCatalog(binding_repo)
        session_repo = InMemorySessionRepository()
        cache = InMemoryConversationCache()
        manual_job_repo = InMemoryManualIngestJobRepository()
        embedder = HashTextEmbedder(dimensions=64)
        vector_store = InMemoryVectorStore()
        reranker = HeuristicReranker()
        token_verifier = StaticTokenVerifier(settings)
        answer_generator = None
        incident_normalizer = None
        parser = None
        visual_summarizer = None
        session_factory = None
        checkpointer = None
        work_order_writer = None
    else:
        session_factory = build_session_factory(settings.database_url or "")
        binding_repo = PostgresBindingRepository(session_factory)
        asset_catalog = PostgresAssetCatalog(session_factory, binding_repo)
        session_repo = PostgresSessionRepository(session_factory)
        cache = RedisConversationCache(settings.redis_url or "")
        manual_job_repo = PostgresManualIngestJobRepository(session_factory)
        embedder = (
            VertexTextEmbedder(settings)
            if settings.vector_backend == "pinecone"
            else HashTextEmbedder(dimensions=settings.text_embedding_dimensions)
        )
        vector_store = (
            PineconeVectorStore(settings)
            if settings.vector_backend == "pinecone"
            else InMemoryVectorStore()
        )
        reranker = (
            VertexRankingReranker(settings)
            if settings.vector_backend == "pinecone"
            else HeuristicReranker()
        )
        token_verifier = (
            OktaJWTVerifier(
                issuer=settings.okta_issuer or "",
                audience=settings.okta_audience or "",
            )
            if settings.auth_mode == "okta"
            else StaticTokenVerifier(settings)
        )
        answer_generator = (
            GeminiAnswerGenerator(settings)
            if settings.generation_backend == "gemini"
            else None
        )
        incident_normalizer = (
            GeminiIncidentNormalizer(settings)
            if settings.generation_backend == "gemini"
            else None
        )
        parser = DocumentAiLayoutParser(settings)
        visual_summarizer = (
            GeminiVisualSummarizer(settings)
            if settings.generation_backend == "gemini"
            else None
        )
        work_order_writer = LocalWorkOrderNoteWriter(session_factory)
        from langgraph.checkpoint.postgres import PostgresSaver

        pg_conn_string = (settings.database_url or "").replace(
            "postgresql+psycopg://", "postgresql://"
        )
        checkpointer = exit_stack.enter_context(
            PostgresSaver.from_conn_string(pg_conn_string)
        )
        try:
            checkpointer.setup()
        except Exception:
            pass

    manual_ingest = ManualIngestPipeline(
        embedder,
        vector_store,
        parser=parser,
        visual_summarizer=visual_summarizer,
        binding_repo=binding_repo,
        visual_low_text_threshold=settings.manual_visual_low_text_threshold,
    )
    manual_job_processor = ManualIngestJobProcessor(manual_job_repo, manual_ingest)
    log_ingest = LogIngestPipeline(
        embedder,
        vector_store,
        normalizer=incident_normalizer,
        confidence_threshold=settings.log_rules_confidence_threshold,
    )
    retrieval = RetrievalService(settings, embedder, vector_store, reranker)
    copilot = DeterministicCopilot(
        session_repo,
        asset_catalog,
        cache,
        retrieval,
        CitationFirstAnswerComposer(),
        answer_generator=answer_generator,
        work_order_writer=work_order_writer,
        checkpointer=checkpointer,
    )

    if settings.runtime_env == "local":
        load_seed_assets(asset_catalog, settings.local_asset_seed_path)

    return Container(
        settings=settings,
        token_verifier=token_verifier,
        session_repo=session_repo,
        asset_catalog=asset_catalog,
        cache=cache,
        manual_job_repo=manual_job_repo,
        manual_ingest=manual_ingest,
        manual_job_processor=manual_job_processor,
        log_ingest=log_ingest,
        retrieval=retrieval,
        copilot=copilot,
        session_factory=session_factory,
        checkpointer=checkpointer,
    )


def get_identity(
    request: Request,
    authorization: str | None = Header(default=None),
) -> VerifiedIdentity:
    container: Container = request.app.state.container
    token = None
    if authorization:
        scheme, _, value = authorization.partition(" ")
        token = value if scheme.lower() == "bearer" else authorization
    try:
        return container.token_verifier.verify(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


IdentityDep = Annotated[VerifiedIdentity, Depends(get_identity)]


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        exit_stack = ExitStack()
        container = build_container(config, exit_stack=exit_stack)
        app.state.container = container
        try:
            yield
        finally:
            exit_stack.close()

    app = FastAPI(title=config.app_name, lifespan=lifespan)
    configure_observability(app, config)

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id", f"req_{uuid4().hex[:12]}")
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

    @app.get("/healthz", response_model=HealthResponse)
    def healthz() -> HealthResponse:
        return HealthResponse(status="ok", environment=config.runtime_env)

    @app.get("/readyz", response_model=ReadinessResponse)
    def readyz(request: Request, response: Response) -> ReadinessResponse:
        container: Container = request.app.state.container
        readiness = container.readiness()
        if readiness.status != "ready":
            response.status_code = 503
        return readiness

    @app.post("/v1/sessions", response_model=SessionRecord)
    def create_session(
        payload: CreateSessionRequest,
        request: Request,
        identity: IdentityDep,
    ) -> SessionRecord:
        container: Container = request.app.state.container
        try:
            return container.copilot.create_session(identity, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/v1/copilot/answer", response_model=AnswerEnvelope)
    def answer(
        payload: AnswerRequest,
        request: Request,
        identity: IdentityDep,
    ) -> AnswerEnvelope:
        container: Container = request.app.state.container
        try:
            return container.copilot.answer(identity, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/v1/ingest/manuals", response_model=IngestResult)
    def ingest_manual(
        payload: IngestManualRequest,
        request: Request,
        identity: IdentityDep,
    ) -> IngestResult:
        container: Container = request.app.state.container
        return container.manual_ingest.ingest(payload, identity.tenant_id)

    @app.post("/v1/ingest/manuals/upload", response_model=IngestResult)
    def ingest_manual_upload(
        request: Request,
        identity: IdentityDep,
        file: UploadFile = File(...),
        doc_id: str = Form(...),
        manufacturer: str = Form("OEM"),
        machine_model: str = Form(...),
        manual_version: str = Form(...),
        machine_family: str | None = Form(None),
        activate_version: bool = Form(True),
    ) -> IngestResult:
        container: Container = request.app.state.container
        suffix = Path(file.filename or "upload.pdf").suffix or ".pdf"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file.file.read())
            tmp_path = tmp.name
        try:
            payload = IngestManualRequest(
                doc_id=doc_id,
                manufacturer=manufacturer,
                machine_model=machine_model,
                machine_family=machine_family,
                manual_version=manual_version,
                pdf_path=tmp_path,
                activate_version=activate_version,
            )
            return container.manual_ingest.ingest(payload, identity.tenant_id)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    @app.post("/v1/ingest/manuals/jobs", response_model=ManualIngestJobRecord)
    def create_manual_job(
        payload: IngestManualRequest,
        request: Request,
        identity: IdentityDep,
    ) -> ManualIngestJobRecord:
        container: Container = request.app.state.container
        return container.manual_job_repo.create(identity.tenant_id, payload)

    @app.get("/v1/ingest/manuals/jobs/{job_id}", response_model=ManualIngestJobRecord)
    def get_manual_job(
        job_id: str,
        request: Request,
        identity: IdentityDep,
    ) -> ManualIngestJobRecord:
        container: Container = request.app.state.container
        job = container.manual_job_repo.get(job_id)
        if job is None or job.tenant_id != identity.tenant_id:
            raise HTTPException(status_code=404, detail="manual ingest job not found")
        return job

    @app.get("/v1/manuals/loaded-subset-pdf")
    def get_loaded_subset_pdf() -> FileResponse:
        try:
            pdf_path = ensure_manual_subset()
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return FileResponse(
            path=pdf_path,
            media_type="application/pdf",
            filename=pdf_path.name,
            content_disposition_type="inline",
        )

    @app.post("/v1/ingest/logs", response_model=IngestResult)
    def ingest_log(
        payload: IngestLogRequest,
        request: Request,
        identity: IdentityDep,
    ) -> IngestResult:
        container: Container = request.app.state.container
        return container.log_ingest.ingest(payload, identity.tenant_id)

    return app
