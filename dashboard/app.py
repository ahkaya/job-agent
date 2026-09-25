from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import subprocess
import sys
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.database import get_connection
from dashboard.distance_map import get_distance, format_distance

st.set_page_config(page_title="Job Agent Dashboard", layout="wide")
st.title("🎯 Job Agent Dashboard")

# Session state: active page
if "page" not in st.session_state:
    st.session_state["page"] = "📋 Pool"

with st.sidebar:
    st.header("⚙️ Control Panel")

    if st.button("🔍 Fetch & Match New Jobs", type="primary", width="stretch"):
        with st.spinner("Collecting and matching... (a few minutes)"):
            result = subprocess.run(
                [sys.executable, "main.py"],
                cwd=ROOT, capture_output=True, text=True,
            )
            if result.returncode == 0:
                st.success("Done!")
            else:
                st.error("Failed!")
            st.code(result.stdout[-2000:])

    st.divider()

    conn = get_connection()
    stats = conn.execute("""
        SELECT
            SUM(CASE WHEN j.is_hidden = 0 AND d.job_id IS NULL AND j.is_applied = 0 THEN 1 ELSE 0 END) as pool,
            SUM(CASE WHEN j.is_hidden = 0 AND d.job_id IS NOT NULL AND j.is_applied = 0 THEN 1 ELSE 0 END) as with_cv,
            SUM(CASE WHEN j.is_applied = 1 AND j.is_hidden = 0 THEN 1 ELSE 0 END) as applied,
            SUM(CASE WHEN j.is_hidden = 1 THEN 1 ELSE 0 END) as hidden
        FROM jobs j
        LEFT JOIN job_documents d ON d.job_id = j.job_id
        WHERE j.match_category IS NOT NULL AND j.match_category != ''
    """).fetchone()
    conn.close()

    n_pool = stats[0] or 0
    n_cv = stats[1] or 0
    n_applied = stats[2] or 0
    n_hidden = stats[3] or 0

    current = st.session_state["page"]

    # Nav button with active state
    def _btn(label, key, target):
        is_active = current == target
        style = "primary" if is_active else "secondary"
        if st.button(label, key=key, width="stretch", type=style):
            st.session_state["page"] = target
            st.rerun()

    _btn(f"📋 Pool ({n_pool})", "nav_pool", "📋 Pool")
    _btn(f"📄 Generated CVs ({n_cv})", "nav_cv", "📄 Generated CVs")
    _btn(f"✅ Applied ({n_applied})", "nav_applied", "✅ Applied")
    _btn(f"🗑️ Hidden ({n_hidden})", "nav_hidden", "🗑️ Hidden")

    st.divider()

    # Manual job count
    conn2 = get_connection()
    n_manual = conn2.execute("""
        SELECT COUNT(*) FROM jobs
        WHERE match_category = 'Manual' AND is_hidden = 0
    """).fetchone()[0]
    conn2.close()

    _btn(f"✍️ Manual Job ({n_manual})", "nav_manual", "✍️ Manual Job")

    st.divider()

    # Response statistics
    conn_y = get_connection()
    try:
        n_responses = conn_y.execute("SELECT COUNT(*) FROM application_emails").fetchone()[0]
        n_interview = conn_y.execute("SELECT COUNT(*) FROM application_emails WHERE category = 'interview'").fetchone()[0]
        n_rejection = conn_y.execute("SELECT COUNT(*) FROM application_emails WHERE category = 'rejection'").fetchone()[0]
        n_offer = conn_y.execute("SELECT COUNT(*) FROM application_emails WHERE category = 'offer'").fetchone()[0]
    except Exception:
        n_responses = n_interview = n_rejection = n_offer = 0
    conn_y.close()

    _btn(f"📬 Responses ({n_responses})", "nav_responses", "📬 Responses")

    if n_responses > 0:
        if n_offer > 0:
            st.success(f"🎉 {n_offer} offers")
        if n_interview > 0:
            st.info(f"📞 {n_interview} interviews")
        if n_rejection > 0:
            st.warning(f"❌ {n_rejection} rejections")

page = st.session_state["page"]

# ============================================================

