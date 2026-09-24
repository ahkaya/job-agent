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

# Session state: aktif sayfa
if "page" not in st.session_state:
    st.session_state["page"] = "📋 Havuz"

with st.sidebar:
    st.header("⚙️ Kontrol Paneli")

    if st.button("🔍 Yeni İlanları Çek ve Eşleştir", type="primary", use_container_width=True):
        with st.spinner("Toplama ve eşleştirme çalışıyor... (birkaç dakika)"):
            result = subprocess.run(
                [sys.executable, "main.py"],
                cwd=ROOT, capture_output=True, text=True,
            )
            if result.returncode == 0:
                st.success("Tamamlandı!")
            else:
                st.error("Hata!")
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

    # Aktif sayfa icin gosterge
    def _btn(label, key, target):
        is_active = current == target
        style = "primary" if is_active else "secondary"
        if st.button(label, key=key, use_container_width=True, type=style):
            st.session_state["page"] = target
            st.rerun()

    _btn(f"📋 Havuz ({n_pool})", "nav_pool", "📋 Havuz")
    _btn(f"📄 CV Üretilmiş ({n_cv})", "nav_cv", "📄 CV Üretilenler")
    _btn(f"✅ Başvuruldu ({n_applied})", "nav_applied", "✅ Başvurulanlar")
    _btn(f"🗑️ Gizlenen ({n_hidden})", "nav_hidden", "🗑️ Gizlenen")

    st.divider()

    # Manuel ilan sayisi
    conn2 = get_connection()
    n_manual = conn2.execute("""
        SELECT COUNT(*) FROM jobs
        WHERE match_category = 'Manuel' AND is_hidden = 0
    """).fetchone()[0]
    conn2.close()

    _btn(f"✍️ Manuel İlan ({n_manual})", "nav_manual", "✍️ Manuel İlan")

    st.divider()

    # Yanit istatistikleri
    conn_y = get_connection()
    try:
        n_responses = conn_y.execute("SELECT COUNT(*) FROM application_emails").fetchone()[0]
        n_interview = conn_y.execute("SELECT COUNT(*) FROM application_emails WHERE category = 'interview'").fetchone()[0]
        n_rejection = conn_y.execute("SELECT COUNT(*) FROM application_emails WHERE category = 'rejection'").fetchone()[0]
        n_offer = conn_y.execute("SELECT COUNT(*) FROM application_emails WHERE category = 'offer'").fetchone()[0]
    except Exception:
        n_responses = n_interview = n_rejection = n_offer = 0
    conn_y.close()

    _btn(f"📬 Yanıtlar ({n_responses})", "nav_responses", "📬 Yanıtlar")

    if n_responses > 0:
        if n_offer > 0:
            st.success(f"🎉 {n_offer} teklif")
        if n_interview > 0:
            st.info(f"📞 {n_interview} mülakat")
        if n_rejection > 0:
            st.warning(f"❌ {n_rejection} ret")

page = st.session_state["page"]

