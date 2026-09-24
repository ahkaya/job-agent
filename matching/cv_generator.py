from dotenv import load_dotenv
load_dotenv()

import os
import json
import re
from io import BytesIO
from datetime import datetime

from openai import OpenAI
from docx import Document
from docx.shared import Pt, RGBColor


MODEL_NAME = "glm-5.3-flash"
BASE_URL = "https://api.z.ai/api/paas/v4/"


CV_PROMPT = """You are an expert CV writer and ATS optimization specialist with 15 years of experience in the Dutch and international job markets.

=== INPUTS ===
1. Master Profile (YAML) - the ONLY source of truth about the candidate.
2. Job posting - a single job to tailor the CV for.

=== ABSOLUTE DATA INTEGRITY RULES (NON-NEGOTIABLE) ===
1. NEVER invent, fabricate, exaggerate, or misrepresent: skills, responsibilities, achievements, metrics, dates, job titles, education, certifications, revenue, profit, cost savings, team size, or performance percentages.
2. If a skill, tool, or experience is NOT explicitly present in the Master Profile, DO NOT include it. Instead, emphasize TRANSFERABLE evidence that IS in the profile.
3. Ph.D. MUST ALWAYS be described as "thesis stage" or "Ph.D. candidate" - NEVER as "completed" or "Ph.D." without qualification.
4. ALL metrics MUST come from the verified_metrics field in the profile. Do not round, extrapolate, or invent metrics.
5. NEVER overstate technical skills. If profile says "foundational academic" for Python, write "foundational academic exposure to Python" - NOT "Python programming skills".
6. If a detail is uncertain, missing, or ambiguous, OMIT it entirely. Do not guess or infer.
7. You may rephrase, reorder, and condense existing content. You may NOT invent or interpolate.

=== CV FORMAT RULES (ATS-COMPLIANT) ===
- MAXIMUM 1.5 pages. Target: 400-500 words for the CV body. This is a HARD limit.
- Use ONLY plain text. NO LaTeX, NO math symbols, NO backslashes, NO asterisks, NO markdown bold.
- Allowed characters: plain text, "- " for bullets, "## " for section headings.
- DO NOT use any special formatting symbols.
- Header: FIRST line MUST be '# Ahmet Kaya' (H1, will be bold). Then contact lines as plain text.
  Candidate Name
  Phone | Email
  Location | Work authorization
  Languages (brief)

- Sections (in this EXACT order, omit if not applicable):
  ## Professional Summary
  (2-3 sentences. Employer-centric. ALWAYS WRITE IN ENGLISH, even if the job posting is in Dutch, German, French or any other language. Dutch job titles and company names MAY be kept in original form. Include 1-2 verified metrics if relevant.)
  ## Core Competencies
  (5-7 bullet points. Each 5-10 words. Use EXACT keywords from the job description where truthful.)
  ## Projects
  (MUST INCLUDE the "Job-Agent: Personal Job Search Automation" project for
   the following role families: Business Operations, Business Analyst, Operations,
   Program/Project Coordinator, Data, Tech, Automation, Product, Marketing.
   Format: bold project name, one-line context, 2-3 bullets (Python, REST APIs,
   LLM APIs, Streamlit). ALWAYS include the GitHub URL "github.com/ahkaya/job-agent"
   in the project line or as a separate link. This is NOT optional for these roles.
   OMIT this section ONLY for: warehouse, manual labor, driving, production,
   cleaning, security, or unskilled entry-level roles.)

  ## Professional Experience
  (ONLY the 3 most relevant roles. Each role: company, title, dates, then 2-4 bullets MAX.)
  ## Education
  (Degree, institution, dates, thesis topic if relevant. Ph.D. MUST say "thesis stage".)
  ## Technical Skills
  (Only skills explicitly in the profile. Include proficiency level honestly.)
  ## Certifications
  (Only certifications in the profile. One line each.)

=== TAILORING STRATEGY (FOLLOW THIS PROCESS) ===
Step 1: Extract the top 5-8 selection criteria from the job description (skills, tools, responsibilities, keywords).
Step 2: For EACH role in the profile, ask: Does this role provide evidence for at least 2 of the top criteria? If NO, OMIT the role entirely.
Step 3: Rewrite bullet points to mirror the job's exact terminology (where truthful). Use the job's words, not synonyms.
Step 4: Reorder roles and bullets: most relevant first.
Step 5: PROJECTS: ALWAYS include the Job-Agent project for Business Operations,
        Analyst, Coordinator, Data, Tech, Automation, Product, and Marketing roles.
        Only OMIT for manual/warehouse/production/driving roles.
Step 6: Use the STAR-K method for bullets: Result/Action by Method, Scope/Impact.
Step 7: For each role, MAXIMUM 3-4 bullets. Older roles (pre-2015): 1-2 bullets MAX.

=== COVER LETTER RULES ===
- MAXIMUM 250 words. HARD limit.
- Formal tone. Address to "Dear Hiring Manager," at the company.
- Structure:
  Paragraph 1: Hook - why this role, why this company (1-2 sentences).
  Paragraph 2: Body - 2-3 concrete evidence matches from the profile (with metrics if available).
  Paragraph 3: Close - call to action, availability, thank you.
- Same data integrity rules apply.
- Plain text only. No markdown, no bold, no bullet points.

========== EXACT FORMAT EXAMPLE (FOLLOW THIS PRECISELY) ==========
Below is an example of the EXACT markdown format you MUST use.
Copy this structure precisely for the candidate:

# Ahmet Kaya
+31 6 15034058 | aaahmetkayaaa@gmail.com
Almelo, Netherlands | Eligible to work in the Netherlands
Languages: English (fluent), Turkish (native), Dutch (A1/A2, actively learning)

## Professional Summary
2-3 sentence summary here, tailored to the job.

## Core Competencies
- Competency 1
- Competency 2
- Competency 3

## Professional Experience
**Company Name A** - **Job Title A** | 2021 - 2025
- Achievement bullet 1
- Achievement bullet 2

**Company Name B** - **Job Title B** | 2019 - 2021
- Achievement bullet 1
- Achievement bullet 2

## Education
**Ph.D. in Field (thesis stage)**, University Name, 2019 - present

## Technical Skills
- Skill 1
- Skill 2

## Certifications
- Certification 1

CRITICAL FORMAT RULES:
1. The first line MUST be "# Ahmet Kaya" (single #, space, name).
2. Every section heading MUST use "## " prefix.
3. Every company name and job title MUST be wrapped in ** double asterisks **.
4. Every bullet MUST start with "- ".
5. NEVER use markdown bold for anything other than company names and job titles.
6. Do NOT add extra # or ## inside paragraphs.

=== OUTPUT LANGUAGE (STRICT) ===
The CV and cover letter MUST ALWAYS be written in ENGLISH.
Even if the job posting is fully in Dutch, German, French, or any other language,
output MUST be in English.
Dutch-specific job titles, company names, or technical terms MAY be kept in original form.

=== OUTPUT FORMAT ===
Return ONLY valid JSON:
{
  "cv": "full CV as plain text with ## section headings and - bullets",
  "cover_letter": "full cover letter as plain text, no markdown"
}
"""


