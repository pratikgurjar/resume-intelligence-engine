# Upload workflow review

## Requirement and Acceptance Criteria
Remove the personal bundled resume; add PDF/TXT upload, recommended format, text review, local persistence, and tailoring from reviewed evidence.

## Scope and Non-Goals
Single-user local UI. No OCR, automatic arbitrary-layout interpretation, semantic rewriting, or hosted upload service.

## Existing Code and Reuse Findings
Reuse evidence matching, selected skill validation, rendering, and reports. Education rendering now accepts arbitrary degree text. Local profile loading resolves the current storage path at runtime.

## Baseline and Pre-existing Issues
The earlier personal-resume suite passed 30 tests. Those fixtures exposed personal data and were replaced by synthetic import/integration fixtures and retained generic engine invariants. Local XeLaTeX remains unavailable; Windows Calibri is required by the fallback.

## Blast Radius
Medium: profile initialization, upload API, generic education renderer, local storage, and UI onboarding. The personal master, emphasis, personal review documents, and personal fixture scripts are removed from distribution.

## Solution and Alternatives
Use explicit reviewed text fields and section headings. PDF extraction feeds the review editor; it does not silently guess employers, tenure, or credentials. An automatic PDF layout parser was deferred because ambiguous grouping can create false claims.

## Implementation Summary
The upload API checks type, size, PDF encryption/page count, extracted-text bounds, and resume structure. A validated profile is atomically saved under ignored local-data. Source claims retain line provenance. The UI loads profile metadata, blocks initial generation until import, offers a downloadable synthetic TXT template, and clears old displayed results after replacement.

## Edge Cases and Failure Modes
Invalid imports preserve the previous profile. Malformed/scanned/encrypted PDFs receive errors. TeX content is escaped. Missing profiles block generation. Generic degrees no longer require MCA text. Empty optional sections are allowed. Long resumes can fail the one-page PDF check and still require human review.

## Security and Privacy
Uploads and generated runs are excluded from Git. Personal source and metadata were removed; old local files were backed up outside the repository. Use clean repository history for distribution; retain the old repository privately. The app remains loopback-only with Host/token checks. It is not a multi-user service.

## Reliability, Performance, and Observability
Serialized generation is reused. Atomic profile replacement avoids partial JSON. Reports retain claim provenance and validation. PDF work is bounded by upload size and page count; no performance benchmark was run.

## Compatibility, Migration, Deployment, and Rollback
Fresh installations need one reviewed upload. Existing local runs remain local. Personal profile files are not auto-imported. Restore from the private local backup if required. Restart the Python server after updating source.

## Testing and Verification
18 synthetic unittest tests passed; node --check ui/app.js passed. Coverage includes parser validation, employer grouping, malformed PDF extraction, empty install, failed-import preservation, PDF generation/extraction, skill visibility and unchanged fit, filename headers, source integrity, TeX injection, and token/file boundaries. Chrome verified example import and PDF generation. No local XeLaTeX compile, fresh-machine install, mobile, or cross-browser test was run. PDF upload was tested through HTTP; Chrome used the example editor workflow.

## Quality Score
Scores apply to this bounded local feature.

| Category | Score | Evidence | Deficiency / remaining risk | Improvement |
|---|---:|---|---|---|
| Requirement and scope | 19/20 | Upload and format guidance implemented | PDF requires manual structuring | Reviewed layout parser |
| Understanding and reuse | 10/10 | Existing engine reused | None in scope | None |
| Integration and blast radius | 9/10 | Synthetic HTTP generation | CLI needs imported profile | Fresh-install CLI check |
| Edge cases and failures | 13/15 | Invalid imports preserve state | No OCR or full PDF resource isolation | Add worker isolation if hosted |
| Verification | 13/15 | 18 tests and Chrome flow | No mobile or local TeX QA | Run those environments |
| Maintainability | 9/10 | Small explicit parser | Fixed section vocabulary | Add aliases only with tests |
| Security/privacy/integrity | 8/8 | Ignored uploads and clean source | Local backups still contain personal files | Keep backups private |
| Reliability/performance/observability | 6/7 | Atomic persistence and serialized rendering | No benchmark | Measure if latency grows |
| Compatibility/rollback | 4/5 | Private backup available | Existing master setup changes | Review migration on other machines |
| Total | 91/100 | Local feature ready for review | Limits above remain | See above |

## Commit Readiness
Checks pass for the local workflow. Public distribution must use the clean repository, never the private backup history.

## Remaining Risks
Uploaded claims are user statements, not independent verification. Links in free text remain plain text. Resume formatting needs human review. Replacing a profile does not delete older local output runs.

## Optional Follow-up Improvements
Add reviewed employer/date extraction, optional contact-link fields, OCR integration, and configurable fonts as separate changes.

## PDF import correction
The original PDF extractor flattened contact fields and section boundaries, while saving required explicit labeled fields. Layout-preserving extraction now feeds an editable preparation step. Employer date rows, context, project headings, and wrapped bullets are preserved; ambiguous text still needs review. Import errors appear at both the upload and tailoring controls. 20 synthetic tests and JS syntax passed. A local personal PDF was used only for local verification: 27 claims retained, one page, extraction checks passed. It was not added to Git. The browser automation extension blocked automated file selection because file-URL access was disabled; the real PDF import was therefore exercised via local HTTP plus browser generation.

## Contact details and hyperlink correction
PDF extraction now recovers HTTPS annotations with visible anchor labels using PDF text bounds. Preparation retains literal location and availability text and exposes detected contact/project/certification URLs in the review editor. TXT supports explicit Link and URL fields. Both renderers skip empty header segments and preserve clickable destinations. PDF validation additionally checks header details and employer metadata. Synthetic integration verifies all seven source URLs through PDF extraction, preparation, save, TeX, and PDF export; invalid URLs and conflicting destinations are rejected. Local verification of the user PDF retained 27 claims, all seven source URL destinations, location, and availability on one page. Personal verification artifacts remain ignored. Automatic mapping still depends on identifiable visible labels and section headings; ambiguous links need review.

## Reviewed emphasis correction
Imported profiles previously lost source bold spans because the public template emphasis map is intentionally empty. Reviewed text now uses `**phrase**` around literal spans; parsing stores the phrase separately from claim text, and both LaTeX and ReportLab apply the same disjoint span positions. Serializing the profile restores the markers for subsequent edits. The original private emphasis map matched 16 current local claims exactly, restoring 26 bold phrases without changing the 27 claim texts. The local profile and backup remain Git-ignored. Synthetic round-trip and renderer tests plus one-page PDF validation passed; selected spans were inspected in the preview and PDF font metadata. PDF font weight is not inferred automatically on new uploads, so users must mark desired phrases during review. No local XeLaTeX compiler was available for this check.

## Emphasis persistence correction
The follow-up screenshot was a previously downloaded PDF, and the newest run was also plain because saving an older unmarked editor draft had overwritten the local profile. The saved profile had zero bold phrases at reproduction time. Saving a draft for the same name and email now retains previous emphasis only for uniquely matching section and exact claim text. A different candidate does not inherit it. The editor refreshes to the canonical saved text after saving, and the sidebar shows the saved bold-phrase count. Removing markers from that canonical draft explicitly clears emphasis. The local profile was restored from the private phrase map. Chrome generated a new Diagrid run with 26 bold phrases; the PDF is one page, its content and link checks pass, and inspected phrase glyphs use Calibri-Bold. The local data and output directories remain excluded from Git. Old downloaded PDFs remain historical snapshots.
