import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL not set in .env file")

DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_USER_EMAIL = "default@baylearn.local"


engine =create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)

SessionLocal= sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base =declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """create all tables if they doesn't exist only called once at startup"""
    from app.models.db_models import User, UploadedFile, Section, Chunk  # noqa: F401
    Base.metadata.create_all(bind=engine)


def seed_default_user():
    """Adds the place holder user to satisfy the uploaded_files.user_id foreign key
    """
    from app.models.db_models import User
    db = SessionLocal()
    try:
        if db.get(User, DEFAULT_USER_ID) is None:
            db.add(User(
                id=DEFAULT_USER_ID,
                email=DEFAULT_USER_EMAIL,
                name="Default User",
                password="!disabled-system-user",
            ))
            db.commit()
    finally:
        db.close()