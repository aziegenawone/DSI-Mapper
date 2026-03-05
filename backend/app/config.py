from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "dsi_mapper"
    postgres_user: str = "dsi"
    postgres_password: str = "changeme"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # MinIO
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "dsi-mapper"

    # NodeODM
    nodeodm_url: str = "http://localhost:3000"

    # JWT
    jwt_secret: str = "change-this-to-a-random-secret"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # DJI
    dji_thermal_sdk_path: str = "./dji/thermal_sdk"

    # AI
    yolo_model_path: str = "./ai/models/panel_detector.pt"
    defect_model_path: str = "./ai/models/defect_classifier.pt"

    # Processing
    max_upload_size_mb: int = 5000
    celery_broker_url: str = "redis://localhost:6379/1"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
