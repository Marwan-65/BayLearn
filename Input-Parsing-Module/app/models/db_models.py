import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Text, DateTime,
    ForeignKey, JSON
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID

from app.models.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    email = Column(String, unique=True, nullable=False)
    name   =Column(String, nullable=True)
    password   =Column(String, nullable=False)
    created_at =   Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    courses   = relationship("Course", back_populates="user", cascade="all, delete-orphan")
    files   =   relationship("UploadedFile", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User id={self.id} email={self.email}>"


class Course(Base):
    __tablename__ = "courses"

    id  = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id     = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name  = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user  = relationship("User", back_populates="courses")
    files = relationship("UploadedFile", back_populates="course", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Course id={self.id} name={self.name}>"


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id   = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id  = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    course_id       = Column(UUID(as_uuid=False), ForeignKey("courses.id", ondelete="SET NULL"), nullable=True)
    file_name    = Column(String, nullable=False)
    file_type    = Column(String, nullable=False)
    source_type     = Column(String, nullable=False)
    title  = Column(String, nullable=True)
    file_path    = Column(String, nullable=False)
    total_chunks    = Column(Integer, default=0)
    uploaded_at  = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user  = relationship("User", back_populates="files")
    course   = relationship("Course", back_populates="files")
    sections = relationship("Section", back_populates="file", cascade="all, delete-orphan")
    chunks   = relationship("Chunk", back_populates="file", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<UploadedFile id={self.id} title={self.title} type={self.source_type}>"


class Section(Base):
    __tablename__ = "sections"

    id              = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    file_id  = Column(UUID(as_uuid=False), ForeignKey("uploaded_files.id", ondelete="CASCADE"), nullable=False)
    heading       = Column(String, nullable=True)
    page            = Column(Integer, nullable=True)
    section_index =Column(Integer, nullable=False)

    # Relationships
    file     = relationship("UploadedFile", back_populates="sections")
    chunks =    relationship("Chunk", back_populates="section", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Section id={self.id} heading={self.heading} page={self.page}>"


class Chunk(Base):
    __tablename__ = "chunks"

    id   =  Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    section_id     =Column(UUID(as_uuid=False), ForeignKey("sections.id", ondelete="CASCADE"), nullable=False)
    file_id     = Column(UUID(as_uuid=False), ForeignKey("uploaded_files.id", ondelete="CASCADE"), nullable=False)
    conten  =Column(Text, nullable=False)
    chunk_index    = Column(Integer, nullable=False)
    chunk_type    =Column(String, nullable=True)
    chunk_metadata  =Column(JSON, nullable=True)

    # Relationships
    section = relationship("Section", back_populates="chunks")
    file = relationship("UploadedFile", back_populates="chunks")

    def __repr__(self):
        return f"<Chunk id={self.id} index={self.chunk_index} type={self.chunk_type}>"