def _build_client():
    api_key = os.environ.get("GLM_API_KEY")
    if not api_key:
        raise RuntimeError("GLM_API_KEY is not set")
    return OpenAI(api_key=api_key, base_url=BASE_URL)


def _format_master_profile(profile_dict):
    import yaml
    return yaml.dump(profile_dict, allow_unicode=True, sort_keys=False)


def generate_cv_and_cover_letter(job: dict) -> dict:
    """LLM ile CV ve cover letter uretir."""
    from matching.gemini_matcher import load_matching_config

    master_profile, _ = load_matching_config()
    client = _build_client()

    user_prompt = f"""# Master Profile
{_format_master_profile(master_profile)}

# Job Posting
Title: {job.get('job_title', '')}
Company: {job.get('company', '')}
Location: {job.get('location', '')}

Description:
{job.get('job_description', '')[:6000]}
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": CV_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
        max_tokens=8000,
        extra_body={
            "thinking": {"type": "enabled"},
            "reasoning_effort": "high",
        },
    )

    content = response.choices[0].message.content

    # Toleransli JSON parse
    if not content or not content.strip():
        # Bazen LLM bos doner, tekrar dene
        raise RuntimeError(f"LLM bos cevap dondu (finish_reason={response.choices[0].finish_reason})")

    raw = content.strip()
    # Markdown fence temizle
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()
        if raw.startswith("json"):
            raw = raw[4:].strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[JSON ERROR] Raw content ilk 500 char:")
        print(repr(raw[:500]))
        print(f"[JSON ERROR] finish_reason={response.choices[0].finish_reason}")
        print(f"[JSON ERROR] usage={response.usage}")
        raise

    cv_text = result.get("cv", "")
    cover_text = result.get("cover_letter", "")

    cv_text, cover_text, issues, cv_words, cl_words = _validate_cv_output(cv_text, cover_text)

    if issues:
        print(f"[VALIDATION] {len(issues)} issue(s):")
        for issue in issues:
            print(f"  - {issue}")
    print(f"[VALIDATION] CV: {cv_words} kelime, Cover: {cl_words} kelime")

    return {
        "cv": cv_text,
        "cover_letter": cover_text,
    }


def save_documents_to_db(job_id, cv_markdown, cover_markdown):
    """CV ve cover letter'i DB'ye kaydeder."""
    from data.database import get_connection

    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat(timespec="seconds")

    cursor.execute("""
        INSERT INTO job_documents (job_id, cv_markdown, cover_letter_markdown, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(job_id) DO UPDATE SET
            cv_markdown = excluded.cv_markdown,
            cover_letter_markdown = excluded.cover_letter_markdown,
            updated_at = excluded.updated_at
    """, (job_id, cv_markdown, cover_markdown, now, now))

    conn.commit()
    conn.close()


def get_documents_from_db(job_id):
    """DB'den CV ve cover letter ceker."""
    from data.database import get_connection

    conn = get_connection()
    row = conn.execute("""
        SELECT cv_markdown, cover_letter_markdown
        FROM job_documents WHERE job_id = ?
    """, (job_id,)).fetchone()
    conn.close()

    if not row:
        return None
    return {"cv": row[0], "cover_letter": row[1]}


def _sanitize_filename(text, max_len=40):
    """Sirket/pozisyon ismini dosya adina uygun hale getirir."""
    text = str(text or "").strip()
    tr_map = {
        "ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
        "Ç": "C", "Ğ": "G", "İ": "I", "Ö": "O", "Ş": "S", "Ü": "U",
        "ß": "ss", "é": "e", "è": "e", "ê": "e", "á": "a", "à": "a",
        "â": "a", "ñ": "n", "&": "and",
    }
    for k, v in tr_map.items():
        text = text.replace(k, v)
    text = re.sub(r"[^A-Za-z0-9\s\-]", "", text)
    text = re.sub(r"\s+", "_", text.strip())
    text = re.sub(r"_+", "_", text)
    return text[:max_len].strip("_") or "Unknown"


def _build_filename(job, doc_type):
    """job ve doc_type'tan dosya adi uretir (uzantisiz)."""
    from datetime import date as _date
    today = _date.today().isoformat()
    company = _sanitize_filename(job.get("company", "Unknown"), 30)
    title = _sanitize_filename(job.get("job_title", "Position"), 40)
    return f"{today}_{company}_{title}_{doc_type}"


def _validate_cv_output(cv_text, cover_text):
    """LLM ciktisini dogrular ve temizler."""
    issues = []

    # 1. Yasakli karakterler
    forbidden = [
        (r"\\\(", "("), (r"\\\)", ")"),
        (r"\\cdot", "*"), (r"\\times", "x"), (r"\\_", "_"),
    ]
    for pattern, repl in forbidden:
        if re.search(pattern, cv_text):
            cv_text = re.sub(pattern, repl, cv_text)
            issues.append(f"cv: yasakli pattern temizlendi: {pattern}")
        if re.search(pattern, cover_text):
            cover_text = re.sub(pattern, repl, cover_text)
            issues.append(f"cl: yasakli pattern temizlendi: {pattern}")

    # 2. Ph.D. kontrolu
    if "Ph.D." in cv_text:
        lower = cv_text.lower()
        has_thesis = "thesis" in lower or "candidate" in lower
        has_completed = re.search(r"ph\.?d\.?\s+(completed|degree|holder)", lower)
        if has_completed and not has_thesis:
            cv_text = cv_text.replace("Ph.D.", "Ph.D. candidate (thesis stage)")
            issues.append("cv: Ph.D. -> 'candidate (thesis stage)' duzeltildi")

    # 3. Kelime sayisi
    cv_words = len(cv_text.split())
    cover_words = len(cover_text.split())
    if cv_words > 600:
        issues.append(f"cv: UYARI kelime sayisi {cv_words} (>600)")
    if cover_words > 320:
        issues.append(f"cl: UYARI kelime sayisi {cover_words} (>320)")

    return cv_text, cover_text, issues, cv_words, cover_words


def _clean_text(text):
    """LaTeX/markdown escape kalintilarini temizler."""
    import re as _re
    if not text:
        return ""
    t = str(text)
    t = t.replace("\\(", "(")
    t = t.replace("\\)", ")")
    t = t.replace("\\cdot", "*")
    t = t.replace("\\times", "x")
    t = t.replace("\\%", "%")
    t = t.replace("\\&", "&")
    t = t.replace("\\_", "_")
    t = _re.sub(r"\\([^nrt])", lambda m: m.group(1), t)
    t = _re.sub(r"^---+$", "", t, flags=_re.MULTILINE)
    return t


def _markdown_to_docx(markdown_text):
    """Basit markdown'u DOCX'e cevirir (bold destegi ile)."""
    markdown_text = _clean_text(markdown_text)
    doc = Document()

    for section in doc.sections:
        section.top_margin = Pt(36)
        section.bottom_margin = Pt(36)
        section.left_margin = Pt(54)
        section.right_margin = Pt(54)

    for line in markdown_text.split("\n"):
        stripped = line.rstrip()
        if not stripped.strip():
            continue

        # H1 (isim) - buyuk bold + mavi
        if stripped.startswith("# "):
            p = doc.add_paragraph()
            run = p.add_run(stripped[2:])
            run.bold = True
            run.font.size = Pt(18)
            run.font.color.rgb = RGBColor(0x1A, 0x4D, 0x80)
            p.paragraph_format.keep_with_next = True

        # H2 (bolum basligi) - mavi bold
        elif stripped.startswith("## "):
            p = doc.add_paragraph()
            run = p.add_run(stripped[3:])
            run.bold = True
            run.font.size = Pt(12)
            run.font.color.rgb = RGBColor(0x1A, 0x4D, 0x80)
            p.paragraph_format.keep_with_next = True

        # H3 - bold
        elif stripped.startswith("### "):
            p = doc.add_paragraph()
            run = p.add_run(stripped[4:])
            run.bold = True
            run.font.size = Pt(11)
            p.paragraph_format.keep_with_next = True

        # Bullet
        elif stripped.startswith("- ") or stripped.startswith("* "):
            p = doc.add_paragraph(style="List Bullet")
            _add_runs_with_bold(p, stripped[2:])

        # Numbered
        elif re.match(r"^\d+\.\s", stripped):
            p = doc.add_paragraph(style="List Number")
            _add_runs_with_bold(p, re.sub(r"^\d+\.\s", "", stripped))

        # Normal paragraf
        else:
            p = doc.add_paragraph()
            _add_runs_with_bold(p, stripped)

    return doc


def _add_runs_with_bold(paragraph, text):
    """**bold** parcalarini algilayip DOCX run'lari ekler."""
    parts = re.split(r"(\*\*[^*]+\*\*)", text)
    for part in parts:
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            run = paragraph.add_run(part[2:-2])
            run.bold = True
        else:
            paragraph.add_run(part)


def generate_docx_bytes(markdown_text):
    """Markdown'dan DOCX bytes uretir."""
    doc = _markdown_to_docx(markdown_text)
    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def generate_pdf_bytes(docx_bytes):
    """DOCX bytes'tan PDF bytes uretir."""
    import dxpdf
    return dxpdf.convert(docx_bytes)


def save_files_to_disk(job_id, company, title):
    """CV ve cover letter'i DOCX + PDF olarak diske kaydeder.

    Donen: {'cv_docx': path, 'cv_pdf': path, 'cl_docx': path, 'cl_pdf': path}
    """
    from pathlib import Path
    from data.database import get_connection

    conn = get_connection()
    row = conn.execute(
        "SELECT cv_markdown, cover_letter_markdown FROM job_documents WHERE job_id = ?",
        (job_id,),
    ).fetchone()
    conn.close()

    if not row:
        return None

    cv_md, cover_md = row

    static_dir = Path("static/cv")
    static_dir.mkdir(parents=True, exist_ok=True)

    files = {}

    # CV DOCX + PDF
    if cv_md:
        cv_docx_bytes = generate_docx_bytes(cv_md)
        cv_docx_path = static_dir / f"{job_id}_cv.docx"
        cv_docx_path.write_bytes(cv_docx_bytes)
        files["cv_docx"] = str(cv_docx_path)

        cv_pdf_bytes = generate_pdf_bytes(cv_docx_bytes)
        cv_pdf_path = static_dir / f"{job_id}_cv.pdf"
        cv_pdf_path.write_bytes(cv_pdf_bytes)
        files["cv_pdf"] = str(cv_pdf_path)

    # Cover Letter DOCX + PDF
    if cover_md:
        cl_docx_bytes = generate_docx_bytes(cover_md)
        cl_docx_path = static_dir / f"{job_id}_cl.docx"
        cl_docx_path.write_bytes(cl_docx_bytes)
        files["cl_docx"] = str(cl_docx_path)

        cl_pdf_bytes = generate_pdf_bytes(cl_docx_bytes)
        cl_pdf_path = static_dir / f"{job_id}_cl.pdf"
        cl_pdf_path.write_bytes(cl_pdf_bytes)
        files["cl_pdf"] = str(cl_pdf_path)

    return files
