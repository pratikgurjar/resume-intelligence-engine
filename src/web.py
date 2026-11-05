"""Loopback-only UI for the evidence constrained resume engine."""
from __future__ import annotations

import argparse
import json
import mimetypes
import secrets
import base64
import io
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from pathlib import Path
from urllib.parse import urlsplit

from src.main import (ROOT, load_profile, analyze_jd, match_requirements, score_mapping,
                      tailor, validate_content, validate_pdf, render, compile_pdf, reports, safe_name)

UI = ROOT / 'ui'
MAX_BODY = 8_000_000
FILES = {'resume.pdf', 'resume.tex', 'score_report.md', 'resume_changes.md',
         'validation_report.json', 'requirements_mapping.json', 'interview_preparation.md', 'preview.png'}


def download_name(company, role, extension):
    return f'Resume_{safe_name(company)}_{safe_name(role)}.{extension}'


def profile_info(profile):
    from src.resume_import import review_text
    urls = set(profile['candidate'].get('links', {}).values()) if profile else set()
    if profile:
        urls.update(f['url'] for f in profile['facts'] if f.get('url'))
    return {'name': profile['candidate']['name'] if profile else None,
            'fact_count': len(profile['facts']) if profile else 0, 'link_count': len(urls),
            'emphasis_count': sum(len(f.get('emphasis', [])) for f in profile['facts']) if profile else 0,
            'review_text': review_text(profile) if profile else ''}


def generate(payload, output_root):
    for key in ('jd', 'company', 'role'):
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            raise ValueError(f'{key} is required')
    if len(payload['jd']) > 60_000 or any(len(payload[k]) > 150 for k in ('company', 'role')):
        raise ValueError('JD must be under 60,000 characters; company and role under 150')
    profile = load_profile()
    analysis = analyze_jd(payload['jd'])
    mapping = match_requirements(profile, analysis)
    score = score_mapping(mapping)
    content = tailor(profile, mapping)
    from src.skill_actions import options, plan
    skill_options = options(profile, mapping)
    selected = payload.get('selected_skills', [])
    plan(profile, selected)
    if any(key not in {item['key'] for item in skill_options} for key in selected):
        raise ValueError('Selected skill is not supported for this JD')
    visible_before = sum(item['action'] == 'highlight' for item in skill_options)
    visible_after = visible_before + sum(item['action'] == 'add' and item['key'] in selected
                                         for item in skill_options)
    skill_visibility = {'before': visible_before, 'after': visible_after,
                        'total': len(skill_options)}
    content['selected_skills'] = selected
    content_check = validate_content(profile, content)
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '_' + secrets.token_hex(6)
    output = output_root / run_id
    output.mkdir(parents=True, exist_ok=False)
    tex = output / 'resume.tex'
    tex.write_text(render(profile, content), encoding='utf-8')
    compilation = compile_pdf(tex, profile)
    renderer = 'LaTeX'
    pdf_check = compilation.get('pdf_validation', {})
    if compilation['status'] != 'passed':
        # Keep compiler diagnostics. A proof is explicitly identified in the UI.
        from src.layout_proof import create_proof
        pdf_check = create_proof(profile, content, output / 'preview.pdf')
        if (output / 'resume.pdf').exists():
            (output / 'resume.pdf').rename(output / 'unvalidated-latex.pdf')
        (output / 'preview.pdf').rename(output / 'resume.pdf')
        renderer = 'ReportLab layout preview'
    pdf_check = validate_pdf(output / 'resume.pdf', profile, content)
    validation = {'content': content_check, 'compilation': compilation, 'pdf': pdf_check,
                  'renderer': renderer, 'status': 'partially_validated',
                  'human_review': 'required', 'application_ready': False,
                  'unresolved_master_items': profile['unresolved']}
    reports(output, profile, analysis, mapping, score, content, validation,
            payload['company'], payload['role'])
    with (output / 'score_report.md').open('a', encoding='utf-8') as score_file:
        score_file.write(f'\nSupported JD skills visible in Skills: {visible_before}/{len(skill_options)} '
                         f'→ {visible_after}/{len(skill_options)}. This counts literal, evidence-backed '
                         'JD skill labels in the Skills section only. It does not measure skill depth, '
                         'candidate fit, or ATS performance.\n')
    if selected:
        with (output / 'resume_changes.md').open('a', encoding='utf-8') as changes_file:
            changes_file.write('\n## Selected skill presentation\n\n')
            for item in skill_options:
                if item['key'] in selected:
                    changes_file.write('- ' + item['label'] + ': ' + item['action'] + ' (' + item['context'] + '), evidence: ' + ', '.join(item['evidence_ids']) + '\n')
            changes_file.write('\nOriginal claims and candidate fit unchanged. New labels are derived literally from master facts.\n')
    import pypdfium2
    with pypdfium2.PdfDocument(str(output / 'resume.pdf')) as document:
        page = document[0]
        bitmap = page.render(scale=1.5)
        try:
            bitmap.to_pil().save(output / 'preview.png')
        finally:
            bitmap.close()
            page.close()
    originals = {}
    for fact in profile['facts']:
        originals.setdefault(fact['section'], []).append(fact['id'])
    by_id = {f['id']: f for f in profile['facts']}
    changes = [{'section': section, 'before': originals.get(section, []), 'after': ids,
                'labels': {fid: by_id[fid]['approved_text'] for fid in ids}}
               for section, ids in content['sections'].items() if originals.get(section, []) != ids]
    return {'id': run_id, 'score': score, 'mapping': mapping, 'changes': changes,
            'skill_options': skill_options, 'selected_skills': selected,
            'skill_visibility': skill_visibility,
            'download_names': {'resume.pdf': download_name(payload['company'], payload['role'], 'pdf'),
                               'resume.tex': download_name(payload['company'], payload['role'], 'tex')},
            'validation': validation, 'fact_count': len(content['claims']),
            'downloads': {name: f'/runs/{run_id}/{name}' for name in sorted(FILES)}}