# ============================================================
# PAGE 1 - POOL
# ============================================================
if page == "📋 Pool":
    st.subheader("📋 Job Pool")
    st.caption("Select jobs you like → generate CVs. Select jobs you dislike → delete.")

    conn = get_connection()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        match_filter = st.multiselect(
            "Match",
            ["Strong Match", "Potential Match", "Low Relevance"],
            default=["Strong Match", "Potential Match"],
        )
    with c2:
        priority_filter = st.multiselect(
            "Priority",
            ["High", "Normal", "Low"],
            default=["High", "Normal", "Low"],
        )
    with c3:
        sources = [r[0] for r in conn.execute(
            "SELECT DISTINCT source FROM job_sources WHERE source IS NOT NULL ORDER BY source"
        ).fetchall()]
        source_filter = st.multiselect("Source", sources, default=[])
    with c4:
        max_distance = st.slider(
            "Max Distance (km)",
            min_value=0,
            max_value=300,
            value=300,
            step=10,
            help="Approximate distance from Almelo. 300 = filter off.",
        )

    sql = """
        SELECT
            j.job_id as id,
            j.job_title as Position,
            j.company as Company,
            j.location as Location,
            j.match_category as Match,
            j.priority as Priority,
            COALESCE(s.source, '') as Source
        FROM jobs j
        LEFT JOIN job_sources s ON s.job_id = j.job_id AND s.is_primary = 1
        LEFT JOIN job_documents d ON d.job_id = j.job_id
        WHERE j.match_category IS NOT NULL AND j.match_category != ''
          AND j.is_hidden = 0
          AND j.is_applied = 0
          AND d.job_id IS NULL
    """
    params = []
    if match_filter:
        sql += f" AND j.match_category IN ({','.join('?' * len(match_filter))})"
        params.extend(match_filter)
    if priority_filter:
        sql += f" AND j.priority IN ({','.join('?' * len(priority_filter))})"
        params.extend(priority_filter)
    if source_filter:
        sql += f" AND s.source IN ({','.join('?' * len(source_filter))})"
        params.extend(source_filter)

    sql += " ORDER BY j.priority DESC, j.posted_date DESC, j.job_id DESC"

    pool_df = pd.read_sql_query(sql, conn, params=params)
    conn.close()

    # Compute distance
    if "Location" in pool_df.columns:
        pool_df["_dist"] = pool_df["Location"].apply(lambda x: get_distance(x))

        # Apply filter (300 = filter off)
        if max_distance < 300:
            pool_df = pool_df[
                (pool_df["_dist"].notna()) & (pool_df["_dist"] <= max_distance)
            ]

        # Add Distance column (after Location)
        pool_df["Distance"] = pool_df["_dist"].apply(
            lambda x: format_distance(x)
        )
        pool_df = pool_df.drop(columns=["_dist"])

        # Reorder columns
        cols = list(pool_df.columns)
        cols.remove("Distance")
        loc_idx = cols.index("Location") if "Location" in cols else len(cols) - 1
        cols.insert(loc_idx + 1, "Distance")
        pool_df = pool_df[cols]

    pool_df.insert(0, "Select", False)

    edited = st.data_editor(
        pool_df,
        width="stretch",
        hide_index=True,
        height=400,
        column_config={
            "Select": st.column_config.CheckboxColumn("Select", default=False),
            "id": st.column_config.NumberColumn("ID", disabled=True, width="small"),
        },
        disabled=["id", "Position", "Company", "Location", "Match", "Priority", "Source"],
        key="pool_editor",
    )

    selected_ids = edited[edited["Select"] == True]["id"].tolist()
    st.caption(f"Selected: **{len(selected_ids)}** jobs")

    # Show details of selected jobs
    if selected_ids:
        st.divider()
        with st.expander(f"📋 Selected Job Details ({len(selected_ids)} jobs)", expanded=True):
            conn = get_connection()
            for jid in selected_ids:
                jid = int(jid)
                detail = conn.execute("""
                    SELECT j.job_id, j.job_title, j.company, j.location,
                           j.job_description, j.match_category, j.priority,
                           COALESCE(s.source_url, '') as source_url,
                           COALESCE(s.source, '') as source
                    FROM jobs j
                    LEFT JOIN job_sources s ON s.job_id = j.job_id AND s.is_primary = 1
                    WHERE j.job_id = ?
                """, (jid,)).fetchone()

                if not detail:
                    continue

                st.markdown(f"### {detail[2]} — {detail[1]}")
                st.caption(f"ID: {detail[0]} | {detail[3]} | Match: {detail[5]} | Priority: {detail[6]} | Source: {detail[8]}")

                if detail[7]:
                    st.markdown(f"🔗 **[Open Job Posting]({detail[7]})**")

                if detail[4]:
                    with st.expander("📄 Show Job Description", expanded=False):
                        import re as _re
                        from bs4 import BeautifulSoup as _BS

                        # HTML -> clean text
                        raw = str(detail[4])
                        soup = _BS(raw, "html.parser")

                        # Turn <li> tags into "- " bullets
                        for li in soup.find_all("li"):
                            li.insert_before("\n- ")

                        # Turn <br>, <p>, <h*> tags into newlines
                        for tag in soup.find_all(["br", "p", "h1", "h2", "h3", "h4", "h5", "h6", "div", "ul", "ol"]):
                            tag.insert_before("\n\n")

                        text = soup.get_text(" ", strip=True)

                        # Clean up excessive whitespace and newlines
                        text = _re.sub(r"[ \t]+", " ", text)
                        text = _re.sub(r"\n{3,}", "\n\n", text)
                        text = text.strip()

                        st.markdown(text)
                else:
                    st.caption("_No job description_")

                st.markdown("---")
            conn.close()

    col_a, col_b = st.columns(2)

    with col_a:
        if st.button("🗑️ Delete Selected", disabled=not selected_ids, width="stretch"):
            conn = get_connection()
            conn.executemany(
                "UPDATE jobs SET is_hidden = 1 WHERE job_id = ?",
                [(int(i),) for i in selected_ids],
            )
            conn.commit()
            conn.close()
            st.success(f"{len(selected_ids)} jobs deleted.")
            st.rerun()

    with col_b:
        if st.button("✍️ Generate CVs for Selected", type="primary", disabled=not selected_ids, width="stretch"):
            from matching.cv_generator import (
                generate_cv_and_cover_letter,
                save_documents_to_db,
            )

            st.warning(f"Generating CVs for {len(selected_ids)} jobs (~{len(selected_ids) * 2} min)")

            progress = st.progress(0)
            status = st.empty()

            conn = get_connection()
            for idx, jid in enumerate(selected_ids):
                jid = int(jid)
                row = conn.execute("""
                    SELECT job_id, job_title, company, location, job_description
                    FROM jobs WHERE job_id = ?
                """, (jid,)).fetchone()

                if not row:
                    continue

                job = {
                    "job_id": row[0],
                    "job_title": row[1],
                    "company": row[2],
                    "location": row[3],
                    "job_description": row[4],
                }

                status.info(f"[{idx+1}/{len(selected_ids)}] {job['company']} | {job['job_title']}")

                try:
                    result = generate_cv_and_cover_letter(job)
                    cv_text = result.get("cv", "")
                    cover_text = result.get("cover_letter", "")
                    if not cv_text:
                        raise RuntimeError(f"LLM returned empty CV (jid={jid})")
                    save_documents_to_db(jid, cv_text, cover_text)

                    from matching.cv_generator import save_files_to_disk
                    save_files_to_disk(jid, job["company"], job["job_title"])
                except Exception as e:
                    st.error(f"Error ({jid}): {e}")

                progress.progress((idx + 1) / len(selected_ids))

            conn.close()
            status.success("Done!")
            st.rerun()

