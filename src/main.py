"""Offline, evidence-constrained resume tailoring. No network or model calls."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / 'local-data/candidate_profile.json'
TEMPLATE = ROOT / 'templates/resume_template.tex'

# Explicit aliases only. Related products are deliberately not interchangeable.
ALIASES = {
    'java': ['java'], 'javascript': ['javascript'], 'go': ['go', 'golang'], 'python': ['python'],
    'spring boot': ['spring boot', 'springboot'], 'spring mvc': ['spring mvc'],
    'rest api': ['rest api', 'rest apis', 'restful', 'rest'],
    'hibernate': ['hibernate'], 'jpa': ['jpa'], 'sql': ['sql'],
    'postgresql': ['postgresql', 'postgres'], 'mysql': ['mysql'],
    'mongodb': ['mongodb'], 'redis': ['redis'], 'kafka': ['kafka'],
    'sqs': ['sqs'], 'aws': ['aws', 'amazon web services'],
    'eks': ['eks'], 'lambda': ['lambda'], 's3': ['s3'],
    'kubernetes': ['kubernetes', 'k8s'], 'docker': ['docker'],
    'ci/cd': ['ci/cd', 'continuous integration', 'continuous delivery'],
    'spinnaker': ['spinnaker'], 'jenkins': ['jenkins'],
    'payments': ['payments', 'payment processing', 'card payments'],
    'tokenization': ['tokenization', 'tokenisation'], 'emi': ['emi'],
    '3ds': ['3ds', '3-d secure', '3-ds', 'emv 3-d secure'],
    'iso 8583': ['iso 8583'], 'pci dss': ['pci dss'],
    'reconciliation': ['reconciliation'], 'security': ['security'],
    'observability': ['observability', 'monitoring', 'alerting'],
    'incident management': ['on-call', 'incident management', 'production incidents'],
    'disaster recovery': ['disaster recovery', 'dr failover'],
    'reliability': ['reliability', 'resilience', 'fault tolerance'],
    'performance': ['performance', 'latency', 'throughput'],
    'caching': ['caching', 'cache'], 'testing': ['testing', 'tests', 'test coverage'],
    'code review': ['code review', 'code reviews'], 'ownership': ['ownership', 'end-to-end'],
    'llm': ['llm', 'llms', 'generative ai', 'genai'],
    'react': ['react'], 'node.js': ['node.js'], 'junit': ['junit'],
    'mockito': ['mockito'], 'sonarqube': ['sonarqube'], 'jacoco': ['jacoco'],
    'grafana': ['grafana'], 'openshift': ['openshift'],
    'distributed systems': ['distributed systems'], 'microservices': ['microservices'],
    'system design': ['system design'], 'mentorship': ['mentoring', 'mentorship', 'mentor'],
    'rust': ['rust'], 'kotlin': ['kotlin'], 'gcp': ['gcp', 'google cloud'],
    'azure': ['azure'], 'rabbitmq': ['rabbitmq'], 'cassandra': ['cassandra'],
    'dynamodb': ['dynamodb'], 'typescript': ['typescript'],
}


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def terms(text):
    return {canonical for canonical, aliases in ALIASES.items()
            if any(re.search(r'(?<!\w)' + re.escape(alias) + r'(?!\w)', text, re.I)
                   for alias in aliases)}


def load_profile(path=None):
    profile_path = Path(path or PROFILE)
    p = json.loads(profile_path.read_text(encoding='utf-8'))
    if p.get('schema_version') != 1 or not isinstance(p.get('facts'), list):
        raise ValueError('Unsupported or incomplete candidate profile')
    if not p.get('facts') or not isinstance(p.get('candidate'), dict) or not isinstance(p.get('employers'), list):
        raise ValueError('Candidate, employers and nonempty facts are required')
    for field in ('name', 'headline', 'contact'):
        if not p['candidate'].get(field):
            raise ValueError('Missing candidate field: ' + field)
    for field in ('email', 'phone', 'location', 'availability'):
        if not isinstance(p['candidate']['contact'].get(field), str):
            raise ValueError('Missing contact field: ' + field)
    employer_ids = [e.get('id') for e in p['employers']]
    if None in employer_ids or len(set(employer_ids)) != len(employer_ids):
        raise ValueError('Employer IDs must be unique')
    for employer in p['employers']:
        if any(not isinstance(employer.get(k), str) for k in ('id', 'name', 'title', 'dates', 'context')):
            raise ValueError('Invalid employer record')
    seen = set()
    for f in p['facts']:
        for field in ('id', 'section', 'original_text', 'approved_text', 'tags', 'source', 'status'):
            if field not in f:
                raise ValueError(f'Missing fact field {field}')
        if f['id'] in seen:
            raise ValueError('Duplicate fact ID: ' + f['id'])
        seen.add(f['id'])
        if f['status'] not in ('source_backed', 'candidate_confirmed', 'unverified'):
            raise ValueError('Invalid fact status')
        if not f['source'] or not f['approved_text'].strip():
            raise ValueError('Every fact needs provenance and approved wording')
        if f['section'] not in ('summary', 'skills', 'experience', 'projects', 'education', 'achievements', 'certifications'):
            raise ValueError('Unsupported fact section')
        if f['section'] == 'experience' and f.get('employer_id') not in employer_ids:
            raise ValueError('Experience fact has an unknown employer')
    for source in p.get('sources', []):
        if not source.get('original_bytes_available'):
            continue
        original = profile_path.parent / source['filename']
        if not original.is_file() or hashlib.sha256(original.read_bytes()).hexdigest() != source.get('sha256'):
            raise ValueError('Master resume is missing or differs from the recorded source hash')
        extracted, _ = extract_pdf(original)
        normalize = lambda value: re.sub(r'[^a-z0-9]', '', value.lower())
        normalized_source = normalize(extracted)
        missing = [f['id'] for f in p['facts'] if f['status'] == 'source_backed'
                   and normalize(f['original_text']) not in normalized_source]
        if missing:
            raise ValueError('Master facts absent from source resume: ' + ', '.join(missing))
    return p


def analyze_jd(text):
    """Conservative lexical extraction; unresolved clauses remain visible."""
    requirements = []
    section = 'unspecified'
    for line in text.splitlines():
        line = line.strip(' \t-*•')
        if not line:
            continue
        if line.startswith('#'):
            continue
        low = line.lower()
        heading = len(line) < 65 and (line.endswith(':') or low in (
            'requirements', 'qualifications', 'preferred', 'nice to have', 'responsibilities'))
        if heading:
            section = ('preferred' if re.search(r'prefer|nice|bonus', low) else
                       'responsibility' if 'responsibilit' in low else 'mandatory')
            continue
        priority = ('preferred' if re.search(r'preferred|nice.to.have|bonus|optional', low)
                    else 'mandatory' if re.search(r'\bmust\b|\brequired\b|\bmandatory\b', low)
                    else section)
        keys = sorted(terms(line))
        year_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:\+|[-–]\s*\d+)?\s*years?', low)
        if year_match:
            keys.append('experience_years')
        if not keys:
            keys = ['unresolved_clause']
        for key in keys:
            requirements.append({
                'id': f'R{len(requirements)+1:03}', 'canonical': key,
                'original_text': line, 'status': priority,
                'weight': 2 if priority == 'mandatory' else 1,
                'minimum_years': float(year_match[1]) if year_match and key == 'experience_years' else None,
                'extraction': 'explicit_alias' if key in ALIASES else 'rule',
            })
    if not requirements:
        raise ValueError('JD is empty or has no readable requirements')
    # Retain all source lines. Do not silently collapse repeated mandatory clauses.
    return {'method': 'conservative lexical rules; human JD review required',
            'source_text': text, 'requirements': requirements,
            'limitations': ['No semantic model is enabled.',
                           'Unknown and compound eligibility clauses require human review.',
                           'A match is relevant evidence, not proof that every qualifier is met.']}


def match_requirements(profile, analysis):
    result = []
    for r in analysis['requirements']:
        key = r['canonical']
        row = dict(r, evidence_ids=[], classification='MISSING', credit=0.0, reason='No source-backed evidence')
        if key == 'unresolved_clause':
            row.update(classification='UNVERIFIED', reason='Clause is outside the lexical extractor; review the original JD')
        elif key == 'experience_years':
            # Duration for a named skill cannot be inferred from total experience.
            scoped = bool(terms(r['original_text']))
            years = profile['candidate'].get('experience_years')
            if scoped or years is None:
                row.update(classification='UNVERIFIED', reason='Skill-specific tenure or ambiguous experience scope is not documented')
            elif years >= r['minimum_years']:
                row.update(classification='DIRECT', credit=1.0, evidence_ids=['candidate.experience_years'], reason='Explicit total experience statement')
            else:
                row.update(hard_blocker=r['status'] == 'mandatory', reason='Documented total experience is below minimum')
        else:
            direct, project, listed = [], [], []
            for employer in profile['employers']:
                if key in terms(employer.get('context', '')):
                    direct.append('employer:' + employer['id'] + '.context')
            for f in profile['facts']:
                if f['status'] == 'unverified':
                    continue
                if key not in set(f['tags']) | terms(f['approved_text']):
                    continue
                if f['section'] == 'experience':
                    direct.append(f['id'])
                elif f['section'] == 'projects':
                    project.append(f['id'])
                else:
                    listed.append(f['id'])
            if direct:
                row.update(classification='DIRECT', credit=1.0, evidence_ids=direct,
                           reason='Explicit relevant professional resume statement; JD qualifiers still need review')
            elif project:
                row.update(classification='TRANSFERABLE', credit=0.5, evidence_ids=project,
                           reason='Project evidence; does not establish professional production depth')
            elif listed:
                row.update(classification='UNVERIFIED', evidence_ids=listed,
                           reason='Listed in skills, summary or credentials; professional depth is not established')
            if re.search(r'\b(expert|expertise|deep|advanced|architect|at scale|\d+\s*\+?\s*years?)\b', r['original_text'], re.I):
                if row['classification'] in ('DIRECT', 'TRANSFERABLE'):
                    row.update(classification='UNVERIFIED', credit=0.0,
                               reason='Relevant evidence exists, but the required depth, scale or duration needs verification')
        result.append(row)
    return result


def score_mapping(mapping):
    denominator = sum(r['weight'] for r in mapping)
    score = round(100 * sum(r['weight'] * r['credit'] for r in mapping) / denominator, 1)
    blockers = [r['id'] for r in mapping if r.get('hard_blocker')]
    missing = [r['id'] for r in mapping if r['status'] == 'mandatory' and r['classification'] == 'MISSING']
    unknown = [r['id'] for r in mapping if r['classification'] == 'UNVERIFIED']
    recommendation = ('Critical Gaps' if blockers or missing else 'Stretch Match' if score < 60
                      else 'Competitive Match' if unknown or score < 85 else 'Strong Match')
    return {'scoring_version': 'lexical-evidence-v1', 'candidate_jd_fit': score,
            'formula': '100 * sum(requirement weight * evidence credit) / sum(requirement weight)',
            'weights': {'mandatory': 2, 'other': 1},
            'credits': {'DIRECT': 1, 'TRANSFERABLE': 0.5, 'UNVERIFIED': 0, 'MISSING': 0},
            'confidence': 'Low: lexical extraction and resume-backed evidence only',
            'resume_presentation': None, 'ats_compatibility': None,
            'presentation_reason': 'Not scored without validated PDF and reviewed rubric; ordering alone earns no numeric improvement',
            'hard_blockers': blockers, 'missing_mandatory': missing,
            'unverified_requirements': unknown, 'application_assessment': recommendation,
            'disclaimer': 'Internal evidence coverage metric; not an ATS score or hiring probability'}


def tailor(profile, mapping):
    weights = {}
    for r in mapping:
        for fid in r['evidence_ids']:
            weights[fid] = weights.get(fid, 0) + r['weight'] * r['credit']
    sections = {}
    for f in profile['facts']:
        sections.setdefault(f['section'], []).append(f['id'])
    by_id = {f['id']: f for f in profile['facts']}
    # Preserve all content and employer grouping; reorder bullets within each employer.
    sections['experience'] = [fid for employer in profile['employers']
        for fid in sorted([f['id'] for f in profile['facts'] if f.get('employer_id') == employer['id']],
                          key=lambda x: -weights.get(x, 0))]
    for sec in ('projects', 'skills'):
        def relevance(fid):
            fact = by_id[fid]
            keys = set(fact['tags']) | terms(fact['approved_text'])
            lexical = sum(r['weight'] for r in mapping if r['canonical'] in keys)
            return weights.get(fid, 0) + lexical
        sections[sec] = sorted(sections.get(sec, []), key=lambda x: -relevance(x))
    return {'schema_version': 1, 'master_hash': fingerprint(profile),
            'sections': sections, 'claims': [{'fact_id': fid, 'text': by_id[fid]['approved_text']}
                for ids in sections.values() for fid in ids],
            'method': 'evidence-weighted ordering; no generated factual language'}


def validate_content(profile, content):
    from src.skill_actions import plan
    plan(profile, content.get('selected_skills', []))
    if content.get('master_hash') != fingerprint(profile):
        raise ValueError('Master hash mismatch: regenerate from the current master')
    by_id = {f['id']: f for f in profile['facts']}
    claims = content.get('claims', [])
    ids = [c['fact_id'] for c in claims]
    if len(ids) != len(set(ids)) or set(ids) != set(by_id):
        raise ValueError('Claims must preserve every master fact exactly once')
    section_ids = [fid for ids in content['sections'].values() for fid in ids]
    if sorted(section_ids) != sorted(by_id):
        raise ValueError('Missing, duplicated or fabricated section facts')
    for section, ids in content['sections'].items():
        if any(by_id[fid]['section'] != section for fid in ids):
            raise ValueError('Fact moved to a false section')
    for c in claims:
        f = by_id[c['fact_id']]
        if c['text'] != f['approved_text'] or f['status'] == 'unverified':
            raise ValueError('Unapproved wording or unverified fact: ' + f['id'])
    return {'status': 'passed', 'checked_claims': len(claims),
            'meaning': 'Original claims match approved master wording; selected skill labels derive from literal evidence. No independent employment verification.'}


def tex_escape(value):
    escapes = {'\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$',
               '#': r'\#', '_': r'\_', '{': r'\{', '}': r'\}',
               '~': r'\textasciitilde{}', '^': r'\textasciicircum{}',
               '\u2013': '--', '\u2014': '---', '\u200b': ''}
    return ''.join(escapes.get(c, c) for c in str(value))


def tex_fact(f, highlights=None, additions=None):
    text = tex_escape(f['approved_text'])
    emphasis = json.loads((ROOT / 'templates/emphasis.json').read_text(encoding='utf-8'))
    for phrase in sorted(emphasis.get(f['id'], []), key=len, reverse=True):
        token = tex_escape(phrase)
        text = text.replace(token, r'\textbf{' + token + '}')
    if f['section'] == 'skills':
        label, rest = text.split(':', 1)
        text = r'{\bfseries\color{navy} ' + label + ':}' + rest
        for phrase in sorted(highlights or [], key=len, reverse=True):
            token = tex_escape(phrase)
            text = re.sub(r'(?<!\w)' + re.escape(token) + r'(?!\w)', lambda _: r'\textbf{' + token + '}', text)
        if additions:
            from src.skill_actions import suffix
            text += tex_escape(suffix(additions))
    if f['section'] == 'certifications' and f.get('url'):
        label = tex_escape(f['link_label'])
        text = text.replace('(' + label + ',', '(' + tex_link(f['url'], label) + ',')
    return text


def tex_link(url, label):
    if not re.fullmatch(r'https://[A-Za-z0-9._~:/?#\[\]@!$&\x27()*+,;=%-]+', url):
        raise ValueError('Invalid HTTPS link')
    return r'\href{' + tex_escape(url) + r'}{\color{blue}\underline{' + label + '}}'


def render(profile, content):
    validate_content(profile, content)
    e = tex_escape
    c = profile['candidate']
    by_id = {f['id']: f for f in profile['facts']}
    section_ids = content['sections']
    from src.skill_actions import plan
    highlights, additions = plan(profile, content.get('selected_skills', []))
    info = c['contact']
    contact_parts = [e(info['email']), e(info['phone'])]
    for label, url in c.get('links', {}).items():
        if url:
            if not re.fullmatch(r'https://[A-Za-z0-9._~:/?#\[\]@!$&\x27()*+,;=%-]+', url):
                raise ValueError('Invalid profile link: ' + label)
            contact_parts.append(r'\href{' + e(url) + r'}{\color{blue}\underline{' + e(label) + '}}')
        else:
            contact_parts.append(e(label))
    contact_parts.extend([e(info['location']), e(info['availability'])])
    contact_tex = ' | '.join(contact_parts)
    lines = [r'\noindent\begin{minipage}{\linewidth}\centering', r'{\fontsize{17.5}{20}\selectfont\bfseries\color{navy} ' + e(c['name']) + r'}\\[2pt]',
             r'{\fontsize{8.3}{10}\selectfont\color{muted} ' + e(c['headline']) + r'}\\[3pt]',
             r'{\fontsize{8.5}{10}\selectfont\color{muted} ' + contact_tex + '}', r'\end{minipage}\par\vspace{4pt}']
    for section in ('summary', 'skills', 'experience', 'projects', 'education', 'achievements', 'certifications'):
        lines.append(r'\section*{' + e(section.upper()) + '}')
        ids = section_ids.get(section, [])
        if section == 'experience':
            for employer in profile['employers']:
                lines += [r'\textbf{' + e(employer['name']) + '}, ' + e(employer['title']) + r'\hfill ' + e(employer['dates']) + r'\par',
                          r'{\fontsize{8.5}{10}\selectfont\itshape\color{muted} ' + e(employer['context']) + '}', r'\begin{itemize}']
                lines += [r'\item ' + tex_fact(by_id[fid]) for fid in ids if by_id[fid].get('employer_id') == employer['id']]
                lines += [r'\end{itemize}']
        elif section == 'projects':
            for fid in ids:
                name, rest = by_id[fid]['title'].split(' ', 1)
                heading = tex_link(by_id[fid]['url'], e(name)) if by_id[fid].get('url') else r'\underline{' + e(name) + '}'
                lines += [r'\textbf{' + heading + r'} {\fontsize{8.5}{10}\selectfont\itshape\color{muted} ' + e(rest) + '}', r'\begin{itemize}',
                          r'\item ' + tex_fact(by_id[fid]), r'\end{itemize}']
        elif section in ('achievements', 'certifications'):
            lines += [r'\begin{itemize}'] + [r'\item ' + tex_fact(by_id[fid]) for fid in ids] + [r'\end{itemize}']
        else:
            for fid in ids:
                f = by_id[fid]
                lines.append(tex_fact(f, highlights.get(fid), additions.get(fid)) + (r'\hfill ' + e(f['date']) if 'date' in f else '') + r'\par')
    template = TEMPLATE.read_text(encoding='utf-8')
    if template.count('@@BODY@@') != 1:
        raise ValueError('Trusted template must have exactly one content placeholder')
    return template.replace('@@BODY@@', '\n'.join(lines))


def extract_pdf(path):
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    return '\n'.join(page.extract_text() or '' for page in reader.pages), reader


def validate_pdf(path, profile, content=None):
    text, reader = extract_pdf(path)
    normalize = lambda v: re.sub(r'[^a-z0-9]', '', v.lower())
    extracted = normalize(text)
    missing = [f['id'] for f in profile['facts'] if normalize(f['approved_text']) not in extracted]
    headings = ['SUMMARY', 'SKILLS', 'EXPERIENCE', 'PROJECTS', 'EDUCATION', 'ACHIEVEMENTS', 'CERTIFICATIONS']
    positions = [text.find(h) for h in headings]
    heading_order = all(x >= 0 for x in positions) and positions == sorted(positions)
    checks = {'one_page': len(reader.pages) == 1, 'text_extractable': len(text.strip()) > 100,
              'all_master_claims_extracted': not missing, 'section_reading_order': heading_order,
              'contact_extracted': profile['candidate']['contact']['email'] in text}
    expected_links = [u for u in profile['candidate'].get('links', {}).values() if u]
    actual_links = [str(a.get_object().get('/A', {}).get('/URI', ''))
                    for page in reader.pages for a in (page.get('/Annots') or [])]
    # The master PDF can contain an equivalent pre-correction www spelling.
    canonical_url = lambda url: re.sub(r'^https://www\.', 'https://', url).rstrip('/')
    checks['contact_links'] = all(canonical_url(url) in {canonical_url(link) for link in actual_links}
                                  for url in expected_links)
    checks['project_and_certificate_links'] = all(
        canonical_url(f['url']) in {canonical_url(link) for link in actual_links}
        for f in profile['facts'] if f.get('url'))
    if content is not None:
        from src.skill_actions import plan, suffix
        _, additions = plan(profile, content.get('selected_skills', []))
        facts_by_id = {f['id']: f for f in profile['facts']}
        checks['skill_additions_extracted'] = all(
            normalize(facts_by_id[fid]['approved_text'] + suffix(items)) in extracted
            for fid, items in additions.items())
    return {'status': 'passed' if all(checks.values()) else 'failed', 'checks': checks,
            'missing_fact_ids': missing, 'page_count': len(reader.pages),
            'visual_inspection': 'unexecuted', 'font_and_overlap_inspection': 'unexecuted',
            'hyperlink_validation': 'PDF link annotations checked against the master profile'}


def compile_pdf(tex, profile):
    exe = shutil.which('xelatex')
    if not exe:
        return {'status': 'unexecuted', 'reason': 'xelatex is not installed or not on PATH; template uses Calibri via fontspec'}
    command = [exe, '-no-shell-escape', '-interaction=nonstopmode', '-halt-on-error', tex.name]
    try:
        for _ in range(2):
            run = subprocess.run(command, cwd=tex.parent, capture_output=True, text=True, timeout=60)
            (tex.parent / 'compile.log').write_text(run.stdout + run.stderr, encoding='utf-8')
            if run.returncode:
                return {'status': 'failed', 'reason': 'LaTeX compilation failed; see compile.log'}
        if 'Overfull \\hbox' in run.stdout or 'Overfull \\vbox' in run.stdout:
            return {'status': 'failed', 'reason': 'LaTeX reports content overflow; revise content, do not shrink fonts silently'}
        pdf = tex.with_suffix('.pdf')
        if not pdf.is_file():
            return {'status': 'failed', 'reason': 'Compiler returned success without PDF'}
        return {'status': 'passed', 'pdf': pdf.name, 'pdf_validation': validate_pdf(pdf, profile)}
    except (subprocess.TimeoutExpired, OSError, ValueError) as exc:
        return {'status': 'failed', 'reason': str(exc)}


def safe_name(value):
    # Labels never become commands, arbitrary paths, or TeX instructions.
    slug = re.sub(r'[^A-Za-z0-9_-]+', '_', value).strip('_')[:70]
    return slug if slug and slug.upper() not in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(10)), *(f'LPT{i}' for i in range(10))} else 'application'


def reports(output, profile, analysis, mapping, score, content, validation, company, role):
    dump(output / 'jd_analysis.json', analysis)
    dump(output / 'requirements_mapping.json', mapping)
    dump(output / 'match_score.json', {'original': score, 'tailored': copy.deepcopy(score),
        'explanation': 'Candidate fit is unchanged. Reordering is not assigned a fabricated presentation improvement.'})
    dump(output / 'tailored_content.json', content)
    dump(output / 'validation_report.json', validation)
    dump(output / 'run_manifest.json', {'created_utc': datetime.now(timezone.utc).isoformat(),
        'company': company, 'role': role, 'profile_version': profile['profile_version'],
        'profile_hash': fingerprint(profile), 'template_sha256': hashlib.sha256(TEMPLATE.read_bytes()).hexdigest(),
        'jd_sha256': hashlib.sha256(analysis['source_text'].encode()).hexdigest(),
        'content_hash': fingerprint(content), 'submission_status': 'not_submitted'})
    rows = ['| Requirement | Class | Evidence | Reason |', '|---|---|---|---|']
    rows += ['| ' + ' | '.join(str(x).replace('|', '/') for x in (
        r['id'] + ': ' + r['canonical'], r['classification'], ', '.join(r['evidence_ids']) or '-', r['reason'])) + ' |' for r in mapping]
    report = (f'# {company} — {role}\n\nCandidate–JD evidence coverage: {score["candidate_jd_fit"]}/100. '
              f'Assessment: {score["application_assessment"]} (provisional).\n\n'
              'Presentation and ATS scores: unscored. This is a conservative lexical baseline, not semantic AI analysis.\n\n'
              + '\n'.join(rows) + '\n\n'
              'Formula: ' + score['formula'] + '. Mandatory weight 2; other weight 1. '
              'Direct credit 1; project/transferable 0.5; missing/unverified 0. '
              'Unknown evidence lowers coverage but does not prove ineligibility.\n\n'
              'Human review required: resolve unknown JD clauses, skill depth, source conflicts, contact links, '
              'and final visual layout. No application is submitted.\n')
    (output / 'score_report.md').write_text(report, encoding='utf-8')
    original = {}
    for f in profile['facts']:
        original.setdefault(f['section'], []).append(f['id'])
    changes = ['# Resume changes', '', 'No factual wording, dates, metrics, roles or employers changed.', '',
               'All master facts retained. Evidence-backed bullets and skill groups reordered by requirement relevance.', '']
    changes += [f'- {s}: {", ".join(original[s])} → {", ".join(ids)}' for s, ids in content['sections'].items() if original[s] != ids]
    changes += ['', 'Pending verification:', *['- ' + x['detail'] for x in profile['unresolved']]]
    (output / 'resume_changes.md').write_text('\n'.join(changes) + '\n', encoding='utf-8')
    selected = [f for f in profile['facts'] if f['section'] == 'experience' and any(f['id'] in r['evidence_ids'] for r in mapping)][:5]
    prep = ['# Interview preparation', '', 'Interview Tips: explain your contribution, implementation, failure cases and measured outcome. '
            'Interviewers may test depth behind keywords. Avoid claiming team work as personal ownership or staging as live deployment.', '']
    for f in selected:
        prep += [f'## {f["id"]}', '', f['approved_text'], '',
                 '- What was your individual contribution? What alternatives did you consider?',
                 '- How did you test correctness and failure paths? How was impact measured?',
                 '- Verify implementation details against your records; this report does not invent them.', '']
    (output / 'interview_preparation.md').write_text('\n'.join(prep), encoding='utf-8')


def run_tailor(args):
    profile = load_profile(args.profile)
    analysis = analyze_jd(Path(args.jd).read_text(encoding='utf-8'))
    mapping = match_requirements(profile, analysis)
    score = score_mapping(mapping)
    content = tailor(profile, mapping)
    content_check = validate_content(profile, content)
    if args.proposal:
        content = json.loads(Path(args.proposal).read_text(encoding='utf-8'))
        content_check = validate_content(profile, content)
    base = Path(args.output).resolve()
    label = safe_name(args.company) + '_' + safe_name(args.role)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = base / (label + '_' + stamp)
    # A new run cannot mutate master data even if --output points inside master.
    if (ROOT / 'master').resolve() == base or (ROOT / 'master').resolve() in base.parents:
        raise ValueError('Output must not be inside the immutable master directory')
    out.mkdir(parents=True, exist_ok=False)
    tex = out / ('Resume_' + label + '.tex')
    tex.write_text(render(profile, content), encoding='utf-8')
    compilation = compile_pdf(tex, profile)
    validation = {'content': content_check, 'compilation': compilation,
                  'visual_fidelity': 'unexecuted: compiled PDF requires visual comparison with master/original_resume.pdf',
                  'human_review': 'required', 'application_ready': False,
                  'status': 'failed' if compilation['status'] == 'failed' else 'partially_validated',
                  'unresolved_master_items': profile['unresolved']}
    reports(out, profile, analysis, mapping, score, content, validation, args.company, args.role)
    print(json.dumps({'output': str(out), 'candidate_jd_fit': score['candidate_jd_fit'],
                      'application_assessment': score['application_assessment'], 'validation': validation['status'],
                      'compilation': compilation['status'], 'application_ready': False}, indent=2))
    return 2 if compilation['status'] != 'passed' else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init', help='Extract a PDF into a new review draft; never overwrites a master')
    init.add_argument('--resume', required=True)
    init.add_argument('--output', default=str(ROOT / 'input/imports'))
    for name in ('tailor', 'score', 'compare'):
        p = sub.add_parser(name)
        p.add_argument('--jd', required=True)
        p.add_argument('--profile', default=str(PROFILE))
        if name == 'tailor':
            p.add_argument('--company', required=True)
            p.add_argument('--role', required=True)
            p.add_argument('--output', default=str(ROOT / 'output'))
            p.add_argument('--proposal', help='Optional structured content proposal; only approved master wording is allowed')
        elif name == 'score':
            p.add_argument('--resume', required=True)
        else:
            p.add_argument('--original', required=True)
            p.add_argument('--tailored', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'tailor':
            return run_tailor(args)
        if args.command == 'init':
            text, reader = extract_pdf(args.resume)
            target = Path(args.output).resolve() / ('import_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
            target.mkdir(parents=True, exist_ok=False)
            shutil.copy2(args.resume, target / 'original_resume.pdf')
            (target / 'extracted_text.txt').write_text(text, encoding='utf-8')
            dump(target / 'import_review.json', {'source_sha256': hashlib.sha256(Path(args.resume).read_bytes()).hexdigest(),
                 'page_count': len(reader.pages), 'status': 'review_required',
                 'structured_profile': None, 'reason': 'Arbitrary resume-to-profile extraction is not implemented; use the documented profile schema and explicit review'})
            print(str(target))
            return 0
        p = load_profile(args.profile)
        analysis = analyze_jd(Path(args.jd).read_text(encoding='utf-8'))
        result = score_mapping(match_requirements(p, analysis))
        paths = [args.resume] if args.command == 'score' else [args.original, args.tailored]
        result['documents'] = {str(path): validate_pdf(path, p) for path in paths}
        print(json.dumps(result, indent=2))
        return 0 if all(v['status'] == 'passed' for v in result['documents'].values()) else 2
    except (ValueError, KeyError, OSError, ImportError) as exc:
        print('Error: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
