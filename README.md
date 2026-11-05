# Resume workspace

Local resume tailoring with reviewed uploads, a fixed LaTeX template, evidence mapping, and PDF previews. No personal resume is bundled. This is a deterministic lexical prototype, not a semantic AI rewriting service.

## Run on Windows

Use Python 3.10 or later. Open PowerShell in the project directory:

```powershell
$ResumePython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (-not (Test-Path -LiteralPath $ResumePython)) { $ResumePython = 'python' }
& $ResumePython --version
& $ResumePython -m pip install -r requirements-ui.txt
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-ui.ps1 -Python $ResumePython
```

If Python opens the Microsoft Store, install Python and reopen PowerShell. Keep the terminal open and visit http://127.0.0.1:8765/ in Chrome. Stop the server with Ctrl+C. Stop an older server before starting another on port 8765.

## Upload and review

1. Choose a UTF-8 TXT or selectable-text PDF, up to 5 MB. PDFs must be unencrypted, with 1 to 10 pages. Scanned PDFs need OCR outside this app.
2. Open **Recommended format and example**. Download the TXT example or load it into the editor. Replace every example detail with your own information.
3. Review the text and arrange it using the labeled fields and section headings below. PDF extraction preserves layout and prepares detected contact fields, headings, employer date rows, project titles, and wrapped bullets for review. Correct any ambiguous or missing fields before saving.
4. Select **Save reviewed resume**. The app validates the structure before replacing the local profile. Invalid input leaves the previous profile intact.
   To reproduce emphasis from your source resume, wrap each phrase in `**double asterisks**` in the review editor. The markers are formatting only; the claim stored and checked in the PDF remains the same plain text. PDF uploads do not automatically detect font-weight changes, so review bold phrases before saving.
5. Enter the company, role, and JD, then select **Tailor my resume**. Review the PDF, changes, and evidence gaps.
6. Use **Add & highlight supported skills** to surface literal skills already backed by the upload. Adjust selections in **Evidence & gaps**. Review the final PDF before applying.

Recommended layout: one column, plain headings, selectable text, and one complete claim per line. Avoid tables, icons, photos, headers, and footers. Use the downloadable example at `ui/resume-format.txt`:

```text
Name: Alex Example
Headline: Software Engineer
Email: alex@example.com
Phone:
Location: Your city
Availability:

[Summary]
Software engineer building web applications.

[Skills]
Languages: JavaScript, Python
Frameworks: React, Node.js

[Experience]
Example Company | Software Engineer | 2023 - Present
- Built REST APIs using Node.js.

[Projects]
Built a task manager using React and TypeScript.

[Education]
Example University, Bachelor of Science, 2023
```

Name, headline, email, and a nonempty Skills section are required. Other sections are optional. Supported section names are Summary, Skills, Experience, Projects, Education, Achievements, and Certifications. Each experience header uses `Company | Role | Dates`; every following experience bullet begins with `-`. Skills rows use `Category: skill, skill`. Contact fields appear above sections. No dates, credentials, tenure, or qualifications are inferred. PDF HTTPS annotations are recovered with their visible labels. Contact links, project links, and certification links appear in the review editor and remain clickable in the exported PDF. Review the detected location, availability, and URL destinations before saving. In TXT, add `Link: label | https://destination` above sections, `URL: https://destination` after a project `Title:`, or `Link: provider | https://destination` after its certification text. The provider label must occur in that certification. Only HTTPS destinations are supported; missing URLs are never invented.

## Local data and privacy

The saved profile is `local-data/candidate_profile.json`. It persists across restarts and is excluded from Git. New uploads replace this single local profile. This is a single-user local tool, not a hosted multi-user service. Generated runs are separate directories under `output/ui`, also excluded from Git. An old run remains there after replacing the profile. Delete local-data and output yourself when you want to remove saved personal data.

The UI shows the saved bold-phrase count. Saving an older unmarked draft or reuploading the same candidate's PDF retains previously reviewed bold phrases on unchanged claims. The editor then refreshes from the saved profile so the markers are visible; removing markers from that current draft clears their emphasis when saved. Existing downloaded PDFs are snapshots and do not update when the profile changes; generate again and open the newest PDF from the workspace.

The server binds to loopback, checks Host and a per-launch request token, limits request sizes, and exposes an allowlist of generated files. No external AI requests, analytics, applications, email, or credentials are sent. Do not expose the server publicly.

Removing files from the current source tree does not remove earlier Git history. Keep any repository containing historic personal resumes private until that history has been replaced or a new clean repository is created.

## Output and scoring

Downloads use `Resume_Company_Role.pdf` and `.tex`. All approved claims remain in their sections; relevance changes ordering. Highlighting and additions change skill presentation. Candidate evidence coverage does not increase merely because a skill is highlighted. The separate JD skills visibility count measures how many supported labels appear in Skills before and after the action. Neither measure is a hiring probability or a validated ATS score.

The template uses Calibri and US Letter paper. Install XeLaTeX with fontspec, geometry, enumitem, hyperref, titlesec, and xcolor for LaTeX PDF export. When compilation is unavailable, the UI labels the ReportLab output as a layout preview. That fallback currently needs licensed Calibri fonts in Windows Fonts. Long resumes can exceed one page; failed PDF checks require review, and the app never grants application approval.

## Development

```powershell
& $ResumePython -m unittest discover -v
node --check ui/app.js
```

The CLI uses the locally saved profile after UI import. Example:

```powershell
& $ResumePython -m src.main tailor --jd input/java_backend.synthetic.txt --company Example --role 'Backend Engineer'
```

CLI tailoring requires XeLaTeX to export its PDF. The UI provides the disclosed ReportLab fallback. Tests use synthetic data only. The PDF preparation regression covers wrapped claims, multiple employers, and project grouping. No full visual similarity, cross-browser, or ATS certification is claimed.