# ============================================================
# PAGE 2 - GENERATED CVS
# ============================================================
elif page == "📄 Generated CVs":
    st.subheader("📄 Jobs with Generated CVs")
    st.caption("Jobs with a generated CV but not yet applied. Check rows to download.")

    conn = get_connection()
    cv_rows = conn.execute("""
        SELECT
            j.job_id,
            j.job_title,
            j.company,
            j.location,
            j.match_category,
            j.priority,
            COALESCE(d.updated_at, d.created_at, '') as cv_date
        FROM jobs j
        JOIN job_documents d ON d.job_id = j.job_id
        WHERE j.is_hidden = 0
          AND j.is_applied = 0
        ORDER BY d.updated_at DESC
    """).fetchall()
    conn.close()

    if not cv_rows:
        st.info("No CVs generated yet.")
    else:
        df_cv = pd.DataFrame(
            [list(r) for r in cv_rows],
            columns=["id", "Position", "Company", "Location", "Match", "Priority", "CV Date"]
        )
        df_cv["CV Date"] = df_cv["CV Date"].astype(str).str[:16].str.replace("T", " ")
        df_cv["Distance"] = df_cv["Location"].apply(lambda x: format_distance(get_distance(x)))

        # Column order: Select, CV Date, Match, id, Position, Company, Location, Distance, Priority
        df_cv = df_cv[["id", "Position", "Company", "Location", "Distance", "Match", "Priority", "CV Date"]]
        df_cv.insert(0, "Select", False)
        df_cv = df_cv[["Select", "CV Date", "Match", "id", "Position", "Company", "Location", "Distance", "Priority"]]

        edited_cv = st.data_editor(
            df_cv,
            width="stretch",
            hide_index=True,
            height=min(400, 60 + 35 * len(df_cv)),
            column_config={
                "Select": st.column_config.CheckboxColumn("Select", default=False, width=40),
                "CV Date": st.column_config.TextColumn("CV Date", disabled=True, width=130),
                "Match": st.column_config.TextColumn("Match", disabled=True, width=110),
                "id": st.column_config.NumberColumn("ID", disabled=True, width=50),
                "Position": st.column_config.TextColumn("Position", disabled=True, width=220),
                "Company": st.column_config.TextColumn("Company", disabled=True, width=140),
                "Location": st.column_config.TextColumn("Location", disabled=True, width=120),
                "Distance": st.column_config.TextColumn("Distance", disabled=True, width=80),
                "Priority": st.column_config.TextColumn("Priority", disabled=True, width=70),
            },
            disabled=["CV Date", "Match", "id", "Position", "Company", "Location", "Distance", "Priority"],
            key="cv_editor",
        )

        selected_ids = edited_cv[edited_cv["Select"] == True]["id"].tolist()
        st.caption(f"Selected: **{len(selected_ids)}** jobs")

        # Show details of selected jobs
        if selected_ids:
            st.divider()
            with st.expander(f"📋 Selected Job Details ({len(selected_ids)} jobs)", expanded=True):
                conn = get_connection()
                for jid in selected_ids:
                    jid = int(jid)
                    detail = conn.execute("""
                        SELECT j.job_id, j.job_title, j.company, j.location,
                               j.job_description, j.match_category, j.priority,
                               COALESCE(s.source_url, '') as source_url,
                               COALESCE(s.source, '') as source
                        FROM jobs j
                        LEFT JOIN job_sources s ON s.job_id = j.job_id AND s.is_primary = 1
                        WHERE j.job_id = ?
                    """, (jid,)).fetchone()
                    if not detail:
                        continue
                    st.markdown(f"### {detail[2]} — {detail[1]}")
                    st.caption(f"ID: {detail[0]} | {detail[3]} | Match: {detail[5]} | Priority: {detail[6]} | Source: {detail[8]}")
                    if detail[7]:
                        st.markdown(f"🔗 **[Open Job Posting]({detail[7]})**")
                    if detail[4]:
                        with st.expander("📄 Show Job Description", expanded=False):
                            import re as _re
                            from bs4 import BeautifulSoup as _BS
                            soup = _BS(str(detail[4]), "html.parser")
                            for li in soup.find_all("li"):
                                li.insert_before("\n- ")
                            for tag in soup.find_all(["br", "p", "h1", "h2", "h3", "h4", "h5", "h6", "div", "ul", "ol"]):
                                tag.insert_before("\n\n")
                            text = soup.get_text(" ", strip=True)
                            text = _re.sub(r"[ \t]+", " ", text)
                            text = _re.sub(r"\n{3,}", "\n\n", text)
                            st.markdown(text.strip())
                    st.markdown("---")
                conn.close()

        # Download blocks for selected jobs
        if selected_ids:
            from matching.cv_generator import _build_filename

            st.divider()
            st.markdown("**📥 Download:**")

            static_dir = Path("static/cv")

            for jid in selected_ids:
                jid = int(jid)
                row = next((r for r in cv_rows if r[0] == jid), None)
                if not row:
                    continue

                title = row[1]
                company = row[2]

                st.markdown(f"**{company} — {title}**")

                cv_docx_path = static_dir / f"{jid}_cv.docx"
                cv_pdf_path = static_dir / f"{jid}_cv.pdf"
                cl_docx_path = static_dir / f"{jid}_cl.docx"
                cl_pdf_path = static_dir / f"{jid}_cl.pdf"

                job_meta = {"company": company, "job_title": title}
                cv_name = _build_filename(job_meta, "CV")
                cover_name = _build_filename(job_meta, "Cover_Letter")

                c1, c2, c3, c4 = st.columns(4)

                if cv_docx_path.exists():
                    with open(cv_docx_path, "rb") as f:
                        c1.download_button("📥 CV DOCX", data=f.read(),
                            file_name=f"{cv_name}.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            key=f"dl_cv_docx_{jid}", width="stretch")
                else:
                    c1.caption("CV DOCX missing")

                if cv_pdf_path.exists():
                    with open(cv_pdf_path, "rb") as f:
                        c2.download_button("📥 CV PDF", data=f.read(),
                            file_name=f"{cv_name}.pdf",
                            mime="application/pdf",
                            key=f"dl_cv_pdf_{jid}", width="stretch")
                else:
                    c2.caption("CV PDF missing")

                if cl_docx_path.exists():
                    with open(cl_docx_path, "rb") as f:
                        c3.download_button("📥 CL DOCX", data=f.read(),
                            file_name=f"{cover_name}.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            key=f"dl_cl_docx_{jid}", width="stretch")
                else:
                    c3.caption("CL DOCX missing")

                if cl_pdf_path.exists():
                    with open(cl_pdf_path, "rb") as f:
                        c4.download_button("📥 CL PDF", data=f.read(),
                            file_name=f"{cover_name}.pdf",
                            mime="application/pdf",
                            key=f"dl_cl_pdf_{jid}", width="stretch")
                else:
                    c4.caption("CL PDF missing")

                st.markdown("")

            st.divider()

        # Apply with Autofill button
        if st.button("🚀 Apply with Autofill",
                     disabled=not selected_ids or len(selected_ids) != 1,
                     width="stretch"):
            jid = int(selected_ids[0])
            conn = get_connection()
            row = conn.execute("""
                SELECT j.job_title, j.company, j.job_description,
                       COALESCE(s.source_url, '') as url
                FROM jobs j
                LEFT JOIN job_sources s ON s.job_id = j.job_id AND s.is_primary = 1
                WHERE j.job_id = ?
            """, (jid,)).fetchone()
            conn.close()

            if not row or not row[3]:
                st.error("❌ No application URL found for this job.")
            else:
                url = row[3]
                supported = any(
                    host in url.lower()
                    for host in ("greenhouse.io", "lever.co", "ashbyhq.com")
                )
                if not supported:
                    st.warning(
                        "⚠️ **Autofill is currently supported only for Greenhouse, "
                        "Lever, and Ashby ATS platforms.**\n\n"
                        f"This job is hosted on a different platform: `{url}`\n\n"
                        "Please apply manually via the job URL."
                    )
                    st.stop()

                cv_pdf = Path("static/cv") / f"{jid}_cv.pdf"
                if not cv_pdf.exists():
                    st.error(f"❌ CV PDF not found: {cv_pdf}")
                else:
                    st.info("🖥️ Opening Chrome with autofilled form. Review, then click **Submit** yourself.")
                    st.caption(f"Job: **{row[1]} — {row[0]}**")
                    st.caption(f"URL: {row[3]}")
                    st.caption(f"CV: `{cv_pdf}`")

                    import subprocess as _sp
                    import sys as _sys

                    script = f'''
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / "job-agent-integrations"))

from dotenv import load_dotenv
load_dotenv(Path.home() / "job-agent-integrations" / ".env")
load_dotenv(Path.home() / "job-agent" / ".env")

from integrations.ai_form_filler_universal import ai_fill_form

PROFILE = {{
    "first_name": "Ahmet",
    "last_name": "Kaya",
    "company": {row[1]!r},
    "job_title": {row[0]!r},
    "email": "aaahmetkayaaa@gmail.com",
    "phone": "+31 6 15034058",
    "location": "Almelo, Netherlands",
    "country": "Netherlands",
    "linkedin": "",
    "summary": (
        "Business Operations professional with 4 years of experience "
        "in supplier coordination, order tracking, and process automation."
    ),
}}

result = ai_fill_form(
    job_url={row[3]!r},
    profile=PROFILE,
    job_description={row[2][:5000]!r},
    cv_path={str(cv_pdf.resolve())!r},
    cl_path=None,
    headless=False,
    keep_open_seconds=600,
)
print("RESULT:", result.get("success"), "-", result.get("message"))
'''
                    _sp.Popen([_sys.executable, "-c", script])
                    st.success("✅ Chrome is opening. Fill and submit manually.")

        if st.button("✅ Mark Selected as Applied",
                     disabled=not selected_ids, type="primary"):
            from datetime import datetime as _dt
            now = _dt.now().strftime("%Y-%m-%d %H:%M")
            conn = get_connection()
            conn.executemany(
                "UPDATE jobs SET is_applied = 1, applied_at = ? WHERE job_id = ?",
                [(now, int(i)) for i in selected_ids],
            )
            conn.commit()
            conn.close()
            st.success(f"{len(selected_ids)} jobs marked as applied.")
            st.rerun()


# ============================================================
# PAGE 3 - APPLIED
# ============================================================
elif page == "✅ Applied":
    st.subheader("✅ Applied Jobs")
    st.caption("Jobs you have applied to. You can undo if you marked one by mistake.")

    conn = get_connection()
    applied_rows = conn.execute("""
        SELECT
            j.job_id as id,
            j.job_title as Position,
            j.company as Company,
            j.location as Location,
            j.match_category as Match,
            j.priority as Priority,
            COALESCE(d.updated_at, d.created_at, '') as [CV Date],
            COALESCE(j.applied_at, '') as [Applied Date],
            COALESCE(j.application_status, '') as [Status],
            (SELECT COUNT(*) FROM application_emails ae WHERE ae.job_id = j.job_id) as [Replies]
        FROM jobs j
        LEFT JOIN job_documents d ON d.job_id = j.job_id
        WHERE j.is_applied = 1
          AND j.is_hidden = 0
        ORDER BY j.applied_at DESC
    """).fetchall()
    conn.close()

    if not applied_rows:
        st.info("No applied jobs yet.")
    else:
        df_applied = pd.DataFrame(
            [list(r) for r in applied_rows],
            columns=["id", "Position", "Company", "Location", "Match", "Priority", "CV Date", "Applied Date", "Status", "Replies"]
        )
        df_applied["CV Date"] = df_applied["CV Date"].astype(str).str[:16].str.replace("T", " ")
        df_applied["Distance"] = df_applied["Location"].apply(lambda x: format_distance(get_distance(x)))

        # Status icons
        icons = {"interview": "📞 Interview", "rejection": "❌ Rejection", "offer": "🎉 Offer", "info": "ℹ️ Info"}
        df_applied["Status"] = df_applied["Status"].apply(lambda x: icons.get(str(x).lower(), x or "—"))

        df_applied = df_applied[["id", "Position", "Company", "Location", "Distance", "Match", "Priority", "Status", "Replies", "CV Date", "Applied Date"]]
        df_applied.insert(0, "Select", False)
        df_applied = df_applied[["Select", "CV Date", "Applied Date", "Match", "id", "Position", "Company", "Location", "Distance", "Status", "Replies", "Priority"]]

        edited_applied = st.data_editor(
            df_applied,
            width="stretch",
            hide_index=True,
            height=min(400, 60 + 35 * len(df_applied)),
            column_config={
                "Select": st.column_config.CheckboxColumn("Select", default=False, width=40),
                "CV Date": st.column_config.TextColumn("CV Date", disabled=True, width=130),
                "Applied Date": st.column_config.TextColumn("Applied Date", disabled=True, width=130),
                "Match": st.column_config.TextColumn("Match", disabled=True, width=110),
                "id": st.column_config.NumberColumn("ID", disabled=True, width=50),
                "Position": st.column_config.TextColumn("Position", disabled=True, width=220),
                "Company": st.column_config.TextColumn("Company", disabled=True, width=140),
                "Location": st.column_config.TextColumn("Location", disabled=True, width=120),
                "Distance": st.column_config.TextColumn("Distance", disabled=True, width=80),
                "Status": st.column_config.TextColumn("Status", disabled=True, width=110),
                "Replies": st.column_config.NumberColumn("📬", disabled=True, width=50),
                "Priority": st.column_config.TextColumn("Priority", disabled=True, width=70),
            },
            disabled=["CV Date", "Applied Date", "Match", "id", "Position", "Company", "Location", "Distance", "Status", "Replies", "Priority"],
            key="applied_editor",
        )

        selected_ids = edited_applied[edited_applied["Select"] == True]["id"].tolist()

        if len(selected_ids) > 1:
            selected_ids = [selected_ids[-1]]

        st.caption(f"Selected: **{len(selected_ids)}** jobs")

        # Show details of selected jobs
        if selected_ids:
            st.divider()
            with st.expander(f"📋 Selected Job Details ({len(selected_ids)} jobs)", expanded=True):
                conn = get_connection()
                for jid in selected_ids:
                    jid = int(jid)
                    detail = conn.execute("""
                        SELECT j.job_id, j.job_title, j.company, j.location,
                               j.job_description, j.match_category, j.priority,
                               COALESCE(s.source_url, '') as source_url,
                               COALESCE(s.source, '') as source
                        FROM jobs j
                        LEFT JOIN job_sources s ON s.job_id = j.job_id AND s.is_primary = 1
                        WHERE j.job_id = ?
                    """, (jid,)).fetchone()
                    if not detail:
                        continue
                    st.markdown(f"### {detail[2]} — {detail[1]}")
                    st.caption(f"ID: {detail[0]} | {detail[3]} | Match: {detail[5]} | Priority: {detail[6]} | Source: {detail[8]}")
                    if detail[7]:
                        st.markdown(f"🔗 **[Open Job Posting]({detail[7]})**")
                    if detail[4]:
                        with st.expander("📄 Show Job Description", expanded=False):
                            import re as _re
                            from bs4 import BeautifulSoup as _BS
                            soup = _BS(str(detail[4]), "html.parser")
                            for li in soup.find_all("li"):
                                li.insert_before("\n- ")
                            for tag in soup.find_all(["br", "p", "h1", "h2", "h3", "h4", "h5", "h6", "div", "ul", "ol"]):
                                tag.insert_before("\n\n")
                            text = soup.get_text(" ", strip=True)
                            text = _re.sub(r"[ \t]+", " ", text)
                            text = _re.sub(r"\n{3,}", "\n\n", text)
                            st.markdown(text.strip())

                    # Responses for this job
                    conn2 = get_connection()
                    responses = conn2.execute("""
                        SELECT sender, subject, category, confidence, reason, received_at
                        FROM application_emails
                        WHERE job_id = ?
                        ORDER BY processed_at DESC
                    """, (jid,)).fetchall()
                    conn2.close()

                    if responses:
                        st.markdown("**📬 Responses for this job:**")
                        icons2 = {"interview": "📞", "rejection": "❌", "offer": "🎉", "info": "ℹ️"}
                        for resp in responses:
                            sender, subject, category, confidence, reason, received_at = resp
                            icon = icons2.get(category, "📩")
                            st.markdown(
                                f"- {icon} **{category.upper() if category else '?'}** · "
                                f"{subject} · `{sender}` · {received_at}"
                            )
                            if reason:
                                st.caption(f"  💭 {reason}")
                    else:
                        st.caption("📭 No responses for this job yet.")

                    st.markdown("---")
                conn.close()

        if st.button("↩️ Undo Application", disabled=not selected_ids):
            conn = get_connection()
            conn.executemany(
                "UPDATE jobs SET is_applied = 0, applied_at = NULL WHERE job_id = ?",
                [(int(i),) for i in selected_ids],
            )
            conn.commit()
            conn.close()
            st.success("Application undone.")
            st.rerun()

        st.divider()
        st.markdown("**📥 Download:**")
        from matching.cv_generator import (
            generate_docx_bytes,
            generate_pdf_bytes,
            _build_filename,
        )

        conn = get_connection()
        full_rows = conn.execute("""
            SELECT j.job_id, j.job_title, j.company, d.cv_markdown, d.cover_letter_markdown
            FROM jobs j
            LEFT JOIN job_documents d ON d.job_id = j.job_id
            WHERE j.is_applied = 1 AND j.is_hidden = 0
            ORDER BY j.applied_at DESC
        """).fetchall()
        conn.close()

        for r in full_rows:
            jid, title, company, cv_md, cover_md = r
            if not cv_md:
                continue
            job_meta = {"company": company, "job_title": title}
            cv_name = _build_filename(job_meta, "CV")
            cover_name = _build_filename(job_meta, "Cover_Letter")

            with st.expander(f"📄 {company} — {title}", expanded=False):
                col1, col2, col3, col4 = st.columns(4)
                try:
                    cv_docx = generate_docx_bytes(cv_md or "")
                    col1.download_button("📥 CV DOCX", data=cv_docx,
                        file_name=f"{cv_name}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key=f"a_cv_docx_{jid}", width="stretch")
                    cv_pdf = generate_pdf_bytes(cv_docx)
                    col2.download_button("📥 CV PDF", data=cv_pdf,
                        file_name=f"{cv_name}.pdf", mime="application/pdf",
                        key=f"a_cv_pdf_{jid}", width="stretch")
                except Exception as e:
                    st.warning(f"CV error: {e}")
                try:
                    cover_docx = generate_docx_bytes(cover_md or "")
                    col3.download_button("📥 CL DOCX", data=cover_docx,
                        file_name=f"{cover_name}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key=f"a_cl_docx_{jid}", width="stretch")
                    cover_pdf = generate_pdf_bytes(cover_docx)
                    col4.download_button("📥 CL PDF", data=cover_pdf,
                        file_name=f"{cover_name}.pdf", mime="application/pdf",
                        key=f"a_cl_pdf_{jid}", width="stretch")
                except Exception as e:
                    st.warning(f"CL error: {e}")


# ============================================================
# PAGE 4 - HIDDEN
# ============================================================
elif page == "🗑️ Hidden":
    st.subheader("🗑️ Hidden Jobs")
    st.caption("Jobs you deleted. You can restore them if deleted by mistake.")

    conn = get_connection()
    hidden_rows = conn.execute("""
        SELECT
            j.job_id as id,
            j.job_title as Position,
            j.company as Company,
            j.location as Location,
            j.match_category as Match,
            j.priority as Priority
        FROM jobs j
        WHERE j.is_hidden = 1
        ORDER BY j.job_id DESC
        LIMIT 500
    """).fetchall()
    conn.close()

    if not hidden_rows:
        st.info("No hidden jobs.")
    else:
        df_hidden = pd.DataFrame(
            [list(r) for r in hidden_rows],
            columns=["id", "Position", "Company", "Location", "Match", "Priority"]
        )
        df_hidden.insert(0, "Select", False)

        edited_hidden = st.data_editor(
            df_hidden,
            width="stretch",
            hide_index=True,
            height=min(400, 60 + 35 * len(df_hidden)),
            column_config={
                "Select": st.column_config.CheckboxColumn("Select", default=False),
                "id": st.column_config.NumberColumn("ID", disabled=True, width="small"),
            },
            disabled=["id", "Position", "Company", "Location", "Match", "Priority"],
            key="hidden_editor",
        )

        selected_ids = edited_hidden[edited_hidden["Select"] == True]["id"].tolist()

        if len(selected_ids) > 1:
            selected_ids = [selected_ids[-1]]

        st.caption(f"Selected: **{len(selected_ids)}** jobs")

        if st.button("↩️ Restore", disabled=not selected_ids):
            conn = get_connection()
            conn.executemany(
                "UPDATE jobs SET is_hidden = 0 WHERE job_id = ?",
                [(int(i),) for i in selected_ids],
            )
            conn.commit()
            conn.close()
            st.success("Job restored.")
            st.rerun()


# ============================================================
# PAGE 5 - MANUAL JOB
# ============================================================
elif page == "✍️ Manual Job":
    st.subheader("✍️ Add Manual Job")
    st.caption("Generate CV + Cover Letter for jobs found on LinkedIn, Indeed, or company sites.")

    with st.form("manual_job_form", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            url = st.text_input("Job URL *", placeholder="https://...")
            position = st.text_input("Position *", placeholder="Business Operations Specialist")
        with col2:
            company = st.text_input("Company *", placeholder="Acme B.V.")
            location = st.text_input("Location", placeholder="Amsterdam")

        description = st.text_area(
            "Job Description *",
            placeholder="Paste the job description here...",
            height=300,
        )

        submitted = st.form_submit_button("✍️ Generate CV + Cover Letter", type="primary")

    if submitted:
        # Validation
        errors = []
        if not url or not url.strip():
            errors.append("URL is required")
        if not position or not position.strip():
            errors.append("Position is required")
        if not company or not company.strip():
            errors.append("Company is required")
        if not description or not description.strip():
            errors.append("Job description is required")

        if errors:
            for err in errors:
                st.error(err)
        else:
            url = url.strip()
            position = position.strip()
            company = company.strip()
            location = location.strip() if location else ""
            description = description.strip()

            # Check if URL already in pool
            conn = get_connection()
            existing = conn.execute("""
                SELECT j.job_id, j.job_title, j.company
                FROM job_sources s
                JOIN jobs j ON j.job_id = s.job_id
                WHERE s.source_url = ?
                  AND j.is_hidden = 0
            """, (url,)).fetchone()
            conn.close()

            if existing:
                st.warning(
                    f"⚠️ This URL is already in Pool: **[ID={existing[0]}] {existing[2]} — {existing[1]}**"
                )
                st.info(
                    "You can still add this manual job using the button below. "
                    "Use the Hidden page to delete the old record from the Pool."
                )

            # Save to session state
            st.session_state["manual_pending"] = {
                "url": url,
                "position": position,
                "company": company,
                "location": location,
                "description": description,
                "existing_id": existing[0] if existing else None,
            }
            st.rerun()

    # Generate pending manual job
    if "manual_pending" in st.session_state:
        pending = st.session_state["manual_pending"]

        st.divider()
        st.markdown(f"### 📄 {pending['company']} — {pending['position']}")
        st.caption(f"{pending['location'] or '—'} · {pending['url']}")

        col_a, col_b = st.columns([1, 3])
        with col_a:
            if st.button("✍️ Generate CV", type="primary"):
                with st.spinner("Generating CV... (~2 min)"):
                    try:
                        from matching.cv_generator import (
                            generate_cv_and_cover_letter,
                            save_documents_to_db,
                            save_files_to_disk,
                        )
                        from data.database import get_connection as _gc
                        from datetime import datetime as _dt

                        # Create job_id: max + 1
                        conn = _gc()
                        max_id = conn.execute("SELECT COALESCE(MAX(job_id), 0) FROM jobs").fetchone()[0]
                        new_id = max_id + 1

                        # Insert into jobs
                        conn.execute("""
                            INSERT INTO jobs (
                                job_id, job_title, company, location,
                                job_description, match_category, priority,
                                posted_date, date_found
                            )
                            VALUES (?, ?, ?, ?, ?, 'Manual', 'High', ?, ?)
                        """, (
                            new_id,
                            pending["position"],
                            pending["company"],
                            pending["location"],
                            pending["description"],
                            _dt.now().strftime("%Y-%m-%d"),
                            _dt.now().strftime("%Y-%m-%d %H:%M"),
                        ))

                        # Insert into job_sources
                        conn.execute("""
                            INSERT INTO job_sources (
                                job_id, source, source_url, date_found, is_primary
                            )
                            VALUES (?, 'Manual', ?, ?, 1)
                        """, (
                            new_id,
                            pending["url"],
                            _dt.now().strftime("%Y-%m-%d %H:%M"),
                        ))
                        conn.commit()
                        conn.close()

                        # Generate CV
                        job = {
                            "job_id": new_id,
                            "job_title": pending["position"],
                            "company": pending["company"],
                            "location": pending["location"],
                            "job_description": pending["description"],
                        }
                        result = generate_cv_and_cover_letter(job)
                        cv_text = result.get("cv", "")
                        cover_text = result.get("cover_letter", "")

                        if not cv_text:
                            raise RuntimeError("LLM returned empty CV")

                        save_documents_to_db(new_id, cv_text, cover_text)
                        save_files_to_disk(new_id, pending["company"], pending["position"])

                        st.success(f"✅ CV generated (ID={new_id})")
                        del st.session_state["manual_pending"]
                        st.rerun()

                    except Exception as e:
                        st.error(f"Error: {e}")

        with col_b:
            if st.button("❌ Cancel"):
                del st.session_state["manual_pending"]
                st.rerun()

    # List of manual jobs
    st.divider()
    st.subheader("📁 Added Manual Jobs")

    conn = get_connection()
    manual_rows = conn.execute("""
        SELECT
            j.job_id,
            j.job_title,
            j.company,
            j.location,
            s.source_url,
            COALESCE(d.updated_at, d.created_at, '') as cv_date
        FROM jobs j
        LEFT JOIN job_sources s ON s.job_id = j.job_id AND s.is_primary = 1
        LEFT JOIN job_documents d ON d.job_id = j.job_id
        WHERE j.match_category = 'Manual'
          AND j.is_hidden = 0
        ORDER BY j.job_id DESC
    """).fetchall()
    conn.close()

    if not manual_rows:
        st.info("No manual jobs added yet.")
    else:
        df_manual = pd.DataFrame(
            [list(r) for r in manual_rows],
            columns=["id", "Position", "Company", "Location", "URL", "CV Date"]
        )
        df_manual["CV Date"] = df_manual["CV Date"].astype(str).str[:16].str.replace("T", " ")
        df_manual["Distance"] = df_manual["Location"].apply(lambda x: format_distance(get_distance(x)) if x else "?")
        df_manual = df_manual[["id", "Position", "Company", "Location", "Distance", "URL", "CV Date"]]
        df_manual.insert(0, "Select", False)

        edited_manual = st.data_editor(
            df_manual,
            width="stretch",
            hide_index=True,
            height=min(400, 60 + 35 * len(df_manual)),
            column_config={
                "Select": st.column_config.CheckboxColumn("Select", default=False, width=40),
                "id": st.column_config.NumberColumn("ID", disabled=True, width=50),
                "Position": st.column_config.TextColumn("Position", disabled=True, width=200),
                "Company": st.column_config.TextColumn("Company", disabled=True, width=140),
                "Location": st.column_config.TextColumn("Location", disabled=True, width=120),
                "Distance": st.column_config.TextColumn("Distance", disabled=True, width=80),
                "URL": st.column_config.LinkColumn("URL", disabled=True, width=200, display_text="🔗 Open"),
                "CV Date": st.column_config.TextColumn("CV Date", disabled=True, width=130),
            },
            disabled=["id", "Position", "Company", "Location", "Distance", "URL", "CV Date"],
            key="manual_editor",
        )

        selected_ids = edited_manual[edited_manual["Select"] == True]["id"].tolist()

        if len(selected_ids) > 1:
            selected_ids = [selected_ids[-1]]

        st.caption(f"Selected: **{len(selected_ids)}** jobs")

        # Download buttons
        if len(selected_ids) == 1:
            jid = int(selected_ids[0])
            row = next((r for r in manual_rows if r[0] == jid), None)
            if row:
                title = row[1]
                company = row[2]
                from pathlib import Path as _P

                st.divider()
                st.markdown(f"**Selected:** {company} — {title}")

                c1, c2, c3, c4 = st.columns(4)
                static_dir = _P("static/cv")
                for col, (label, path, mime) in zip(
                    [c1, c2, c3, c4],
                    [
                        ("📥 CV DOCX", f"{jid}_cv.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                        ("📥 CV PDF", f"{jid}_cv.pdf", "application/pdf"),
                        ("📥 CL DOCX", f"{jid}_cl.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                        ("📥 CL PDF", f"{jid}_cl.pdf", "application/pdf"),
                    ],
                ):
                    fp = static_dir / path
                    if fp.exists():
                        with open(fp, "rb") as f:
                            col.download_button(label, data=f.read(),
                                file_name=path, mime=mime,
                                key=f"manual_dl_{path}", width="stretch")
                    else:
                        col.caption(f"{label} missing")

        # Delete
        if selected_ids:
            if st.button("🗑️ Delete Selected Manual Job", disabled=not selected_ids):
                conn = get_connection()
                jid = int(selected_ids[0])
                for table in ["job_documents", "job_matches", "job_match_queue", "job_sources"]:
                    conn.execute(f"DELETE FROM {table} WHERE job_id = ?", (jid,))
                conn.execute("DELETE FROM jobs WHERE job_id = ?", (jid,))
                conn.commit()
                conn.close()

                # Delete disk files
                from pathlib import Path as _P2
                for f in _P2("static/cv").glob(f"{jid}_*"):
                    f.unlink()

                st.success(f"Manual job (ID={jid}) deleted.")
                st.rerun()


# ============================================================

# ============================================================
# PAGE 6 - RESPONSES
# ============================================================
elif page == "📬 Responses":
    st.subheader("📬 Application Responses")
    st.caption("Application responses pulled automatically from Gmail.")

    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("🔄 Sync from Sheets", type="primary"):
            try:
                import sys as _sys
                from pathlib import Path as _P
                _sys.path.insert(0, str(_P.home() / "job-agent-integrations"))
                from dotenv import load_dotenv
                load_dotenv(_P.home() / "job-agent-integrations" / ".env")
                load_dotenv(_P.home() / "job-agent" / ".env")

                from integrations.gmail_tracker import sync_sheet_to_db
                with st.spinner("Reading Sheets, classifying with LLM... (~30 sec)"):
                    stats = sync_sheet_to_db(verbose=False)
                st.success(
                    f"Sync complete: "
                    f"{stats['new']} new, "
                    f"{stats['classified']} classified, "
                    f"{stats['matched']} matched"
                )
                st.rerun()
            except Exception as e:
                st.error(f"Sync error: {e}")

    with col2:
        st.caption(
            "💡 **How it works:** Gmail → Make.com → Google Sheets → this page. "
            "Click **Sync** when new emails arrive."
        )

    st.divider()

    conn = get_connection()
    rows = conn.execute("""
        SELECT
            ae.email_id, ae.sender, ae.subject, ae.category,
            ae.confidence, ae.reason, ae.received_at,
            ae.job_id, j.company, j.job_title
        FROM application_emails ae
        LEFT JOIN jobs j ON j.job_id = ae.job_id
        ORDER BY ae.processed_at DESC
    """).fetchall()
    conn.close()

    if not rows:
        st.info("No responses yet. Click **Sync** or add a new email to the Sheet.")
    else:
        categories = sorted(set(r[3] for r in rows if r[3]))
        selected_cats = st.multiselect(
            "Filter by category", categories, default=categories,
        )

        filtered = [r for r in rows if r[3] in selected_cats]
        st.caption(f"Total: **{len(filtered)}** responses")

        icons = {
            "interview": "📞", "rejection": "❌",
            "offer": "🎉", "info": "ℹ️", "irrelevant": "🗑️",
        }

        for r in filtered:
            (email_id, sender, subject, category,
             confidence, reason, received_at,
             job_id, company, job_title) = r

            icon = icons.get(category, "❓")

            with st.container(border=True):
                h1, h2 = st.columns([3, 1])
                with h1:
                    st.markdown(f"### {icon} {subject}")
                    st.caption(f"**From:** {sender} · **Received:** {received_at}")
                with h2:
                    if category == "offer":
                        st.success(category.upper())
                    elif category == "interview":
                        st.info(category.upper())
                    elif category == "rejection":
                        st.error(category.upper())
                    else:
                        st.caption(category.upper())

                if job_id and company:
                    st.markdown(f"🔗 **Related job:** {company} — {job_title}")

                if reason:
                    st.caption(f"💭 **LLM reason:** {reason}")

                if confidence:
                    st.caption(f"🎯 Confidence: {confidence:.0%}")
