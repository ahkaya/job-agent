import json
import hashlib
from datetime import date
from uuid import uuid4

from data.database import create_tables, get_connection
from matching.gemini_matcher import analyze_job


DAILY_GEMINI_REQUEST_CAP = 200
PROCESSING_LEASE_SECONDS = 3600


def _today():
    return date.today().isoformat()


def build_job_fingerprint(job):
    relevant_data = {
        "job_title": str(job.get("job_title", "") or "").strip(),
        "company": str(job.get("company", "") or "").strip(),
        "location": str(job.get("location", "") or "").strip(),
        "posted_date": str(job.get("posted_date", "") or "").strip(),
        "job_description": str(
            job.get("job_description", "")
            or job.get("description", "")
            or ""
        ).strip(),
    }

    return hashlib.sha256(
        json.dumps(
            relevant_data,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def synchronize_matching_queue():
    """Synchronize persisted queue state with the match lifecycle."""

    create_tables()
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            UPDATE job_match_queue
            SET
                status = 'failed',
                last_error = 'Processing lease expired.',
                processing_token = NULL,
                job_fingerprint = NULL,
                lease_expires_at = NULL,
                updated_at = datetime('now')
            WHERE status = 'processing'
              AND lease_expires_at IS NOT NULL
              AND lease_expires_at < datetime('now')
        """)

        cursor.execute("""
            UPDATE job_match_queue
            SET
                status = 'completed',
                processing_token = NULL,
                job_fingerprint = NULL,
                lease_expires_at = NULL,
                completed_at = COALESCE(completed_at, datetime('now')),
                updated_at = datetime('now')
            WHERE EXISTS (
                SELECT 1
                FROM job_matches
                WHERE job_matches.job_id = job_match_queue.job_id
                  AND job_matches.is_current = 1
            )
        """)

        cursor.execute("""
            UPDATE job_match_queue
            SET
                status = 'pending',
                last_error = NULL,
                processing_token = NULL,
                lease_expires_at = NULL,
                completed_at = NULL,
                updated_at = datetime('now')
            WHERE status = 'completed'
              AND EXISTS (
                  SELECT 1
                  FROM jobs
                  WHERE jobs.job_id = job_match_queue.job_id
                    AND jobs.job_description IS NOT NULL
                    AND TRIM(jobs.job_description) != ''
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM job_matches
                  WHERE job_matches.job_id = job_match_queue.job_id
                    AND job_matches.is_current = 1
              )
        """)

        cursor.execute("""
            INSERT INTO job_match_queue (
                job_id,
                status,
                updated_at
            )
            SELECT
                jobs.job_id,
                'pending',
                datetime('now')
            FROM jobs
            WHERE jobs.job_description IS NOT NULL
              AND TRIM(jobs.job_description) != ''
              AND NOT EXISTS (
                  SELECT 1
                  FROM job_matches
                  WHERE job_matches.job_id = jobs.job_id
                    AND job_matches.is_current = 1
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM job_match_queue
                  WHERE job_match_queue.job_id = jobs.job_id
              )
        """)

        conn.commit()
    finally:
        conn.close()


def get_daily_request_count(request_date=None):
    create_tables()
    request_date = request_date or _today()
    conn = get_connection()

    try:
        return conn.execute("""
            SELECT COUNT(*)
            FROM gemini_request_log
            WHERE request_date = ?
        """, (request_date,)).fetchone()[0]
    finally:
        conn.close()


def get_queue_summary(request_date=None):
    synchronize_matching_queue()
    request_date = request_date or _today()
    conn = get_connection()

    try:
        pending = conn.execute("""
            SELECT COUNT(*)
            FROM job_match_queue
            WHERE status IN ('pending', 'failed')
        """).fetchone()[0]

        requests_today = conn.execute("""
            SELECT COUNT(*)
            FROM gemini_request_log
            WHERE request_date = ?
        """, (request_date,)).fetchone()[0]
    finally:
        conn.close()

    return {
        "pending": pending,
        "requests_today": requests_today,
        "remaining_capacity": max(
            0,
            DAILY_GEMINI_REQUEST_CAP - requests_today,
        ),
    }


def get_unmatched_jobs():
    """Return all unmatched jobs in deterministic queue order."""

    synchronize_matching_queue()
    today = _today()
    conn = get_connection()

    try:
        rows = conn.execute("""
            SELECT
                j.job_id,
                j.job_title,
                j.company,
                j.location,
                j.salary,
                j.posted_date,
                j.job_description
            FROM job_match_queue q
            JOIN jobs j
                ON j.job_id = q.job_id
            WHERE q.status IN ('pending', 'failed')
              AND j.job_description IS NOT NULL
              AND TRIM(j.job_description) != ''
              AND NOT EXISTS (
                  SELECT 1
                  FROM job_matches jm
                  WHERE jm.job_id = j.job_id
                    AND jm.is_current = 1
              )
            ORDER BY
                CASE
                    WHEN j.posted_date GLOB '????-??-??'
                    THEN j.posted_date
                    ELSE ''
                END DESC,
                CASE
                    WHEN j.posted_date GLOB '????-??-??'
                    THEN CAST(
                        julianday(?) - julianday(j.posted_date)
                        AS INTEGER
                    )
                    ELSE 999999
                END ASC,
                j.job_id ASC
        """, (today,)).fetchall()
    finally:
        conn.close()

    return [
        {
            "job_id": row[0],
            "job_title": row[1],
            "company": row[2],
            "location": row[3],
            "salary": row[4],
            "posted_date": row[5],
            "job_description": row[6],
        }
        for row in rows
    ]


def reserve_next_job(request_date=None):
    """Atomically reserve one Gemini request without exceeding the cap."""

    synchronize_matching_queue()
    request_date = request_date or _today()
    token = str(uuid4())
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # This serializes capacity checks and reservations across processes.
        cursor.execute("BEGIN IMMEDIATE")

        cursor.execute("""
            UPDATE job_match_queue
            SET
                status = 'failed',
                last_error = 'Processing lease expired.',
                processing_token = NULL,
                job_fingerprint = NULL,
                lease_expires_at = NULL,
                updated_at = datetime('now')
            WHERE status = 'processing'
              AND lease_expires_at IS NOT NULL
              AND lease_expires_at < datetime('now')
        """)

        requests_today = cursor.execute("""
            SELECT COUNT(*)
            FROM gemini_request_log
            WHERE request_date = ?
        """, (request_date,)).fetchone()[0]

        if requests_today >= DAILY_GEMINI_REQUEST_CAP:
            conn.commit()
            return None

        row = cursor.execute("""
            SELECT
                j.job_id,
                j.job_title,
                j.company,
                j.location,
                j.salary,
                j.posted_date,
                j.job_description
            FROM job_match_queue q
            JOIN jobs j
                ON j.job_id = q.job_id
            WHERE q.status IN ('pending', 'failed')
              AND j.job_description IS NOT NULL
              AND TRIM(j.job_description) != ''
              AND (
                  q.last_attempt_date IS NULL
                  OR q.last_attempt_date != ?
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM job_matches jm
                  WHERE jm.job_id = j.job_id
                    AND jm.is_current = 1
              )
            ORDER BY
                CASE
                    WHEN j.posted_date GLOB '????-??-??'
                    THEN j.posted_date
                    ELSE ''
                END DESC,
                CASE
                    WHEN j.posted_date GLOB '????-??-??'
                    THEN CAST(
                        julianday(?) - julianday(j.posted_date)
                        AS INTEGER
                    )
                    ELSE 999999
                END ASC,
                j.job_id ASC
            LIMIT 1
        """, (request_date, request_date)).fetchone()

        if row is None:
            conn.commit()
            return None

        job_id = row[0]
        job_fingerprint = build_job_fingerprint({
            "job_title": row[1],
            "company": row[2],
            "location": row[3],
            "posted_date": row[5],
            "job_description": row[6],
        })

        cursor.execute("""
            UPDATE job_match_queue
            SET
                status = 'processing',
                attempt_count = attempt_count + 1,
                last_attempt_date = ?,
                last_error = NULL,
                processing_token = ?,
                job_fingerprint = ?,
                lease_expires_at = datetime(
                    'now',
                    '+' || ? || ' seconds'
                ),
                updated_at = datetime('now')
            WHERE job_id = ?
        """, (
            request_date,
            token,
            job_fingerprint,
            PROCESSING_LEASE_SECONDS,
            job_id,
        ))

        cursor.execute("""
            INSERT INTO gemini_request_log (
                job_id,
                request_date,
                outcome,
                processing_token,
                job_fingerprint
            )
            VALUES (?, ?, 'reserved', ?, ?)
        """, (
            job_id,
            request_date,
            token,
            job_fingerprint,
        ))

        request_id = cursor.lastrowid
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "request_id": request_id,
        "processing_token": token,
        "job_fingerprint": job_fingerprint,
        "job": {
            "job_id": row[0],
            "job_title": row[1],
            "company": row[2],
            "location": row[3],
            "salary": row[4],
            "posted_date": row[5],
            "job_description": row[6],
        },
    }


def mark_request_failed(reservation, error):
    conn = get_connection()
    cursor = conn.cursor()
    job_id = reservation["job"]["job_id"]
    error_message = str(error)

    try:
        cursor.execute("BEGIN IMMEDIATE")

        cursor.execute("""
            UPDATE gemini_request_log
            SET
                outcome = 'failed',
                finished_at = datetime('now'),
                error_message = ?
            WHERE request_id = ?
              AND job_id = ?
              AND processing_token = ?
              AND job_fingerprint = ?
              AND outcome = 'reserved'
        """, (
            error_message,
            reservation["request_id"],
            job_id,
            reservation["processing_token"],
            reservation["job_fingerprint"],
        ))

        if cursor.rowcount != 1:
            conn.rollback()
            return False

        cursor.execute("""
            UPDATE job_match_queue
            SET
                status = 'failed',
                last_error = ?,
                processing_token = NULL,
                lease_expires_at = NULL,
                updated_at = datetime('now')
            WHERE job_id = ?
              AND processing_token = ?
        """, (
            error_message,
            job_id,
            reservation["processing_token"],
        ))

        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _mark_reservation_stale(
    cursor,
    reservation,
    reason,
    queue_status,
):
    job_id = reservation["job"]["job_id"]

    cursor.execute("""
        UPDATE gemini_request_log
        SET
            outcome = 'stale',
            finished_at = datetime('now'),
            error_message = ?
        WHERE request_id = ?
          AND job_id = ?
          AND processing_token = ?
          AND job_fingerprint = ?
          AND outcome = 'reserved'
    """, (
        reason,
        reservation["request_id"],
        job_id,
        reservation["processing_token"],
        reservation["job_fingerprint"],
    ))

    if queue_status is None:
        return

    cursor.execute("""
        UPDATE job_match_queue
        SET
            status = ?,
            last_attempt_date = CASE
                WHEN ? = 'pending' THEN NULL
                ELSE last_attempt_date
            END,
            last_error = ?,
            processing_token = NULL,
            job_fingerprint = NULL,
            lease_expires_at = NULL,
            completed_at = CASE
                WHEN ? = 'completed' THEN datetime('now')
                ELSE NULL
            END,
            updated_at = datetime('now')
        WHERE job_id = ?
          AND status = 'processing'
          AND processing_token = ?
          AND job_fingerprint = ?
    """, (
        queue_status,
        queue_status,
        reason,
        queue_status,
        job_id,
        reservation["processing_token"],
        reservation["job_fingerprint"],
    ))


def save_match(reservation, analysis):
    """Atomically save a reservation-bound Gemini match result.

    Returns True when saved. Returns False when the reservation became
    stale, leaving changed source data eligible for a new reservation.
    """

    conn = get_connection()
    cursor = conn.cursor()
    job = reservation["job"]
    job_id = job["job_id"]

    try:
        cursor.execute("BEGIN IMMEDIATE")

        request_row = cursor.execute("""
            SELECT request_id
            FROM gemini_request_log
            WHERE request_id = ?
              AND job_id = ?
              AND processing_token = ?
              AND job_fingerprint = ?
              AND outcome = 'reserved'
        """, (
            reservation["request_id"],
            job_id,
            reservation["processing_token"],
            reservation["job_fingerprint"],
        )).fetchone()

        if request_row is None:
            conn.rollback()
            return False

        queue_row = cursor.execute("""
            SELECT processing_token, job_fingerprint
            FROM job_match_queue
            WHERE job_id = ?
              AND status = 'processing'
              AND processing_token = ?
              AND job_fingerprint = ?
        """, (
            job_id,
            reservation["processing_token"],
            reservation["job_fingerprint"],
        )).fetchone()

        if queue_row is None:
            _mark_reservation_stale(
                cursor,
                reservation,
                "Reservation was replaced or expired.",
                queue_status=None,
            )
            conn.commit()
            return False

        current_job = cursor.execute("""
            SELECT
                job_title,
                company,
                location,
                posted_date,
                job_description
            FROM jobs
            WHERE job_id = ?
        """, (job_id,)).fetchone()

        current_fingerprint = build_job_fingerprint({
            "job_title": current_job[0],
            "company": current_job[1],
            "location": current_job[2],
            "posted_date": current_job[3],
            "job_description": current_job[4],
        })

        current_match_exists = cursor.execute("""
            SELECT 1
            FROM job_matches
            WHERE job_id = ?
              AND is_current = 1
        """, (job_id,)).fetchone()

        if current_match_exists:
            _mark_reservation_stale(
                cursor,
                reservation,
                "A newer current match already exists.",
                queue_status="completed",
            )
            conn.commit()
            return False

        if current_fingerprint != reservation["job_fingerprint"]:
            _mark_reservation_stale(
                cursor,
                reservation,
                "Collected job data changed after reservation.",
                queue_status="pending",
            )
            conn.commit()
            return False

        cursor.execute("""
            UPDATE jobs
            SET
                job_family = ?,
                seniority = ?,
                country = ?,
                work_model = ?,
                salary = ?,
                salary_period = ?,
                salary_type = ?,
                days_old = ?,
                key_requirements = ?,
                dutch_requirement = ?,
                education_requirement = ?,
                experience_requirement = ?,
                match_category = ?,
                why_match = ?,
                gaps = ?,
                priority = ?
            WHERE job_id = ?
        """, (
            analysis.get("job_family", ""),
            analysis.get("seniority", ""),
            analysis.get("country", "Netherlands"),
            analysis.get("work_model", ""),
            analysis.get("salary", ""),
            analysis.get("salary_period", ""),
            analysis.get("salary_type", ""),
            analysis.get("days_old"),
            json.dumps(
                analysis.get("key_requirements", []),
                ensure_ascii=False,
            ),
            analysis.get("dutch_requirement", ""),
            analysis.get("education_requirement", ""),
            analysis.get("experience_requirement", ""),
            analysis.get("match_category", ""),
            json.dumps(analysis.get("why_match", []), ensure_ascii=False),
            json.dumps(analysis.get("gaps", []), ensure_ascii=False),
            analysis.get("priority", ""),
            job_id,
        ))

        cursor.execute("""
            INSERT INTO job_matches (
                job_id,
                match_category,
                match_reason,
                direct_matches,
                transferable_matches,
                gaps,
                experience_gap,
                education_match,
                language_match,
                overall_notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id,
            analysis.get("match_category", ""),
            json.dumps(analysis.get("why_match", []), ensure_ascii=False),
            json.dumps(
                analysis.get("direct_matches", []),
                ensure_ascii=False,
            ),
            json.dumps(
                analysis.get("transferable_matches", []),
                ensure_ascii=False,
            ),
            json.dumps(analysis.get("gaps", []), ensure_ascii=False),
            analysis.get("experience_gap", ""),
            analysis.get("education_match", ""),
            analysis.get("language_match", ""),
            "",
        ))

        cursor.execute("""
            UPDATE gemini_request_log
            SET
                outcome = 'completed',
                finished_at = datetime('now')
            WHERE request_id = ?
              AND job_id = ?
              AND processing_token = ?
              AND job_fingerprint = ?
              AND outcome = 'reserved'
        """, (
            reservation["request_id"],
            job_id,
            reservation["processing_token"],
            reservation["job_fingerprint"],
        ))

        if cursor.rowcount != 1:
            raise RuntimeError("Reservation request log was not current.")

        cursor.execute("""
            UPDATE job_match_queue
            SET
                status = 'completed',
                last_error = NULL,
                processing_token = NULL,
                job_fingerprint = NULL,
                lease_expires_at = NULL,
                completed_at = datetime('now'),
                updated_at = datetime('now')
            WHERE job_id = ?
              AND status = 'processing'
              AND processing_token = ?
              AND job_fingerprint = ?
        """, (
            job_id,
            reservation["processing_token"],
            reservation["job_fingerprint"],
        ))

        if cursor.rowcount != 1:
            raise RuntimeError("Reservation queue row was not current.")

        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def run_batch_matching():
    summary = get_queue_summary()

    print()
    print("=" * 60)
    print("BATCH GEMINI MATCHING")
    print("=" * 60)
    print(f"Gemini requests today: {summary['requests_today']}")
    print(f"Remaining daily capacity: {summary['remaining_capacity']}")
    print(f"Pending jobs: {summary['pending']}")

    if summary["remaining_capacity"] == 0:
        print("Daily Gemini request cap reached. Jobs remain queued.")
        return

    if summary["pending"] == 0:
        print("No pending jobs found.")
        return

    successful = 0
    failed = 0
    stale = 0
    attempted = 0

    while True:
        reservation = reserve_next_job()

        if reservation is None:
            break

        attempted += 1
        job = reservation["job"]

        print()
        print(
            f"[{attempted}] "
            f"{job['company']} | "
            f"{job['job_title']}"
        )

        try:
            analysis = analyze_job(job)
            if save_match(reservation, analysis):
                successful += 1
                print(f"Match: {analysis.get('match_category', '')}")
            else:
                stale += 1
                print("STALE: Job changed or reservation was replaced.")
        except Exception as error:
            mark_request_failed(reservation, error)
            failed += 1
            print(f"ERROR: {error}")

    final_summary = get_queue_summary()

    print()
    print("=" * 60)
    print("BATCH COMPLETE")
    print("=" * 60)
    print(f"Attempted: {attempted}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Stale: {stale}")
    print(f"Gemini requests today: {final_summary['requests_today']}")
    print(f"Remaining daily capacity: {final_summary['remaining_capacity']}")
    print(f"Pending jobs: {final_summary['pending']}")


if __name__ == "__main__":
    run_batch_matching()
