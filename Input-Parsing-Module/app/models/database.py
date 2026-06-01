import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL not set in .env file")

# Fixed UUID for the placeholder "system" user used until real auth exists.
# uploaded_files.user_id is a FK to users.id, so this row must exist before any
# upload can be saved. Keep this in sync with upload_controller's default param.
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_USER_EMAIL = "default@baylearn.local"

# pool_pre_ping: transparently checks a connection is alive before using it and
# reconnects if Supabase's pooler dropped it while idle (the cause of random
# "server closed the connection unexpectedly" errors on upload).
# pool_recycle: proactively retire connections older than 5 min.
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency — yields a DB session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """Create all tables if they don't exist. Called once on app startup."""
    from app.models.db_models import User, UploadedFile, Section, Chunk  # noqa: F401
    Base.metadata.create_all(bind=engine)


def seed_default_user():
    """
    Ensure the placeholder system user exists so uploads (which default to
    DEFAULT_USER_ID) satisfy the uploaded_files.user_id foreign key.

    Idempotent: does nothing if the user is already present. Called once on
    startup, after create_tables().
    """
    from app.models.db_models import User
    db = SessionLocal()
    try:
        if db.get(User, DEFAULT_USER_ID) is None:
            db.add(User(
                id=DEFAULT_USER_ID,
                email=DEFAULT_USER_EMAIL,
                name="Default User",
                # Placeholder, non-functional credential. This user never logs in;
                # it only exists to satisfy the uploaded_files.user_id FK.
                password="!disabled-system-user",
            ))
            db.commit()
    finally:
        db.close()