# ============================================================
# SAYFA 1 — HAVUZ
# ============================================================
if page == "📋 Havuz":
    st.subheader("📋 İlan Havuzu")
    st.caption("Beğendiklerini seç → CV üret. Beğenmediklerini seç → sil.")

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
            "Öncelik",
            ["High", "Normal", "Low"],
            default=["High", "Normal", "Low"],
        )
    with c3:
        sources = [r[0] for r in conn.execute(
            "SELECT DISTINCT source FROM job_sources WHERE source IS NOT NULL ORDER BY source"
        ).fetchall()]
        source_filter = st.multiselect("Kaynak", sources, default=[])
    with c4:
        max_distance = st.slider(
            "Maks. Uzaklık (km)",
            min_value=0,
            max_value=300,
            value=300,
            step=10,
            help="Almelo merkezli yaklaşık mesafe. 300 = filtre kapalı.",
        )

    sql = """
        SELECT
            j.job_id as id,
            j.job_title as Pozisyon,
            j.company as Şirket,
            j.location as Konum,
            j.match_category as Match,
            j.priority as Öncelik,
            COALESCE(s.source, '') as Kaynak
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

    # Uzaklik hesapla
    if "Konum" in pool_df.columns:
        pool_df["_dist"] = pool_df["Konum"].apply(lambda x: get_distance(x))

        # Filtre uygula (300 ise filtre kapali)
        if max_distance < 300:
            pool_df = pool_df[
                (pool_df["_dist"].notna()) & (pool_df["_dist"] <= max_distance)
            ]

        # Uzaklik sutunu ekle (Konum'dan sonra)
        pool_df["Uzaklık"] = pool_df["_dist"].apply(
            lambda x: format_distance(x)
        )
        pool_df = pool_df.drop(columns=["_dist"])

        # Sutun sirasini duzenle
        cols = list(pool_df.columns)
        cols.remove("Uzaklık")
        konum_idx = cols.index("Konum") if "Konum" in cols else len(cols) - 1
        cols.insert(konum_idx + 1, "Uzaklık")
        pool_df = pool_df[cols]

    # Uzaklik sutunu ekle (Konum'dan sonra)
    if "Konum" in pool_df.columns:
        pool_df["Uzaklık"] = pool_df["Konum"].apply(
            lambda x: format_distance(get_distance(x))
        )
        # Sutun sirasini duzenle: Konum'dan sonra Uzaklik
        cols = list(pool_df.columns)
        cols.remove("Uzaklık")
        konum_idx = cols.index("Konum") if "Konum" in cols else len(cols) - 1
        cols.insert(konum_idx + 1, "Uzaklık")
        pool_df = pool_df[cols]

    pool_df.insert(0, "Seç", False)

    edited = st.data_editor(
        pool_df,
        use_container_width=True,
        hide_index=True,
        height=400,
        column_config={
            "Seç": st.column_config.CheckboxColumn("Seç", default=False),
            "id": st.column_config.NumberColumn("ID", disabled=True, width="small"),
        },
        disabled=["id", "Pozisyon", "Şirket", "Konum", "Match", "Öncelik", "Kaynak"],
        key="pool_editor",
    )

    selected_ids = edited[edited["Seç"] == True]["id"].tolist()
    st.caption(f"Seçili: **{len(selected_ids)}** ilan")

    # Secili ilanlarin detayini goster
    if selected_ids:
        st.divider()
        with st.expander(f"📋 Seçili İlan Detayı ({len(selected_ids)} ilan)", expanded=True):
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
                st.caption(f"ID: {detail[0]} | {detail[3]} | Match: {detail[5]} | Öncelik: {detail[6]} | Kaynak: {detail[8]}")

                if detail[7]:
                    st.markdown(f"🔗 **[İlanı Aç]({detail[7]})**")

                if detail[4]:
                    with st.expander("📄 İlan Metnini Göster", expanded=False):
                        import re as _re
                        from bs4 import BeautifulSoup as _BS

                        # HTML -> temiz metin
                        raw = str(detail[4])
                        soup = _BS(raw, "html.parser")

                        # <li> etiketlerini "- " ile madde yap
                        for li in soup.find_all("li"):
                            li.insert_before("\n- ")

                        # <br>, <p>, <h*> etiketlerini newline yap
                        for tag in soup.find_all(["br", "p", "h1", "h2", "h3", "h4", "h5", "h6", "div", "ul", "ol"]):
                            tag.insert_before("\n\n")

                        text = soup.get_text(" ", strip=True)

                        # Coklu bosluk ve newline'lari temizle
                        text = _re.sub(r"[ \t]+", " ", text)
                        text = _re.sub(r"\n{3,}", "\n\n", text)
                        text = text.strip()

                        st.markdown(text)
                else:
                    st.caption("_İlan metni yok_")

                st.markdown("---")
            conn.close()

    col_a, col_b = st.columns(2)

    with col_a:
        if st.button("🗑️ Seçilenleri Sil", disabled=not selected_ids, use_container_width=True):
            conn = get_connection()
            conn.executemany(
                "UPDATE jobs SET is_hidden = 1 WHERE job_id = ?",
                [(int(i),) for i in selected_ids],
            )
            conn.commit()
            conn.close()
            st.success(f"{len(selected_ids)} ilan silindi.")
            st.rerun()

    with col_b:
        if st.button("✍️ Seçilenler İçin CV Üret", type="primary", disabled=not selected_ids, use_container_width=True):
            from matching.cv_generator import (
                generate_cv_and_cover_letter,
                save_documents_to_db,
            )

            st.warning(f"{len(selected_ids)} ilan için CV üretilecek (~{len(selected_ids) * 2} dk)")

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
                        raise RuntimeError(f"LLM bos CV dondurdu (jid={jid})")
                    save_documents_to_db(jid, cv_text, cover_text)

                    from matching.cv_generator import save_files_to_disk
                    save_files_to_disk(jid, job["company"], job["job_title"])
                except Exception as e:
                    st.error(f"Hata ({jid}): {e}")

                progress.progress((idx + 1) / len(selected_ids))

            conn.close()
            status.success("Tamamlandı!")
            st.rerun()


# ============================================================
# SAYFA 2 — CV ÜRETİLENLER
# ============================================================
elif page == "📄 CV Üretilenler":
    st.subheader("📄 CV Üretilen İlanlar")
    st.caption("CV üretilmiş, henüz başvurulmamış ilanlar. İndirmek için satırları işaretle.")

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
        st.info("Henüz CV üretilmedi.")
    else:
        df_cv = pd.DataFrame(
            [list(r) for r in cv_rows],
            columns=["id", "Pozisyon", "Şirket", "Konum", "Match", "Öncelik", "CV Tarihi"]
        )
        df_cv["CV Tarihi"] = df_cv["CV Tarihi"].astype(str).str[:16].str.replace("T", " ")
        df_cv["Uzaklık"] = df_cv["Konum"].apply(lambda x: format_distance(get_distance(x)))

        # Sutun sirasi: Sec, CV Tarihi, Match, id, Pozisyon, Şirket, Konum, Uzaklik, Öncelik
        df_cv = df_cv[["id", "Pozisyon", "Şirket", "Konum", "Uzaklık", "Match", "Öncelik", "CV Tarihi"]]
        df_cv.insert(0, "Seç", False)
        df_cv = df_cv[["Seç", "CV Tarihi", "Match", "id", "Pozisyon", "Şirket", "Konum", "Uzaklık", "Öncelik"]]

        edited_cv = st.data_editor(
            df_cv,
            use_container_width=True,
            hide_index=True,
            height=min(400, 60 + 35 * len(df_cv)),
            column_config={
                "Seç": st.column_config.CheckboxColumn("Seç", default=False, width=40),
                "CV Tarihi": st.column_config.TextColumn("CV Tarihi", disabled=True, width=130),
                "Match": st.column_config.TextColumn("Match", disabled=True, width=110),
                "id": st.column_config.NumberColumn("ID", disabled=True, width=50),
                "Pozisyon": st.column_config.TextColumn("Pozisyon", disabled=True, width=220),
                "Şirket": st.column_config.TextColumn("Şirket", disabled=True, width=140),
                "Konum": st.column_config.TextColumn("Konum", disabled=True, width=120),
                "Uzaklık": st.column_config.TextColumn("Uzaklık", disabled=True, width=80),
                "Öncelik": st.column_config.TextColumn("Öncelik", disabled=True, width=70),
            },
            disabled=["CV Tarihi", "Match", "id", "Pozisyon", "Şirket", "Konum", "Uzaklık", "Öncelik"],
            key="cv_editor",
        )

        selected_ids = edited_cv[edited_cv["Seç"] == True]["id"].tolist()
        st.caption(f"Seçili: **{len(selected_ids)}** ilan")

        # Secili ilanlarin detayini goster
        if selected_ids:
            st.divider()
            with st.expander(f"📋 Seçili İlan Detayı ({len(selected_ids)} ilan)", expanded=True):
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
                    st.caption(f"ID: {detail[0]} | {detail[3]} | Match: {detail[5]} | Öncelik: {detail[6]} | Kaynak: {detail[8]}")
                    if detail[7]:
                        st.markdown(f"🔗 **[İlanı Aç]({detail[7]})**")
                    if detail[4]:
                        with st.expander("📄 İlan Metnini Göster", expanded=False):
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

        # Secili ilanlar icin indirme bloklari
        if selected_ids:
            from matching.cv_generator import _build_filename

            st.divider()
            st.markdown("**📥 İndir:**")

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
                            key=f"dl_cv_docx_{jid}", use_container_width=True)
                else:
                    c1.caption("CV DOCX yok")

                if cv_pdf_path.exists():
                    with open(cv_pdf_path, "rb") as f:
                        c2.download_button("📥 CV PDF", data=f.read(),
                            file_name=f"{cv_name}.pdf",
                            mime="application/pdf",
                            key=f"dl_cv_pdf_{jid}", use_container_width=True)
                else:
                    c2.caption("CV PDF yok")

                if cl_docx_path.exists():
                    with open(cl_docx_path, "rb") as f:
                        c3.download_button("📥 CL DOCX", data=f.read(),
                            file_name=f"{cover_name}.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            key=f"dl_cl_docx_{jid}", use_container_width=True)
                else:
                    c3.caption("CL DOCX yok")

                if cl_pdf_path.exists():
                    with open(cl_pdf_path, "rb") as f:
                        c4.download_button("📥 CL PDF", data=f.read(),
                            file_name=f"{cover_name}.pdf",
                            mime="application/pdf",
                            key=f"dl_cl_pdf_{jid}", use_container_width=True)
                else:
                    c4.caption("CL PDF yok")

                st.markdown("")

            st.divider()

        if st.button("✅ Seçilenleri Başvuruldu İşaretle",
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
            st.success(f"{len(selected_ids)} ilan başvuruldu olarak işaretlendi.")
            st.rerun()

# ============================================================
# SAYFA 3 — BAŞVURULANLAR
# ============================================================
elif page == "✅ Başvurulanlar":
    st.subheader("✅ Başvurulan İlanlar")
    st.caption("Başvurduğun ilanlar. Yanlışlıkla işaretlediysen geri alabilirsin.")

    conn = get_connection()
    applied_rows = conn.execute("""
        SELECT
            j.job_id as id,
            j.job_title as Pozisyon,
            j.company as Şirket,
            j.location as Konum,
            j.match_category as Match,
            j.priority as Öncelik,
            COALESCE(d.updated_at, d.created_at, '') as [CV Tarihi],
            COALESCE(j.applied_at, '') as [Başvuru Tarihi],
            COALESCE(j.application_status, '') as [Durum],
            (SELECT COUNT(*) FROM application_emails ae WHERE ae.job_id = j.job_id) as [Yanit]
        FROM jobs j
        LEFT JOIN job_documents d ON d.job_id = j.job_id
        WHERE j.is_applied = 1
          AND j.is_hidden = 0
        ORDER BY j.applied_at DESC
    """).fetchall()
    conn.close()

    if not applied_rows:
        st.info("Henüz başvurulan ilan yok.")
    else:
        df_applied = pd.DataFrame(
            [list(r) for r in applied_rows],
            columns=["id", "Pozisyon", "Şirket", "Konum", "Match", "Öncelik", "CV Tarihi", "Başvuru Tarihi", "Durum", "Yanit"]
        )
        df_applied["CV Tarihi"] = df_applied["CV Tarihi"].astype(str).str[:16].str.replace("T", " ")
        df_applied["Uzaklık"] = df_applied["Konum"].apply(lambda x: format_distance(get_distance(x)))

        # Durum ikonlari
        icons = {"interview": "📞 Mülakat", "rejection": "❌ Ret", "offer": "🎉 Teklif", "info": "ℹ️ Bilgi"}
        df_applied["Durum"] = df_applied["Durum"].apply(lambda x: icons.get(str(x).lower(), x or "—"))

        df_applied = df_applied[["id", "Pozisyon", "Şirket", "Konum", "Uzaklık", "Match", "Öncelik", "Durum", "Yanit", "CV Tarihi", "Başvuru Tarihi"]]
        df_applied.insert(0, "Seç", False)
        df_applied = df_applied[["Seç", "CV Tarihi", "Başvuru Tarihi", "Match", "id", "Pozisyon", "Şirket", "Konum", "Uzaklık", "Durum", "Yanit", "Öncelik"]]

        edited_applied = st.data_editor(
            df_applied,
            use_container_width=True,
            hide_index=True,
            height=min(400, 60 + 35 * len(df_applied)),
            column_config={
                "Seç": st.column_config.CheckboxColumn("Seç", default=False, width=40),
                "CV Tarihi": st.column_config.TextColumn("CV Tarihi", disabled=True, width=130),
                "Başvuru Tarihi": st.column_config.TextColumn("Başvuru Tarihi", disabled=True, width=130),
                "Match": st.column_config.TextColumn("Match", disabled=True, width=110),
                "id": st.column_config.NumberColumn("ID", disabled=True, width=50),
                "Pozisyon": st.column_config.TextColumn("Pozisyon", disabled=True, width=220),
                "Şirket": st.column_config.TextColumn("Şirket", disabled=True, width=140),
                "Konum": st.column_config.TextColumn("Konum", disabled=True, width=120),
                "Uzaklık": st.column_config.TextColumn("Uzaklık", disabled=True, width=80),
                "Durum": st.column_config.TextColumn("Durum", disabled=True, width=110),
                "Yanit": st.column_config.NumberColumn("📬", disabled=True, width=50),
                "Öncelik": st.column_config.TextColumn("Öncelik", disabled=True, width=70),
            },
            disabled=["CV Tarihi", "Başvuru Tarihi", "Match", "id", "Pozisyon", "Şirket", "Konum", "Uzaklık", "Durum", "Yanit", "Öncelik"],
            key="applied_editor",
        )

        selected_ids = edited_applied[edited_applied["Seç"] == True]["id"].tolist()

        if len(selected_ids) > 1:
            selected_ids = [selected_ids[-1]]

        st.caption(f"Seçili: **{len(selected_ids)}** ilan")

        # Secili ilanlarin detayini goster
        if selected_ids:
            st.divider()
            with st.expander(f"📋 Seçili İlan Detayı ({len(selected_ids)} ilan)", expanded=True):
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
                    st.caption(f"ID: {detail[0]} | {detail[3]} | Match: {detail[5]} | Öncelik: {detail[6]} | Kaynak: {detail[8]}")
                    if detail[7]:
                        st.markdown(f"🔗 **[İlanı Aç]({detail[7]})**")
                    if detail[4]:
                        with st.expander("📄 İlan Metnini Göster", expanded=False):
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

                    # Bu ilana gelen yanitlar
                    conn2 = get_connection()
                    responses = conn2.execute("""
                        SELECT sender, subject, category, confidence, reason, received_at
                        FROM application_emails
                        WHERE job_id = ?
                        ORDER BY processed_at DESC
                    """, (jid,)).fetchall()
                    conn2.close()

                    if responses:
                        st.markdown("**📬 Bu ilana gelen yanıtlar:**")
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
                        st.caption("📭 Bu ilana henüz yanıt gelmedi.")

                    st.markdown("---")
                conn.close()

        if st.button("↩️ Başvuruyu Geri Al", disabled=not selected_ids):
            conn = get_connection()
            conn.executemany(
                "UPDATE jobs SET is_applied = 0, applied_at = NULL WHERE job_id = ?",
                [(int(i),) for i in selected_ids],
            )
            conn.commit()
            conn.close()
            st.success("Basvuru geri alindi.")
            st.rerun()

        st.divider()
        st.markdown("**📥 İndir:**")
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
                        key=f"a_cv_docx_{jid}", use_container_width=True)
                    cv_pdf = generate_pdf_bytes(cv_docx)
                    col2.download_button("📥 CV PDF", data=cv_pdf,
                        file_name=f"{cv_name}.pdf", mime="application/pdf",
                        key=f"a_cv_pdf_{jid}", use_container_width=True)
                except Exception as e:
                    st.warning(f"CV hata: {e}")
                try:
                    cover_docx = generate_docx_bytes(cover_md or "")
                    col3.download_button("📥 CL DOCX", data=cover_docx,
                        file_name=f"{cover_name}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key=f"a_cl_docx_{jid}", use_container_width=True)
                    cover_pdf = generate_pdf_bytes(cover_docx)
                    col4.download_button("📥 CL PDF", data=cover_pdf,
                        file_name=f"{cover_name}.pdf", mime="application/pdf",
                        key=f"a_cl_pdf_{jid}", use_container_width=True)
                except Exception as e:
                    st.warning(f"CL hata: {e}")


# ============================================================
# SAYFA 4 — GİZLENENLER
# ============================================================
elif page == "🗑️ Gizlenen":
    st.subheader("🗑️ Gizlenen İlanlar")
    st.caption("Sildiğin ilanlar. Yanlışlıkla sildiysen geri alabilirsin.")

    conn = get_connection()
    hidden_rows = conn.execute("""
        SELECT
            j.job_id as id,
            j.job_title as Pozisyon,
            j.company as Şirket,
            j.location as Konum,
            j.match_category as Match,
            j.priority as Öncelik
        FROM jobs j
        WHERE j.is_hidden = 1
        ORDER BY j.job_id DESC
        LIMIT 500
    """).fetchall()
    conn.close()

    if not hidden_rows:
        st.info("Gizlenen ilan yok.")
    else:
        df_hidden = pd.DataFrame(
            [list(r) for r in hidden_rows],
            columns=["id", "Pozisyon", "Şirket", "Konum", "Match", "Öncelik"]
        )
        df_hidden.insert(0, "Seç", False)

        edited_hidden = st.data_editor(
            df_hidden,
            use_container_width=True,
            hide_index=True,
            height=min(400, 60 + 35 * len(df_hidden)),
            column_config={
                "Seç": st.column_config.CheckboxColumn("Seç", default=False),
                "id": st.column_config.NumberColumn("ID", disabled=True, width="small"),
            },
            disabled=["id", "Pozisyon", "Şirket", "Konum", "Match", "Öncelik"],
            key="hidden_editor",
        )

        selected_ids = edited_hidden[edited_hidden["Seç"] == True]["id"].tolist()

        if len(selected_ids) > 1:
            selected_ids = [selected_ids[-1]]

        st.caption(f"Seçili: **{len(selected_ids)}** ilan")

        if st.button("↩️ Geri Getir", disabled=not selected_ids):
            conn = get_connection()
            conn.executemany(
                "UPDATE jobs SET is_hidden = 0 WHERE job_id = ?",
                [(int(i),) for i in selected_ids],
            )
            conn.commit()
            conn.close()
            st.success("Ilan geri getirildi.")
            st.rerun()


# ============================================================
# SAYFA 5 — MANUEL İLAN
# ============================================================
elif page == "✍️ Manuel İlan":
    st.subheader("✍️ Manuel İlan Ekle")
    st.caption("LinkedIn, Indeed veya şirket sitesinden bulduğun ilanlar için CV + Cover Letter üret.")

    with st.form("manual_job_form", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            url = st.text_input("İlan URL *", placeholder="https://...")
            position = st.text_input("Pozisyon *", placeholder="Business Operations Specialist")
        with col2:
            company = st.text_input("Şirket *", placeholder="Acme B.V.")
            location = st.text_input("Konum", placeholder="Amsterdam")

        description = st.text_area(
            "İlan Metni *",
            placeholder="İlan açıklamasını buraya yapıştır...",
            height=300,
        )

        submitted = st.form_submit_button("✍️ CV + Cover Letter Üret", type="primary")

    if submitted:
        # Validasyon
        errors = []
        if not url or not url.strip():
            errors.append("URL zorunlu")
        if not position or not position.strip():
            errors.append("Pozisyon zorunlu")
        if not company or not company.strip():
            errors.append("Şirket zorunlu")
        if not description or not description.strip():
            errors.append("İlan metni zorunlu")

        if errors:
            for err in errors:
                st.error(err)
        else:
            url = url.strip()
            position = position.strip()
            company = company.strip()
            location = location.strip() if location else ""
            description = description.strip()

            # URL havuzda var mi kontrolu
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
                    f"⚠️ Bu URL zaten Havuz'da: **[ID={existing[0]}] {existing[2]} — {existing[1]}**"
                )
                st.info(
                    "Aşağıdaki butonu kullanarak bu manuel ilanı yine de ekleyebilirsin. "
                    "Havuz'daki eski kaydı silmek için Gizlenen sayfasını kullan."
                )

            # Session state'e kaydet
            st.session_state["manual_pending"] = {
                "url": url,
                "position": position,
                "company": company,
                "location": location,
                "description": description,
                "existing_id": existing[0] if existing else None,
            }
            st.rerun()

    # Bekleyen manuel ilan varsa uret
    if "manual_pending" in st.session_state:
        pending = st.session_state["manual_pending"]

        st.divider()
        st.markdown(f"### 📄 {pending['company']} — {pending['position']}")
        st.caption(f"{pending['location'] or '—'} · {pending['url']}")

        col_a, col_b = st.columns([1, 3])
        with col_a:
            if st.button("✍️ CV Üret", type="primary"):
                with st.spinner("CV üretiliyor... (~2 dk)"):
                    try:
                        from matching.cv_generator import (
                            generate_cv_and_cover_letter,
                            save_documents_to_db,
                            save_files_to_disk,
                        )
                        from data.database import get_connection as _gc
                        from datetime import datetime as _dt

                        # job_id olustur: mevcut max + 1
                        conn = _gc()
                        max_id = conn.execute("SELECT COALESCE(MAX(job_id), 0) FROM jobs").fetchone()[0]
                        new_id = max_id + 1

                        # jobs tablosuna ekle
                        conn.execute("""
                            INSERT INTO jobs (
                                job_id, job_title, company, location,
                                job_description, match_category, priority,
                                posted_date, date_found
                            )
                            VALUES (?, ?, ?, ?, ?, 'Manuel', 'High', ?, ?)
                        """, (
                            new_id,
                            pending["position"],
                            pending["company"],
                            pending["location"],
                            pending["description"],
                            _dt.now().strftime("%Y-%m-%d"),
                            _dt.now().strftime("%Y-%m-%d %H:%M"),
                        ))

                        # job_sources'a ekle
                        conn.execute("""
                            INSERT INTO job_sources (
                                job_id, source, source_url, date_found, is_primary
                            )
                            VALUES (?, 'Manuel', ?, ?, 1)
                        """, (
                            new_id,
                            pending["url"],
                            _dt.now().strftime("%Y-%m-%d %H:%M"),
                        ))
                        conn.commit()
                        conn.close()

                        # CV uret
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
                            raise RuntimeError("LLM bos CV dondurdu")

                        save_documents_to_db(new_id, cv_text, cover_text)
                        save_files_to_disk(new_id, pending["company"], pending["position"])

                        st.success(f"✅ CV üretildi (ID={new_id})")
                        del st.session_state["manual_pending"]
                        st.rerun()

                    except Exception as e:
                        st.error(f"Hata: {e}")

        with col_b:
            if st.button("❌ İptal"):
                del st.session_state["manual_pending"]
                st.rerun()

    # Manuel ilanlarin listesi
    st.divider()
    st.subheader("📁 Eklenmiş Manuel İlanlar")

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
        WHERE j.match_category = 'Manuel'
          AND j.is_hidden = 0
        ORDER BY j.job_id DESC
    """).fetchall()
    conn.close()

    if not manual_rows:
        st.info("Henüz manuel ilan eklenmemiş.")
    else:
        df_manual = pd.DataFrame(
            [list(r) for r in manual_rows],
            columns=["id", "Pozisyon", "Şirket", "Konum", "URL", "CV Tarihi"]
        )
        df_manual["CV Tarihi"] = df_manual["CV Tarihi"].astype(str).str[:16].str.replace("T", " ")
        df_manual["Uzaklık"] = df_manual["Konum"].apply(lambda x: format_distance(get_distance(x)) if x else "?")
        df_manual = df_manual[["id", "Pozisyon", "Şirket", "Konum", "Uzaklık", "URL", "CV Tarihi"]]
        df_manual.insert(0, "Seç", False)

        edited_manual = st.data_editor(
            df_manual,
            use_container_width=True,
            hide_index=True,
            height=min(400, 60 + 35 * len(df_manual)),
            column_config={
                "Seç": st.column_config.CheckboxColumn("Seç", default=False, width=40),
                "id": st.column_config.NumberColumn("ID", disabled=True, width=50),
                "Pozisyon": st.column_config.TextColumn("Pozisyon", disabled=True, width=200),
                "Şirket": st.column_config.TextColumn("Şirket", disabled=True, width=140),
                "Konum": st.column_config.TextColumn("Konum", disabled=True, width=120),
                "Uzaklık": st.column_config.TextColumn("Uzaklık", disabled=True, width=80),
                "URL": st.column_config.LinkColumn("URL", disabled=True, width=200, display_text="🔗 Aç"),
                "CV Tarihi": st.column_config.TextColumn("CV Tarihi", disabled=True, width=130),
            },
            disabled=["id", "Pozisyon", "Şirket", "Konum", "Uzaklık", "URL", "CV Tarihi"],
            key="manual_editor",
        )

        selected_ids = edited_manual[edited_manual["Seç"] == True]["id"].tolist()

        if len(selected_ids) > 1:
            selected_ids = [selected_ids[-1]]

        st.caption(f"Seçili: **{len(selected_ids)}** ilan")

        # Indirme butonlari
        if len(selected_ids) == 1:
            jid = int(selected_ids[0])
            row = next((r for r in manual_rows if r[0] == jid), None)
            if row:
                title = row[1]
                company = row[2]
                from pathlib import Path as _P

                st.divider()
                st.markdown(f"**Seçili:** {company} — {title}")

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
                                key=f"manual_dl_{path}", use_container_width=True)
                    else:
                        col.caption(f"{label} yok")

        # Silme
        if selected_ids:
            if st.button("🗑️ Seçilen Manuel İlanı Sil", disabled=not selected_ids):
                conn = get_connection()
                jid = int(selected_ids[0])
                for table in ["job_documents", "job_matches", "job_match_queue", "job_sources"]:
                    conn.execute(f"DELETE FROM {table} WHERE job_id = ?", (jid,))
                conn.execute("DELETE FROM jobs WHERE job_id = ?", (jid,))
                conn.commit()
                conn.close()

                # Disk dosyalarini sil
                from pathlib import Path as _P2
                for f in _P2("static/cv").glob(f"{jid}_*"):
                    f.unlink()

                st.success(f"Manuel ilan (ID={jid}) silindi.")
                st.rerun()


