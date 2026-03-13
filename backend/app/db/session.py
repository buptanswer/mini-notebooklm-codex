from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.models import Base

settings = get_settings()

engine = create_engine(
    settings.sqlite_url,
    connect_args={"check_same_thread": False},
    future=True,
)
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


def init_db() -> None:
    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    _apply_lightweight_migrations()
    _init_fts()


def _apply_lightweight_migrations() -> None:
    document_columns = {
        "document_title": "ALTER TABLE documents ADD COLUMN document_title VARCHAR(255)",
        "source_relative_path": "ALTER TABLE documents ADD COLUMN source_relative_path VARCHAR(500) NOT NULL DEFAULT ''",
        "enriched_ir_path": "ALTER TABLE documents ADD COLUMN enriched_ir_path VARCHAR(500)",
        "review_status": "ALTER TABLE documents ADD COLUMN review_status VARCHAR(24) NOT NULL DEFAULT 'pending'",
        "parser_warning_count": "ALTER TABLE documents ADD COLUMN parser_warning_count INTEGER NOT NULL DEFAULT 0",
        "unknown_block_count": "ALTER TABLE documents ADD COLUMN unknown_block_count INTEGER NOT NULL DEFAULT 0",
        "parent_chunk_count": "ALTER TABLE documents ADD COLUMN parent_chunk_count INTEGER NOT NULL DEFAULT 0",
        "child_chunk_count": "ALTER TABLE documents ADD COLUMN child_chunk_count INTEGER NOT NULL DEFAULT 0",
        "review_summary": "ALTER TABLE documents ADD COLUMN review_summary TEXT",
    }
    parent_chunk_columns = {
        "block_ids_json": "ALTER TABLE parent_chunks ADD COLUMN block_ids_json TEXT NOT NULL DEFAULT '[]'",
        "assets_json": "ALTER TABLE parent_chunks ADD COLUMN assets_json TEXT NOT NULL DEFAULT '[]'",
        "metadata_json": "ALTER TABLE parent_chunks ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'",
    }
    child_chunk_columns = {
        "assets_json": "ALTER TABLE child_chunks ADD COLUMN assets_json TEXT NOT NULL DEFAULT '[]'",
        "metadata_json": "ALTER TABLE child_chunks ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'",
        "embedding_model": "ALTER TABLE child_chunks ADD COLUMN embedding_model VARCHAR(64)",
    }

    with engine.begin() as connection:
        existing_columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(documents)")).fetchall()
        }
        for column_name, statement in document_columns.items():
            if column_name not in existing_columns:
                connection.execute(text(statement))
        _apply_table_migrations(connection, "parent_chunks", parent_chunk_columns)
        _apply_table_migrations(connection, "child_chunks", child_chunk_columns)


def _apply_table_migrations(connection, table_name: str, columns: dict[str, str]) -> None:
    existing_columns = {
        row[1] for row in connection.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    }
    for column_name, statement in columns.items():
        if column_name not in existing_columns:
            connection.execute(text(statement))


def _init_fts() -> None:
    statements = [
        "DROP TRIGGER IF EXISTS documents_au;",
        "DROP TRIGGER IF EXISTS documents_ad;",
        "DROP TRIGGER IF EXISTS documents_ai;",
        "DROP TRIGGER IF EXISTS child_chunks_au;",
        "DROP TRIGGER IF EXISTS child_chunks_ad;",
        "DROP TRIGGER IF EXISTS child_chunks_ai;",
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
            document_id UNINDEXED,
            knowledge_base_id UNINDEXED,
            source_filename,
            source_format,
            tokenize='unicode61'
        );
        """,
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS child_chunks_fts USING fts5(
            child_chunk_id UNINDEXED,
            document_id UNINDEXED,
            chunk_type,
            header_path,
            retrieval_text,
            tokenize='unicode61'
        );
        """,
        """
        CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
            INSERT INTO documents_fts(rowid, document_id, knowledge_base_id, source_filename, source_format)
            VALUES (new.rowid, new.id, new.knowledge_base_id, new.source_filename, new.source_format);
        END;
        """,
        """
        CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
            DELETE FROM documents_fts WHERE rowid = old.rowid;
        END;
        """,
        """
        CREATE TRIGGER IF NOT EXISTS child_chunks_ai AFTER INSERT ON child_chunks BEGIN
            INSERT INTO child_chunks_fts(rowid, child_chunk_id, document_id, chunk_type, header_path, retrieval_text)
            VALUES (new.rowid, new.id, new.document_id, new.chunk_type, new.header_path_json, new.retrieval_text);
        END;
        """,
        """
        CREATE TRIGGER IF NOT EXISTS child_chunks_ad AFTER DELETE ON child_chunks BEGIN
            DELETE FROM child_chunks_fts WHERE rowid = old.rowid;
        END;
        """,
    ]

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Session:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
