
from __future__ import annotations

import uuid as _uuid_module
from sqlalchemy import (
    Column, String, Integer, Float, Boolean,
    Text, DateTime, ForeignKey, JSON,
    create_engine, text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def _uuid() -> str:
    return str(_uuid_module.uuid4())


class User(Base):
    __tablename__ = "users"

    id    = Column(String, primary_key=True, default=_uuid)
    email  = Column(String, unique=True, nullable=False)
    username   = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, nullable=False,
                        server_default=text("NOW()"))

    enrollments   = relationship("CourseEnrollment", back_populates="user",
                                 cascade="all, delete-orphan")
    pfa_states    = relationship("StudentPFAState",   back_populates="user",
                                 cascade="all, delete-orphan")
    sessions    = relationship("Session",           back_populates="user",
                                 cascade="all, delete-orphan")

class Course(Base):
    __tablename__ = "courses"

    id     = Column(String, primary_key=True, default=_uuid)
    name  = Column(String, unique=True, nullable=False)
    description = Column(Text,   nullable=True)
    created_at  = Column(DateTime, nullable=False,
                         server_default=text("NOW()"))

    concepts    = relationship("Concept", back_populates="course",
                               cascade="all, delete-orphan")
    enrollments = relationship("CourseEnrollment", back_populates="course",
                               cascade="all, delete-orphan")

class CourseEnrollment(Base):
    __tablename__ = "course_enrollments"

    user_id   = Column(String, ForeignKey("users.id",   ondelete="CASCADE"),
                       primary_key=True)
    course_id = Column(String, ForeignKey("courses.id", ondelete="CASCADE"),
                       primary_key=True)

    user   = relationship("User",   back_populates="enrollments")
    course = relationship("Course", back_populates="enrollments")

class Session(Base):
    __tablename__ = "sessions"

    id     = Column(String, primary_key=True, default=_uuid)
    user_id      = Column(String, ForeignKey("users.id", ondelete="CASCADE"),
                                 nullable=False)
    scope_type     = Column(String, nullable=False)
    scope_ids      = Column(String, nullable=False)   # comma separeted
    started_at  = Column(DateTime, nullable=False,
                                 server_default=text("NOW()"))
    ended_at     = Column(DateTime, nullable=True)
    terminate_requested = Column(Boolean, nullable=False,
                                 server_default=text("FALSE"))

    user   = relationship("User", back_populates="sessions")
    interactions = relationship("SessionInteraction",
                                back_populates="session",
                                cascade="all, delete-orphan")

class Concept(Base):
    __tablename__ = "concepts"

    id           = Column(String, primary_key=True, default=_uuid)
    course_id    = Column(String, ForeignKey("courses.id", ondelete="CASCADE"),
                          nullable=False)
    name    = Column(String,  nullable=False)
    difficulty   = Column(Integer, nullable=False)
    aliases      = Column(JSON,    nullable=False, server_default=text("'[]'"))
    concept_type = Column(String,  nullable=False, server_default=text("'unknown'"))

    course = relationship("Course",       back_populates="concepts")
    file_links   = relationship("ConceptFile",  back_populates="concept",
                                  cascade="all, delete-orphan")
    pfa_states   = relationship("StudentPFAState",
                                  back_populates="concept",
                                  cascade="all, delete-orphan")
    interactions   = relationship("SessionInteraction",    back_populates="concept")
# to save concepts
class ConceptFile(Base):
    __tablename__ = "concept_files"

    concept_id = Column(String, ForeignKey("concepts.id", ondelete="CASCADE"),
                        primary_key=True)
    file_id    = Column(String, primary_key=True)   # chunk DB file uuid

    concept = relationship("Concept", back_populates="file_links")