def make_server(port=8765, output_root=None):
    output_root = Path(output_root or ROOT / 'output/ui').resolve()
    token = secrets.token_urlsafe(32)
    generation_lock = Lock()  # PDF renderers share process state; serialize generation.

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def log_message(self, *_):
            pass  # Do not log JDs or candidate data.

        def send(self, status, body, content_type='application/json; charset=utf-8', filename=None):
            if not isinstance(body, bytes):
                body = json.dumps(body).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            if filename:
                self.send_header('Content-Disposition', f'inline; filename="{filename}"')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; frame-src 'self'; object-src 'self'; frame-ancestors 'self'")
            self.end_headers()
            self.wfile.write(body)

        def allowed_host(self):
            return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}',
                                                f'localhost:{self.server.server_port}'}

        def do_GET(self):
            if not self.allowed_host():
                return self.send(403, {'error': 'Local host required'})
            path = urlsplit(self.path).path
            if path == '/':
                body = (UI / 'index.html').read_text(encoding='utf-8').replace('@@TOKEN@@', token)
                return self.send(200, body.encode(), 'text/html; charset=utf-8')
            if path == '/api/profile':
                from src.main import PROFILE
                profile = load_profile() if PROFILE.exists() else None
                return self.send(200, profile_info(profile))
            if path in ('/app.js', '/style.css', '/resume-format.txt'):
                file = UI / path[1:]
            elif path.startswith('/runs/'):
                parts = path.split('/')
                if len(parts) != 4 or parts[3] not in FILES:
                    return self.send(404, {'error': 'File not found'})
                import re
                if not re.fullmatch(r'[0-9]{8}T[0-9]{6}_[a-f0-9]{12}', parts[2]):
                    return self.send(404, {'error': 'File not found'})
                file = output_root / parts[2] / parts[3]
            else:
                return self.send(404, {'error': 'Page not found'})
            if not file.is_file():
                return self.send(404, {'error': 'File not found'})
            filename = None
            if path.startswith('/runs/') and file.name in {'resume.pdf', 'resume.tex'}:
                manifest = json.loads((file.parent / 'run_manifest.json').read_text(encoding='utf-8'))
                filename = download_name(manifest['company'], manifest['role'], file.suffix[1:])
            return self.send(200, file.read_bytes(), mimetypes.guess_type(file.name)[0] or 'application/octet-stream', filename)

        def do_POST(self):
            try:
                size = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                return self.send(400, {'error': 'Invalid request length'})
            if size <= 0 or size > MAX_BODY:
                return self.send(413, {'error': 'Request is empty or too large'})
            # Consume bounded bodies before rejecting so Windows does not reset
            # the connection and hide the actionable response from the browser.
            raw = self.rfile.read(size)
            if not self.allowed_host() or self.headers.get('X-Resume-Token') != token:
                return self.send(403, {'error': 'Reload this local page and try again'})
            if self.path not in ('/api/tailor', '/api/extract', '/api/resume', '/api/prepare'):
                return self.send(404, {'error': 'Endpoint not found'})
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                return self.send(415, {'error': 'JSON required'})
            try:
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise ValueError('Expected a JSON object')
                with generation_lock:
                    if self.path == '/api/extract':
                        from pypdf import PdfReader
                        encoded = payload.get('data', '')
                        if not isinstance(encoded, str):
                            raise ValueError('PDF data must be base64 text')
                        data = base64.b64decode(encoded, validate=True)
                        if not data.startswith(b'%PDF'):
                            raise ValueError('Upload a valid text-based PDF')
                        try:
                            reader = PdfReader(io.BytesIO(data))
                            if reader.is_encrypted or not 1 <= len(reader.pages) <= 10:
                                raise ValueError('Use an unencrypted PDF of 1 to 10 pages')
                            text = '\n'.join(page.extract_text(extraction_mode='layout') or '' for page in reader.pages)
                        except ValueError:
                            raise
                        except Exception as exc:
                            raise ValueError('PDF could not be read; upload the recommended TXT format') from exc
                        if not text.strip() or len(text) > 60000:
                            raise ValueError('PDF needs selectable text under 60,000 characters; scanned PDFs need OCR first')
                        from src.pdf_links import extract_links
                        result = {'text': text, 'links': extract_links(data, reader)}
                    elif self.path == '/api/prepare':
                        from src.resume_import import prepare_resume
                        result = {'text': prepare_resume(payload.get('text'), payload.get('links'))}
                    elif self.path == '/api/resume':
                        from src.resume_import import parse_resume, retain_existing_emphasis
                        from src.main import PROFILE, dump
                        profile = parse_resume(payload.get('text'))
                        clear_emphasis = payload.get('clear_emphasis', False)
                        if not isinstance(clear_emphasis, bool):
                            raise ValueError('clear_emphasis must be a boolean')
                        if not clear_emphasis and PROFILE.exists():
                            profile = retain_existing_emphasis(profile, load_profile())
                        PROFILE.parent.mkdir(parents=True, exist_ok=True)
                        temporary = PROFILE.with_suffix('.tmp')
                        dump(temporary, profile)
                        temporary.replace(PROFILE)
                        result = profile_info(profile)
                    else:
                        from src.main import PROFILE
                        if not PROFILE.exists():
                            raise ValueError('Upload and review a resume first')
                        result = generate(payload, output_root)
                self.send(200, result)
            except (ValueError, KeyError, UnicodeError) as exc:
                self.send(400, {'error': str(exc)})
            except Exception:
                self.send(500, {'error': 'Operation failed. Check Python dependencies, local storage, and Calibri fonts. No application was submitted.'})

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    server = make_server(args.port)
    print(f'Resume workspace: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
