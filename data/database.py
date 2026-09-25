import os
from pathlib import Path

import turso
import turso.sync

DB_PATH = Path(__file__).parent / "jobs.db"
TURSO_REMOTE_URL = os.environ.get("TURSO_SYNC_URL")
TURSO_TOKEN = os.environ.get("TURSO_TOKEN")


def get_connection():
    if TURSO_REMOTE_URL and TURSO_TOKEN:
        # Turso Cloud sync connection (local-first)
        conn = turso.sync.connect(
            str(DB_PATH),
            remote_url=TURSO_REMOTE_URL,
            auth_token=TURSO_TOKEN,
        )
    else:
        # Fallback: local SQLite file
        conn = turso.connect(str(DB_PATH))

    # NOTE: foreign key enforcement is not supported by Turso MVCC mode
    # and is therefore intentionally omitted here. Application-level
    # integrity is maintained by job-agent's own logic.
    return conn




def _commit_and_push(conn):
    """Commit locally and push to Turso if connected."""
    conn.commit()
    try:
        if hasattr(conn, "push"):
            conn.push()
    except Exception:
        pass  # offline fallback


def create_tables():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            job_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_title TEXT NOT NULL,
            company TEXT,
            job_family TEXT,
            seniority TEXT,
            location TEXT,
            country TEXT DEFAULT 'Netherlands',
            work_model TEXT,
            salary TEXT,
            salary_period TEXT,
            salary_type TEXT,
            posted_date TEXT,
            days_old INTEGER,
            job_description TEXT,
            key_requirements TEXT,
            dutch_requirement TEXT,
            education_requirement TEXT,
            experience_requirement TEXT,
            match_category TEXT,
            why_match TEXT,
            gaps TEXT,
            priority TEXT,
            date_found TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS job_sources (
            source_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            source TEXT NOT NULL,
            source_url TEXT,
            source_job_id TEXT,
            date_found TEXT,
            source_posted_date TEXT,
            is_primary INTEGER DEFAULT 0,
            FOREIGN KEY (job_id) REFERENCES jobs(job_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS job_matches (
            match_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            match_category TEXT,
            match_reason TEXT,
            direct_matches TEXT,
            transferable_matches TEXT,
            gaps TEXT,
            experience_gap TEXT,
            education_match TEXT,
            language_match TEXT,
            overall_notes TEXT,
            is_current INTEGER NOT NULL DEFAULT 1,
            invalidated_at TEXT,
            invalidation_reason TEXT,
            FOREIGN KEY (job_id) REFERENCES jobs(job_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS job_match_queue (
            job_id INTEGER PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (
                    status IN (
                        'pending',
                        'processing',
                        'completed',
                        'failed'
                    )
                ),
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_attempt_date TEXT,
            last_error TEXT,
            processing_token TEXT,
            job_fingerprint TEXT,
            lease_expires_at TEXT,
            completed_at TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (job_id) REFERENCES jobs(job_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gemini_request_log (
            request_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            request_date TEXT NOT NULL,
            reserved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT,
            outcome TEXT NOT NULL DEFAULT 'reserved',
            error_message TEXT,
            processing_token TEXT,
            job_fingerprint TEXT,
            FOREIGN KEY (job_id) REFERENCES jobs(job_id)
        )
    """)

    existing_columns = {
        row[1]
        for row in cursor.execute(
            "PRAGMA table_info(job_matches)"
        )
    }

    lifecycle_columns = {
        "is_current": (
            "INTEGER NOT NULL DEFAULT 1"
        ),
        "invalidated_at": "TEXT",
        "invalidation_reason": "TEXT",
    }

    queue_columns = {
        "job_fingerprint": "TEXT",
    }

    request_log_columns = {
        "processing_token": "TEXT",
        "job_fingerprint": "TEXT",
    }

    for column, definition in lifecycle_columns.items():
        if column not in existing_columns:
            cursor.execute(
                f"ALTER TABLE job_matches "
                f"ADD COLUMN {column} {definition}"
            )

    existing_queue_columns = {
        row[1]
        for row in cursor.execute(
            "PRAGMA table_info(job_match_queue)"
        )
    }

    for column, definition in queue_columns.items():
        if column not in existing_queue_columns:
            cursor.execute(
                f"ALTER TABLE job_match_queue "
                f"ADD COLUMN {column} {definition}"
            )

    existing_request_log_columns = {
        row[1]
        for row in cursor.execute(
            "PRAGMA table_info(gemini_request_log)"
        )
    }

    for column, definition in request_log_columns.items():
        if column not in existing_request_log_columns:
            cursor.execute(
                f"ALTER TABLE gemini_request_log "
                f"ADD COLUMN {column} {definition}"
            )

    # Existing match rows predate lifecycle tracking and remain current.
    cursor.execute("""
        UPDATE job_matches
        SET is_current = 1
        WHERE is_current IS NULL
    """)

    # If an older database contains multiple current matches for one job,
    # retain every row but treat only the newest result as current before
    # creating the one-current-match index below.
    cursor.execute("""
        UPDATE job_matches
        SET
            is_current = 0,
            invalidated_at = COALESCE(
                invalidated_at,
                datetime('now')
            ),
            invalidation_reason = COALESCE(
                invalidation_reason,
                'Superseded during match lifecycle migration.'
            )
        WHERE is_current = 1
          AND match_id NOT IN (
              SELECT MAX(match_id)
              FROM job_matches
              WHERE is_current = 1
              GROUP BY job_id
          )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_jobs_identity
        ON jobs (
            LOWER(TRIM(COALESCE(company, ''))),
            LOWER(TRIM(COALESCE(job_title, ''))),
            LOWER(TRIM(COALESCE(location, '')))
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_job_sources_lookup
        ON job_sources (source, source_job_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_job_sources_job_id
        ON job_sources (job_id)
    """)

    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_job_matches_one_current
        ON job_matches (job_id)
        WHERE is_current = 1
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_job_matches_current
        ON job_matches (is_current, job_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_job_match_queue_state
        ON job_match_queue (
            status,
            last_attempt_date,
            job_id
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_gemini_request_log_day
        ON gemini_request_log (request_date, request_id)
    """)

    _commit_and_push(conn)
    conn.close()


def find_duplicate_job(
    job_title,
    company,
    location,
    conn=None,
):
    owns_connection = conn is None

    if owns_connection:
        conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""
        SELECT job_id
        FROM jobs
        WHERE LOWER(TRIM(COALESCE(job_title, '')))
              = LOWER(TRIM(COALESCE(?, '')))
          AND LOWER(TRIM(COALESCE(company, '')))
              = LOWER(TRIM(COALESCE(?, '')))
          AND LOWER(TRIM(COALESCE(location, '')))
              = LOWER(TRIM(COALESCE(?, '')))
        LIMIT 1
    """, (
        job_title,
        company,
        location,
    ))

    result = cursor.fetchone()

    if owns_connection:
        conn.close()

    if result:
        return result[0]

    return None


def update_existing_job(
    job_id,
    job,
):

    conn = get_connection()

    try:
        _update_job_and_invalidate_matches(
            conn,
            job_id,
            job,
        )
        _commit_and_push(conn)
    finally:
        conn.close()


def _normalized_value(value):
    return str(value or "").strip()


def _relevant_job_data_changed(existing_job, job):
    existing_title, existing_location, existing_date, existing_description = (
        existing_job
    )

    return any((
        _normalized_value(existing_title)
        != _normalized_value(job.job_title),
        _normalized_value(existing_location)
        != _normalized_value(job.location),
        _normalized_value(existing_date)
        != _normalized_value(job.posted_date),
        _normalized_value(existing_description)
        != _normalized_value(job.description),
    ))


def _invalidate_current_matches(conn, job_id, reason):
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE job_matches
        SET
            is_current = 0,
            invalidated_at = datetime('now'),
            invalidation_reason = ?
        WHERE job_id = ?
          AND is_current = 1
    """, (reason, job_id))

    cursor.execute("""
        UPDATE jobs
        SET
            job_family = NULL,
            seniority = NULL,
            country = 'Netherlands',
            work_model = NULL,
            salary_period = NULL,
            salary_type = NULL,
            days_old = NULL,
            key_requirements = NULL,
            dutch_requirement = NULL,
            education_requirement = NULL,
            experience_requirement = NULL,
            match_category = NULL,
            why_match = NULL,
            gaps = NULL,
            priority = NULL
        WHERE job_id = ?
    """, (job_id,))


def _update_job_and_invalidate_matches(conn, job_id, job):
    cursor = conn.cursor()

    existing_job = cursor.execute("""
        SELECT
            job_title,
            location,
            posted_date,
            job_description
        FROM jobs
        WHERE job_id = ?
    """, (job_id,)).fetchone()

    if existing_job is None:
        raise ValueError(f"Job ID {job_id} does not exist.")

    relevant_data_changed = _relevant_job_data_changed(
        existing_job,
        job,
    )

    cursor.execute("""
        UPDATE jobs
        SET
            job_title = ?,
            company = ?,
            location = ?,
            salary = ?,
            posted_date = ?,
            job_description = ?
        WHERE job_id = ?
    """, (
        job.job_title,
        job.company,
        job.location,
        job.salary,
        job.posted_date,
        job.description,
        job_id,
    ))

    if relevant_data_changed:
        _invalidate_current_matches(
            conn,
            job_id,
            "Relevant collected job data changed.",
        )

    return relevant_data_changed


def insert_collected_job(job):

    conn = get_connection()
    cursor = conn.cursor()

    existing_job_id = None

    if job.source_job_id:

        cursor.execute(
            """
            SELECT job_id
            FROM job_sources
            WHERE source = ?
              AND source_job_id = ?
            LIMIT 1
            """,
            (
                job.source,
                job.source_job_id,
            ),
        )

        result = cursor.fetchone()

        if result:
            existing_job_id = result[0]

    if existing_job_id is None and job.source_url:

        cursor.execute("""
            SELECT job_id
            FROM job_sources
            WHERE source_url = ?
            LIMIT 1
        """, (job.source_url,))

        result = cursor.fetchone()

        if result:
            existing_job_id = result[0]

    # A stable source ID identifies a specific posting. Do not merge a
    # newly observed source ID solely because title, company, and location
    # match: repeated postings can legitimately share those values.
    if existing_job_id is None and not job.source_job_id:

        existing_job_id = find_duplicate_job(
            job.job_title,
            job.company,
            job.location,
            conn=conn,
        )

    if existing_job_id is not None:

        _update_job_and_invalidate_matches(
            conn,
            existing_job_id,
            job,
        )

        cursor.execute(
            """
            SELECT source_id
            FROM job_sources
            WHERE job_id = ?
              AND source = ?
              AND source_job_id = ?
            LIMIT 1
            """,
            (
                existing_job_id,
                job.source,
                job.source_job_id,
            ),
        )

        source_exists = cursor.fetchone()

        if source_exists is None:

            cursor.execute(
                """
                INSERT INTO job_sources (
                    job_id,
                    source,
                    source_url,
                    source_job_id,
                    date_found,
                    source_posted_date,
                    is_primary
                )
                VALUES (
                    ?,
                    ?,
                    ?,
                    ?,
                    DATE('now'),
                    ?,
                    0
                )
                """,
                (
                    existing_job_id,
                    job.source,
                    job.source_url,
                    job.source_job_id,
                    job.posted_date,
                ),
            )
        else:
            cursor.execute("""
                UPDATE job_sources
                SET
                    source_url = ?,
                    source_posted_date = ?,
                    date_found = DATE('now')
                WHERE source_id = ?
            """, (
                job.source_url,
                job.posted_date,
                source_exists[0],
            ))

        _commit_and_push(conn)
        conn.close()

        return existing_job_id, False

    cursor.execute(
        """
        INSERT INTO jobs (
            job_title,
            company,
            location,
            salary,
            posted_date,
            job_description,
            date_found
        )
        VALUES (?, ?, ?, ?, ?, ?, DATE('now'))
        """,
        (
            job.job_title,
            job.company,
            job.location,
            job.salary,
            job.posted_date,
            job.description,
        ),
    )

    job_id = cursor.lastrowid

    cursor.execute(
        """
        INSERT INTO job_sources (
            job_id,
            source,
            source_url,
            source_job_id,
            date_found,
            source_posted_date,
            is_primary
        )
        VALUES (
            ?,
            ?,
            ?,
            ?,
            DATE('now'),
            ?,
            1
        )
        """,
        (
            job_id,
            job.source,
            job.source_url,
            job.source_job_id,
            job.posted_date,
        ),
    )

    _commit_and_push(conn)
    conn.close()

    return job_id, True


if __name__ == "__main__":

    create_tables()

    print("JOB DATABASE READY")
