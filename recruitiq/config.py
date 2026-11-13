import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    db_url: str = field(default_factory=lambda: os.environ.get("RECRUITIQ_DB_URL", f"sqlite:///{ROOT / 'recruitiq.db'}"))
    # no default: the app refuses to start without it, so there is never a well-known signing key in production
    jwt_secret: str = field(default_factory=lambda: os.environ.get("RECRUITIQ_JWT_SECRET", ""))
    jwt_minutes: int = field(default_factory=lambda: int(os.environ.get("RECRUITIQ_JWT_MINUTES", "60")))
    # where candidates reach the interview portal. used to build the link in the invitation
    public_url: str = field(default_factory=lambda: os.environ.get("RECRUITIQ_PUBLIC_URL", "http://127.0.0.1:8000"))
    api_url: str = field(default_factory=lambda: os.environ.get("RECRUITIQ_API_URL", "http://127.0.0.1:8000"))
    cors_origins: list = field(default_factory=lambda: [o for o in os.environ.get("RECRUITIQ_CORS_ORIGINS", "").split(",") if o])
    webhook_secret: str = field(default_factory=lambda: os.environ.get("RECRUITIQ_WEBHOOK_SECRET", ""))
    retention_days: int = field(default_factory=lambda: int(os.environ.get("RECRUITIQ_RETENTION_DAYS", "180")))
    media_dir: str = field(default_factory=lambda: os.environ.get("RECRUITIQ_MEDIA_DIR", str(ROOT / "media")))
    max_media_mb: int = field(default_factory=lambda: int(os.environ.get("RECRUITIQ_MAX_MEDIA_MB", "15")))
    max_upload_mb: int = field(default_factory=lambda: int(os.environ.get("RECRUITIQ_MAX_UPLOAD_MB", "5")))
    # first admin, only used when there are no users yet
    bootstrap_user: str = field(default_factory=lambda: os.environ.get("RECRUITIQ_BOOTSTRAP_USER", ""))
    bootstrap_password: str = field(default_factory=lambda: os.environ.get("RECRUITIQ_BOOTSTRAP_PASSWORD", ""))
    # hosted demo: loads made-up sample candidates into an empty database and shows a notice in the dashboard
    demo: bool = field(default_factory=lambda: os.environ.get("RECRUITIQ_DEMO", "") == "1")
    # outgoing mail. empty means notifications can be drafted but not sent
    smtp_host: str = field(default_factory=lambda: os.environ.get("SMTP_HOST", ""))
    smtp_port: int = field(default_factory=lambda: int(os.environ.get("SMTP_PORT", "465")))
    smtp_user: str = field(default_factory=lambda: os.environ.get("SMTP_USER", ""))
    smtp_password: str = field(default_factory=lambda: os.environ.get("SMTP_PASSWORD", ""))
    mail_from: str = field(default_factory=lambda: os.environ.get("MAIL_FROM", ""))
    # reading applications from a mailbox. defaults reuse the SMTP login, which is the same Gmail account
    imap_host: str = field(default_factory=lambda: os.environ.get("IMAP_HOST", "imap.gmail.com"))
    imap_user: str = field(default_factory=lambda: os.environ.get("IMAP_USER", "") or os.environ.get("SMTP_USER", ""))
    imap_password: str = field(default_factory=lambda: os.environ.get("IMAP_PASSWORD", "") or os.environ.get("SMTP_PASSWORD", ""))
    inbox_folder: str = field(default_factory=lambda: os.environ.get("RECRUITIQ_INBOX_FOLDER", "INBOX"))
    # 0 means only when someone presses the button
    inbox_poll_seconds: int = field(default_factory=lambda: int(os.environ.get("RECRUITIQ_INBOX_POLL_SECONDS", "0")))
    # optional LLM helper. nothing in scoring uses it
    llm_models: list = field(default_factory=lambda: [m for m in os.environ.get("RECRUITIQ_LLM_MODELS", "").split(",") if m] or None)
    llm_web_models: list = field(default_factory=lambda: [m for m in os.environ.get("RECRUITIQ_LLM_WEB_MODELS", "").split(",") if m] or None)
    llm_api_key: str = field(default_factory=lambda: os.environ.get("OPENROUTER_API_KEY", ""))


def get_settings() -> Settings:
    return Settings()