# el 7ala bta3et el taleb
class StudentPFAState(Base):
    __tablename__ = "student_pfa_state"

    user_id    = Column(String, ForeignKey("users.id",    ondelete="CASCADE"),  primary_key=True)
    concept_id = Column(String, ForeignKey("concepts.id", ondelete="CASCADE"),primary_key=True)

    succ_easy  = Column(Float, nullable=False, server_default=text("0"))
    succ_med   = Column(Float, nullable=False, server_default=text("0"))
    succ_hard  = Column(Float, nullable=False, server_default=text("0"))
    fail_easy  = Column(Float, nullable=False, server_default=text("0"))
    fail_med   = Column(Float, nullable=False, server_default=text("0"))
    fail_hard  = Column(Float, nullable=False, server_default=text("0"))
    bonus_easy = Column(Float, nullable=False, server_default=text("0"))
    bonus_med  = Column(Float, nullable=False, server_default=text("0"))
    bonus_hard = Column(Float, nullable=False, server_default=text("0"))
    updated_at = Column(DateTime, nullable=False,
                        server_default=text("NOW()"))

    user    = relationship("User",    back_populates="pfa_states")
    concept = relationship("Concept", back_populates="pfa_states")


class SessionInteraction(Base):
    __tablename__ = "session_interactions"

    id           = Column(String, primary_key=True, default=_uuid)
    session_id   = Column(String, ForeignKey("sessions.id",  ondelete="CASCADE"),        nullable=False)
    user_id    = Column(String, ForeignKey("users.id",     ondelete="CASCADE"),  nullable=False)
    concept_id   = Column(String, ForeignKey("concepts.id",  ondelete="CASCADE"),  nullable=False)
    difficulty   = Column(String(10), nullable=False)
    correct   = Column(Boolean,   nullable=False)
    p_before     = Column(Float,  nullable=False)
    p_after    = Column(Float,  nullable=False)
    p_hard_after = Column(Float,  nullable=False)
    created_at   = Column(DateTime,   nullable=False, server_default=text("NOW()"))

    session = relationship("Session", back_populates="interactions")
    concept = relationship("Concept", back_populates="interactions")


# 3ashan el prere
class KnowledgeNode(Base):
    __tablename__ = "knowledge_nodes"

    id  = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    description  = Column(Text, nullable=True)
    aliases = Column(JSON, nullable=False, server_default=text("'[]'"))
    concept_type = Column(String,nullable=False, server_default=text("'unknown'"))
    source  = Column(String, nullable=False)  
    source_id  = Column(String,nullable=True)    

    outgoing_edges = relationship("KnowledgeEdge", foreign_keys="KnowledgeEdge.from_node_id",  back_populates="from_node", cascade="all, delete-orphan")
    incoming_edges = relationship("KnowledgeEdge", foreign_keys="KnowledgeEdge.to_node_id",  back_populates="to_node",  cascade="all, delete-orphan")
    concept_mappings = relationship("ConceptNodeMapping", back_populates="node",  cascade="all, delete-orphan")

class KnowledgeEdge(Base):
    __tablename__ = "knowledge_edges"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    from_node_id = Column(Integer, ForeignKey("knowledge_nodes.id",  ondelete="CASCADE"),
                          nullable=False)
    to_node_id   = Column(Integer, ForeignKey("knowledge_nodes.id",  ondelete="CASCADE"),
                          nullable=False)
    source       = Column(String,  nullable=False)  

    from_node = relationship("KnowledgeNode", foreign_keys=[from_node_id],
                              back_populates="outgoing_edges")
    to_node   = relationship("KnowledgeNode", foreign_keys=[to_node_id],
                              back_populates="incoming_edges")



class ConceptNodeMapping(Base):
    __tablename__ = "concept_node_mappings"
    concept_id  = Column(String,  ForeignKey("concepts.id",  ondelete="CASCADE"), primary_key=True)
    node_id  = Column(Integer, ForeignKey("knowledge_nodes.id",ondelete="CASCADE"), primary_key=True)
    confidence  = Column(Float,  nullable=False)
    match_type  = Column(String, nullable=False)   

    concept = relationship("Concept")
    node    = relationship("KnowledgeNode", back_populates="concept_mappings")



