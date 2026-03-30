from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

RuntimeEnv = Literal["local", "test", "staging", "prod"]
AuthMode = Literal["dev", "okta"]
VectorBackend = Literal["pinecone", "in_memory"]
GenerationBackend = Literal["gemini", "heuristic"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="COPILOT_",
        env_file=".env",
        extra="ignore",
    )

    app_name: str = "maintenance-copilot"
    runtime_env: RuntimeEnv = "local"
    auth_mode: AuthMode = "dev"
    vector_backend: VectorBackend = "pinecone"
    generation_backend: GenerationBackend = "gemini"
    log_level: str = "INFO"

    dev_tenant_id: str = "companyA"
    dev_user_id: str = "tech-001"

    okta_issuer: str | None = None
    okta_audience: str | None = None

    google_project: str | None = None
    google_location: str = "us-central1"
    documentai_location: str = "us"
    documentai_layout_processor_id: str | None = None
    documentai_ocr_processor_id: str | None = None

    text_embedding_model: str = "gemini-embedding-001"
    text_embedding_dimensions: int = 768
    multimodal_embedding_model: str = "multimodalembedding@001"
    multimodal_embedding_dimensions: int = 1408
    generation_flash_model: str = "gemini-2.5-flash"
    generation_pro_model: str = "gemini-2.5-pro"

    ranking_location: str = "global"
    ranking_config: str = "default_ranking_config"
    ranking_model_fast: str = "semantic-ranker-fast@latest"
    ranking_model_default: str = "semantic-ranker-default@latest"

    pinecone_api_key: str | None = None
    pinecone_manual_index: str = "oem-manuals"
    pinecone_log_index: str = "historical-insights"

    database_url: str | None = None
    redis_url: str | None = None
    worker_poll_interval_seconds: int = 5

    request_timeout_seconds: int = 30
    retrieval_top_k: int = 50
    answer_top_n: int = 12
    min_manual_evidence: int = 4
    min_log_evidence: int = 2
    low_confidence_threshold: float = 0.55
    log_rules_confidence_threshold: float = 0.75

    visual_summary_max_items: int = 3
    manual_visual_low_text_threshold: int = 80
    local_asset_seed_path: str = "fixtures/assets.json"
    local_sample_manual_request_path: str = "fixtures/manual_job.json"
    local_sample_log_request_path: str = "fixtures/log_incident.json"

    enable_otel: bool = True
    otel_service_name: str = "maintenance-copilot"

    @property
    def is_test(self) -> bool:
        return self.runtime_env == "test"

    @property
    def uses_managed_providers(self) -> bool:
        return self.vector_backend == "pinecone" or self.generation_backend == "gemini"

    @model_validator(mode="after")
    def validate_runtime_modes(self) -> Settings:
        if self.runtime_env in {"staging", "prod"} and self.auth_mode != "okta":
            raise ValueError("staging/prod require COPILOT_AUTH_MODE=okta")
        if self.runtime_env == "test":
            self.vector_backend = "in_memory"
            self.generation_backend = "heuristic"
            self.auth_mode = "dev"
        if self.auth_mode == "okta" and (
            not self.okta_issuer or not self.okta_audience
        ):
            raise ValueError(
                "COPILOT_OKTA_ISSUER and COPILOT_OKTA_AUDIENCE are required "
                "when COPILOT_AUTH_MODE=okta"
            )
        return self

    def managed_provider_requirements(self) -> dict[str, str | None]:
        return {
            "COPILOT_GOOGLE_PROJECT": self.google_project,
            "COPILOT_DOCUMENTAI_LAYOUT_PROCESSOR_ID": self.documentai_layout_processor_id,
            "COPILOT_PINECONE_API_KEY": self.pinecone_api_key,
            "COPILOT_DATABASE_URL": self.database_url,
            "COPILOT_REDIS_URL": self.redis_url,
        }

    def validate_startup(self) -> None:
        if self.is_test:
            return
        missing = [
            key
            for key, value in self.managed_provider_requirements().items()
            if not value
        ]
        if missing:
            raise ValueError(
                "Missing required startup configuration: " + ", ".join(sorted(missing))
            )
        if self.runtime_env == "local" and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            raise ValueError(
                "GOOGLE_APPLICATION_CREDENTIALS is required in local runtime for "
                "Vertex AI and Document AI access"
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
