from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "CognAI API"
    
    # DB connections with local fallbacks
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgrespassword@localhost:5432/cognai"
    REDIS_URL: str = "redis://localhost:6379/0"
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "neo4jpassword"
    
    # LLM API Keys
    GROQ_API_KEY: str | None = None
    GEMINI_API_KEY: str | None = None

    CLOUDFLARE_ACCOUNT_ID: str | None = None
    CLOUDFLARE_API_TOKEN: str | None = None
    CLOUDFLARE_MODEL: str = "@cf/meta/llama-3.1-8b-instruct-fp8"
    
    LLM_PROVIDER: str = "bedrock"
    
    # AWS Bedrock
    AWS_BEDROCK_API_KEY: str | None = None
    AWS_REGION: str = "us-east-1"
    AWS_BEDROCK_MODEL: str = "global.amazon.nova-2-lite-v1:0"
    AWS_BEDROCK_VISION_MODEL: str = "global.amazon.nova-2-lite-v1:0"
    
    # Auth
    SECRET_KEY: str = "super_secret_development_key_change_me_in_prod"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8 # 8 days
    
    # Google OAuth2
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None

    # SMTP Configuration
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM_EMAIL: str = "noreply@cognai.local"

    model_config = SettingsConfigDict(env_file=(".env", ".env.local"), extra="ignore")

settings = Settings()