# ============================================================
# SAYFA 6 — YANITLAR
# ============================================================
elif page == "📬 Yanıtlar":
    st.subheader("📬 Başvuru Yanıtları")
    st.caption("Gmail'den otomatik olarak çekilen başvuru yanıtları.")

    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("🔄 Sheets'ten Sync Et", type="primary"):
            try:
                import sys as _sys
                from pathlib import Path as _P
                _sys.path.insert(0, str(_P.home() / "job-agent-integrations"))
                from dotenv import load_dotenv
                load_dotenv(_P.home() / "job-agent-integrations" / ".env")
                load_dotenv(_P.home() / "job-agent" / ".env")

                from integrations.gmail_tracker import sync_sheet_to_db
                with st.spinner("Sheets okunuyor, LLM sınıflandırıyor... (~30 sn)"):
                    stats = sync_sheet_to_db(verbose=False)
                st.success(
                    f"Sync tamamlandı: "
                    f"{stats['new']} yeni, "
                    f"{stats['classified']} sınıflandırıldı, "
                    f"{stats['matched']} eşleşti"
                )
                st.rerun()
            except Exception as e:
                st.error(f"Sync hatası: {e}")

    with col2:
        st.caption(
            "💡 **Nasıl çalışır:** Gmail → Make.com → Google Sheets → bu sayfa. "
            "Yeni mailler geldiğinde **Sync Et** butonuna bas."
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
        st.info("Henüz yanıt yok. **Sync Et** butonuna bas veya Sheets'e yeni bir mail ekle.")
    else:
        categories = sorted(set(r[3] for r in rows if r[3]))
        selected_cats = st.multiselect(
            "Kategori filtrele", categories, default=categories,
        )

        filtered = [r for r in rows if r[3] in selected_cats]
        st.caption(f"Toplam: **{len(filtered)}** yanıt")

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
                    st.markdown(f"🔗 **İlgili ilan:** {company} — {job_title}")

                if reason:
                    st.caption(f"💭 **LLM gerekçesi:** {reason}")

                if confidence:
                    st.caption(f"🎯 Güven: {confidence:.0%}")
