import base64
import copy
import http.client
import io
import json
import re
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from src.main import ROOT, analyze_jd, match_requirements, tailor, render, validate_content
from src.resume_import import parse_resume, prepare_resume
from src.web import make_server


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT / 'ui/resume-format.txt').read_text()

    def test_parser_preserves_claims_and_employer(self):
        p = parse_resume(self.text)
        self.assertEqual('Alex Example', p['candidate']['name'])
        self.assertEqual('Example Company', p['employers'][0]['name'])
        for fact in p['facts']:
            self.assertIn(fact['approved_text'], self.text)
        self.assertNotIn('experience_years', p['candidate'])

    def test_invalid_structure_is_actionable(self):
        for text in ['', self.text.replace('Email:', 'Mail:'), self.text.replace('Frameworks:', 'Frameworks'),
                     self.text.replace('Example Company | Software Engineer |', 'Example Company'),
                     self.text.replace('alex@example.com', 'bad-email')]:
            with self.assertRaises(ValueError): parse_resume(text)

    def test_generic_degree_and_tex_injection(self):
        p = parse_resume(self.text.replace('Bachelor of Science', r'BSc \input{secret}'))
        content = tailor(p, match_requirements(p, analyze_jd('JavaScript required')))
        output = render(p, content)
        self.assertNotIn(r'BSc \input{secret}', output)
        generic = parse_resume(self.text)
        self.assertIn('Bachelor', render(generic, tailor(generic, [])))

    def test_fact_mutation_rejected(self):
        p = parse_resume(self.text)
        content = tailor(p, [])
        content['claims'][0]['text'] = 'Invented experience'
        with self.assertRaises(ValueError): validate_content(p, content)

    def test_pdf_layout_preparation_preserves_wrapped_claims_and_groups(self):
        raw = '''ALEX EXAMPLE
SOFTWARE ENGINEER
alex@example.com | +1-555-010-1234
SUMMARY
Engineer building services
with automated tests.
SKILLS
Languages: Python,
JavaScript
EXPERIENCE
Example Company, Software Engineer              Jan 2023 - Present
Backend services team
� Built APIs using Node.js
  and request validation.
Second Company, Engineer                       Jan 2021 - Dec 2022
• Added database tests.
PROJECTS
SampleApp React task manager
• Built a task manager.
  Added request validation.
OtherApp Python utility
• Built a file parser.
EDUCATION
Example University, Bachelor of Science, 2021
'''
        prepared = prepare_resume(raw)
        p = parse_resume(prepared)
        self.assertEqual(2, len(p['employers']))
        self.assertIn('Engineer building services with automated tests.', prepared)
        self.assertIn('Languages: Python, JavaScript', prepared)
        self.assertIn('- Built APIs using Node.js and request validation.', prepared)
        self.assertEqual('ALEX EXAMPLE', p['candidate']['name'])
        self.assertEqual('Backend services team', p['employers'][0]['context'])
        projects = [f for f in p['facts'] if f['section'] == 'projects']
        self.assertEqual(2, len(projects))
        self.assertEqual('SampleApp React task manager', projects[0]['title'])
        self.assertIn('Added request validation.', projects[0]['approved_text'])

    def test_preparation_does_not_guess_unstructured_employers(self):
        with self.assertRaisesRegex(ValueError, 'Section headings'):
            prepare_resume('A flat document without detectable headings. ' * 3)
        self.assertEqual(self.text, prepare_resume(self.text))


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.profile = Path(self.temp.name) / 'local-data/profile.json'
        self.patch = patch('src.main.PROFILE', self.profile)
        self.patch.start()
        self.server = make_server(0, Path(self.temp.name) / 'output')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        _, page, _ = self.request('GET', '/')
        self.token = re.search(r'name="resume-token" content="([^"]+)"', page.decode())[1]
        self.text = (ROOT / 'ui/resume-format.txt').read_text()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.patch.stop(); self.temp.cleanup()

    def request(self, method, path, payload=None, authenticated=True):
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=30)
        headers = {'Content-Type': 'application/json'}
        if authenticated and hasattr(self, 'token'): headers['X-Resume-Token'] = self.token
        c.request(method, path, json.dumps(payload) if payload is not None else None, headers)
        response = c.getresponse(); result = response.status, response.read(), dict(response.getheaders()); c.close()
        return result

    def test_empty_install_requires_upload(self):
        status, data, _ = self.request('GET', '/api/profile')
        self.assertEqual(200, status)
        self.assertIsNone(json.loads(data)['name'])
        self.assertEqual(400, self.request('POST', '/api/tailor', {'company':'Example','role':'Engineer','jd':'JavaScript'})[0])

    def test_invalid_import_preserves_saved_profile(self):
        self.assertEqual(200, self.request('POST', '/api/resume', {'text':self.text})[0])
        before = self.profile.read_bytes()
        self.assertEqual(400, self.request('POST', '/api/resume', {'text':'invalid'})[0])
        self.assertEqual(before, self.profile.read_bytes())

    def test_import_generation_and_skill_visibility(self):
        self.request('POST', '/api/resume', {'text':self.text})
        payload = {'company':'Example','role':'Engineer','jd':'Requirements:\nNode.js and TypeScript required.'}
        status, data, _ = self.request('POST', '/api/tailor', payload)
        self.assertEqual(200, status, data)
        before = json.loads(data)
        payload['selected_skills'] = ['node.js','typescript']
        status, data, _ = self.request('POST', '/api/tailor', payload)
        self.assertEqual(200, status, data)
        after = json.loads(data)
        self.assertEqual(before['score'], after['score'])
        self.assertEqual({'before':1,'after':2,'total':2}, after['skill_visibility'])
        self.assertTrue(after['validation']['pdf']['checks']['all_master_claims_extracted'])
        self.assertTrue(after['validation']['pdf']['checks']['skill_additions_extracted'])
        status, pdf, headers = self.request('GET', after['downloads']['resume.pdf'])
        self.assertEqual(200, status)
        self.assertTrue(pdf.startswith(b'%PDF'))
        self.assertIn('Resume_Example_Engineer.pdf', headers['Content-Disposition'])

    def test_pdf_extract_and_invalid_pdf(self):
        from reportlab.pdfgen.canvas import Canvas
        stream = io.BytesIO(); canvas = Canvas(stream); canvas.drawString(30,700,'Synthetic resume text'); canvas.save()
        status, data, _ = self.request('POST', '/api/extract', {'data':base64.b64encode(stream.getvalue()).decode()})
        self.assertEqual(200, status)
        self.assertIn('Synthetic resume text', json.loads(data)['text'])
        for value in ('not base64', base64.b64encode(b'%PDF invalid').decode()):
            self.assertEqual(400, self.request('POST', '/api/extract', {'data':value})[0])

    def test_token_and_file_boundary(self):
        self.assertEqual(403, self.request('POST','/api/resume',{'text':self.text},False)[0])
        for path in ('/local-data/candidate_profile.json','/runs/../../README.md','/src/main.py'):
            self.assertEqual(404, self.request('GET',path)[0])
