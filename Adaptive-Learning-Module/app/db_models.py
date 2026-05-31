"""
models.py
=========
SQLAlchemy ORM models for the Adaptive Learning DB.
All primary keys are UUIDs to match the Chunk DB conventions.

Also exports `ensure_tables(db_url)` which creates all tables
that don't exist yet — safe to call on every startup.

Adaptive Learning DB schema:

  users               — mirrors chunk DB users (same UUID)
  courses             — mirrors chunk DB courses (same UUID)
  course_enrollments  — user ↔ course enrollment
  concepts            — extracted from files, belong to a course
  concept_files       — links concepts to the chunk DB files they came from
  sessions            — one row per adaptive session
  student_pfa_state   — PFA counts per (user, concept)
  session_interactions— one row per question step

Dependencies:
    pip install sqlalchemy psycopg2-binary
"""

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


# ---------------------------------------------------------------------------
# users
# UUID mirrors the chunk DB user UUID so the same user ID works in both DBs.
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id         = Column(String, primary_key=True, default=_uuid)
    email      = Column(String, unique=True, nullable=False)
    username   = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, nullable=False,
                        server_default=text("NOW()"))

    enrollments   = relationship("CourseEnrollment", back_populates="user",
                                 cascade="all, delete-orphan")
    pfa_states    = relationship("StudentPFAState",   back_populates="user",
                                 cascade="all, delete-orphan")
    sessions      = relationship("Session",           back_populates="user",
                                 cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# courses
# UUID mirrors the chunk DB course UUID so course_id is portable.
# name is UNIQUE — used as the human-readable link when needed.
# ---------------------------------------------------------------------------
class Course(Base):
    __tablename__ = "courses"

    id          = Column(String, primary_key=True, default=_uuid)
    name        = Column(String, unique=True, nullable=False)
    description = Column(Text,   nullable=True)
    created_at  = Column(DateTime, nullable=False,
                         server_default=text("NOW()"))

    concepts    = relationship("Concept", back_populates="course",
                               cascade="all, delete-orphan")
    enrollments = relationship("CourseEnrollment", back_populates="course",
                               cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# course_enrollments
# ---------------------------------------------------------------------------
class CourseEnrollment(Base):
    __tablename__ = "course_enrollments"

    user_id   = Column(String, ForeignKey("users.id",   ondelete="CASCADE"),
                       primary_key=True)
    course_id = Column(String, ForeignKey("courses.id", ondelete="CASCADE"),
                       primary_key=True)

    user   = relationship("User",   back_populates="enrollments")
    course = relationship("Course", back_populates="enrollments")


# ---------------------------------------------------------------------------
# concepts
# ---------------------------------------------------------------------------
class Concept(Base):
    __tablename__ = "concepts"

    id           = Column(String, primary_key=True, default=_uuid)
    course_id    = Column(String, ForeignKey("courses.id", ondelete="CASCADE"),
                          nullable=False)
    name         = Column(String,  nullable=False)
    difficulty   = Column(Integer, nullable=False)
    aliases      = Column(JSON,    nullable=False, server_default=text("'[]'"))
    concept_type = Column(String,  nullable=False, server_default=text("'unknown'"))

    course         = relationship("Course",       back_populates="concepts")
    file_links     = relationship("ConceptFile",  back_populates="concept",
                                  cascade="all, delete-orphan")
    pfa_states     = relationship("StudentPFAState",
                                  back_populates="concept",
                                  cascade="all, delete-orphan")
    interactions   = relationship("SessionInteraction",
                                  back_populates="concept")


# ---------------------------------------------------------------------------
# concept_files
# Links a concept to the chunk DB files it was extracted from.
# Enables scope_type=files sessions to find the right concept subset.
# concept_id : UUID of the concept in this DB
# file_id    : UUID of the file in the chunk DB (stored as varchar)
# ---------------------------------------------------------------------------
class ConceptFile(Base):
    __tablename__ = "concept_files"

    concept_id = Column(String, ForeignKey("concepts.id", ondelete="CASCADE"),
                        primary_key=True)
    file_id    = Column(String, primary_key=True)   # chunk DB file UUID

    concept = relationship("Concept", back_populates="file_links")


# ---------------------------------------------------------------------------
# sessions
# scope_type  : "course" | "files"
# scope_ids   : comma-separated chunk DB UUIDs (course UUIDs or file UUIDs)
#               exactly what the frontend sent — stored for audit/replay
# ---------------------------------------------------------------------------
class Session(Base):
    __tablename__ = "sessions"

    id         = Column(String, primary_key=True, default=_uuid)
    user_id    = Column(String, ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False)
    scope_type = Column(String, nullable=False)
    scope_ids  = Column(String, nullable=False)   # comma-separated UUIDs
    started_at = Column(DateTime, nullable=False,
                        server_default=text("NOW()"))
    ended_at   = Column(DateTime, nullable=True)

    user         = relationship("User", back_populates="sessions")
    interactions = relationship("SessionInteraction",
                                back_populates="session",
                                cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# student_pfa_state
# One row per (user, concept). Updated at the end of every session.
# Stores raw PFA counts — probabilities are computed on the fly.
# ---------------------------------------------------------------------------
class StudentPFAState(Base):
    __tablename__ = "student_pfa_state"

    user_id    = Column(String, ForeignKey("users.id",    ondelete="CASCADE"),
                        primary_key=True)
    concept_id = Column(String, ForeignKey("concepts.id", ondelete="CASCADE"),
                        primary_key=True)

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


# ---------------------------------------------------------------------------
# session_interactions
# One row per question step inside a session.
# ---------------------------------------------------------------------------
class SessionInteraction(Base):
    __tablename__ = "session_interactions"

    id           = Column(String, primary_key=True, default=_uuid)
    session_id   = Column(String, ForeignKey("sessions.id",  ondelete="CASCADE"),
                          nullable=False)
    user_id      = Column(String, ForeignKey("users.id",     ondelete="CASCADE"),
                          nullable=False)
    concept_id   = Column(String, ForeignKey("concepts.id",  ondelete="CASCADE"),
                          nullable=False)
    difficulty   = Column(String(10), nullable=False)
    correct      = Column(Boolean,    nullable=False)
    p_before     = Column(Float,      nullable=False)
    p_after      = Column(Float,      nullable=False)
    p_hard_after = Column(Float,      nullable=False)
    created_at   = Column(DateTime,   nullable=False,
                          server_default=text("NOW()"))

    session = relationship("Session", back_populates="interactions")
    concept = relationship("Concept", back_populates="interactions")



# ---------------------------------------------------------------------------
# knowledge_nodes
# Global concept graph nodes — one per distinct concept across all courses.
# Concepts from different courses map to the same node via concept_node_mappings.
# ---------------------------------------------------------------------------
class KnowledgeNode(Base):
    __tablename__ = "knowledge_nodes"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    name         = Column(Text,    nullable=False)
    description  = Column(Text,    nullable=True)
    aliases      = Column(JSON,    nullable=False, server_default=text("'[]'"))
    concept_type = Column(String,  nullable=False, server_default=text("'unknown'"))
    source       = Column(String,  nullable=False)   # e.g. "metacademy", "acm_ccs"
    source_id    = Column(String,  nullable=True)    # source-specific stable ID

    outgoing_edges = relationship("KnowledgeEdge",
                                   foreign_keys="KnowledgeEdge.from_node_id",
                                   back_populates="from_node",
                                   cascade="all, delete-orphan")
    incoming_edges = relationship("KnowledgeEdge",
                                   foreign_keys="KnowledgeEdge.to_node_id",
                                   back_populates="to_node",
                                   cascade="all, delete-orphan")
    concept_mappings = relationship("ConceptNodeMapping",
                                     back_populates="node",
                                     cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# knowledge_edges
# Directed prerequisite edges between knowledge nodes.
# from_node → to_node means "from_node is a prerequisite of to_node"
# ---------------------------------------------------------------------------
class KnowledgeEdge(Base):
    __tablename__ = "knowledge_edges"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    from_node_id = Column(Integer, ForeignKey("knowledge_nodes.id",
                                               ondelete="CASCADE"),
                          nullable=False)
    to_node_id   = Column(Integer, ForeignKey("knowledge_nodes.id",
                                               ondelete="CASCADE"),
                          nullable=False)
    source       = Column(String,  nullable=False)   # e.g. "metacademy", "acm_ccs"

    from_node = relationship("KnowledgeNode", foreign_keys=[from_node_id],
                              back_populates="outgoing_edges")
    to_node   = relationship("KnowledgeNode", foreign_keys=[to_node_id],
                              back_populates="incoming_edges")


# ---------------------------------------------------------------------------
# concept_node_mappings
# Links a course concept to its global knowledge node.
# One concept maps to one node; one node can have many concept mappings
# (same concept extracted from different courses points to same node).
# ---------------------------------------------------------------------------
class ConceptNodeMapping(Base):
    __tablename__ = "concept_node_mappings"

    # concept_id : VARCHAR — concepts.id is a UUID string
    # node_id    : INTEGER — knowledge_nodes.id is a serial integer
    concept_id  = Column(String,  ForeignKey("concepts.id",
                                              ondelete="CASCADE"),
                         primary_key=True)
    node_id     = Column(Integer, ForeignKey("knowledge_nodes.id",
                                              ondelete="CASCADE"),
                         primary_key=True)
    confidence  = Column(Float,   nullable=False)
    match_type  = Column(String,  nullable=False)   # exact_name | exact_alias | semantic

    concept = relationship("Concept")
    node    = relationship("KnowledgeNode", back_populates="concept_mappings")


# ---------------------------------------------------------------------------
# ensure_tables
# Creates all tables that don't exist yet.
# Safe to call on every startup — IF NOT EXISTS on all DDL.
# Never drops or alters existing tables.
# ---------------------------------------------------------------------------

def ensure_tables(db_url: str) -> None:
    """
    Create all adaptive learning DB tables that don't exist yet.
    Call once at application startup before any request is served.
    Order matters — tables are created in FK dependency order.
    """
    engine = create_engine(db_url)
    with engine.connect() as conn:

        # 1. users — no FK dependencies
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id         VARCHAR PRIMARY KEY,
                email      VARCHAR NOT NULL UNIQUE,
                username   VARCHAR NOT NULL UNIQUE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """))

        # 2. courses — no FK dependencies
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS courses (
                id          VARCHAR PRIMARY KEY,
                name        VARCHAR NOT NULL UNIQUE,
                description TEXT,
                created_at  TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """))

        # 3. course_enrollments — depends on users, courses
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS course_enrollments (
                user_id   VARCHAR NOT NULL REFERENCES users(id)   ON DELETE CASCADE,
                course_id VARCHAR NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                PRIMARY KEY (user_id, course_id)
            )
        """))

        # 4. concepts — depends on courses
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

        # 5. concept_files — depends on concepts
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS concept_files (
                concept_id VARCHAR NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
                file_id    VARCHAR NOT NULL,
                PRIMARY KEY (concept_id, file_id)
            )
        """))

        # 6. sessions — depends on users
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sessions (
                id         VARCHAR PRIMARY KEY,
                user_id    VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                scope_type VARCHAR NOT NULL,
                scope_ids  VARCHAR NOT NULL,
                started_at TIMESTAMP NOT NULL DEFAULT NOW(),
                ended_at   TIMESTAMP
            )
        """))

        # 7. student_pfa_state — depends on users, concepts
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

        # 8. session_interactions — depends on sessions, users, concepts
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

        # 9. knowledge_nodes — integer serial PK, no FK dependencies
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

        # 10. knowledge_edges — integer serial PK, integer FKs
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

        # 11. concept_node_mappings — concept_id VARCHAR (uuid), node_id INTEGER
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