def ensure_tables(db_url: str) -> None:
    """
    create tables if not exist call at the startup
    """
    engine = create_engine(db_url)
    with engine.connect() as conn:

   
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id         VARCHAR PRIMARY KEY,
                email      VARCHAR NOT NULL UNIQUE,
                username   VARCHAR NOT NULL UNIQUE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS courses (
                id          VARCHAR PRIMARY KEY,
                name        VARCHAR NOT NULL UNIQUE,
                description TEXT,
                created_at  TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS course_enrollments (
                user_id   VARCHAR NOT NULL REFERENCES users(id)   ON DELETE CASCADE,
                course_id VARCHAR NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                PRIMARY KEY (user_id, course_id)
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS concepts (
                id           VARCHAR PRIMARY KEY,
                course_id    VARCHAR NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                name         TEXT    NOT NULL,
                difficulty   INTEGER NOT NULL,
                aliases      JSONB   NOT NULL DEFAULT '[]',
                concept_type TEXT    NOT NULL DEFAULT 'unknown'
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS concept_files (
                concept_id VARCHAR NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
                file_id    VARCHAR NOT NULL,
                PRIMARY KEY (concept_id, file_id)
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sessions (
                id                  VARCHAR PRIMARY KEY,
                user_id             VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                scope_ids           VARCHAR NOT NULL,
                started_at          TIMESTAMP NOT NULL DEFAULT NOW(),
                ended_at            TIMESTAMP,
                result_json         TEXT,
                terminate_requested BOOLEAN NOT NULL DEFAULT FALSE
            )
        """))

        conn.execute(text("""
            ALTER TABLE sessions
                ADD COLUMN IF NOT EXISTS terminate_requested BOOLEAN NOT NULL DEFAULT FALSE
        """))


        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS student_pfa_state (
                user_id    VARCHAR NOT NULL REFERENCES users(id)    ON DELETE CASCADE,
                concept_id VARCHAR NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
                succ_easy  FLOAT NOT NULL DEFAULT 0,
                succ_med   FLOAT NOT NULL DEFAULT 0,
                succ_hard  FLOAT NOT NULL DEFAULT 0,
                fail_easy  FLOAT NOT NULL DEFAULT 0,
                fail_med   FLOAT NOT NULL DEFAULT 0,
                fail_hard  FLOAT NOT NULL DEFAULT 0,
                bonus_easy FLOAT NOT NULL DEFAULT 0,
                bonus_med  FLOAT NOT NULL DEFAULT 0,
                bonus_hard FLOAT NOT NULL DEFAULT 0,
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                PRIMARY KEY (user_id, concept_id)
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS session_interactions (
                id           VARCHAR PRIMARY KEY,
                session_id   VARCHAR NOT NULL REFERENCES sessions(id)  ON DELETE CASCADE,
                user_id      VARCHAR NOT NULL REFERENCES users(id)     ON DELETE CASCADE,
                concept_id   VARCHAR NOT NULL REFERENCES concepts(id)  ON DELETE CASCADE,
                difficulty   VARCHAR(10) NOT NULL,
                correct      BOOLEAN     NOT NULL,
                p_before     FLOAT       NOT NULL,
                p_after      FLOAT       NOT NULL,
                p_hard_after FLOAT       NOT NULL,
                created_at   TIMESTAMP   NOT NULL DEFAULT NOW()
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS knowledge_nodes (
                id           SERIAL  PRIMARY KEY,
                name         TEXT    NOT NULL,
                description  TEXT,
                aliases      JSONB   NOT NULL DEFAULT '[]',
                concept_type TEXT    NOT NULL DEFAULT 'unknown',
                source       TEXT    NOT NULL,
                source_id    TEXT,
                UNIQUE (source, source_id)
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS knowledge_edges (
                id           SERIAL  PRIMARY KEY,
                from_node_id INTEGER NOT NULL
                    REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
                to_node_id   INTEGER NOT NULL
                    REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
                source       TEXT    NOT NULL,
                UNIQUE (from_node_id, to_node_id)
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS concept_node_mappings (
                concept_id VARCHAR NOT NULL
                    REFERENCES concepts(id) ON DELETE CASCADE,
                node_id    INTEGER NOT NULL
                    REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
                confidence FLOAT   NOT NULL,
                match_type TEXT    NOT NULL
                    CHECK (match_type IN
                           ('exact_name', 'exact_alias', 'semantic')),
                PRIMARY KEY (concept_id, node_id)
            )
        """))

        conn.commit()
    print("[db] All adaptive learning tables verified.")