"""Import explicitly structured resume text without inferring qualifications."""
import re
from src.main import terms

SECTIONS = ('summary', 'skills', 'experience', 'projects', 'education', 'achievements', 'certifications')


def parse_resume(text):
    if not isinstance(text, str) or not 50 <= len(text) <= 60000:
        raise ValueError('Resume text must contain 50 to 60,000 characters')
    fields, facts, employers = {}, [], []
    section = None
    employer = None
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        heading = line.strip('[]').lower()
        if heading in SECTIONS:
            section = heading
            continue
        if section is None:
            key, separator, value = line.partition(':')
            if not separator or key.lower() not in ('name', 'headline', 'email', 'phone', 'location', 'availability'):
                raise ValueError(f'Line {number}: use the labeled contact fields in the recommended format')
            if key.lower() in fields:
                raise ValueError(f'Duplicate contact field: {key}')
            fields[key.lower()] = value.strip()
            continue
        if section == 'experience' and not line.startswith(('-', '•')):
            parts = [p.strip() for p in line.split('|')]
            if len(parts) != 3 or not all(parts):
                raise ValueError(f'Line {number}: experience header must be Company | Role | Dates; prefix bullets with -')
            employer = {'id': f'employer-{len(employers)+1}', 'name': parts[0], 'title': parts[1], 'dates': parts[2], 'context': ''}
            employers.append(employer)
            continue
        value = line.lstrip('-• ').strip()
        if section == 'skills' and ':' not in value:
            raise ValueError(f'Line {number}: skills must use Category: skill, skill')
        fact = {'id': f'{section}-{len(facts)+1}', 'section': section, 'original_text': value,
                'approved_text': value, 'tags': sorted(terms(value)), 'status': 'source_backed',
                'source': {'type': 'user_upload', 'locator': f'line {number}'}}
        if section == 'experience':
            if employer is None:
                raise ValueError('Add Company | Role | Dates before experience bullets')
            fact['employer_id'] = employer['id']
        if section == 'projects':
            fact['title'] = 'Project details'
        if section == 'education':
            fact['date'] = ''
        facts.append(fact)
    for key in ('name', 'headline', 'email'):
        if not fields.get(key):
            raise ValueError(f'{key.title()}: is required above the sections')
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', fields['email']):
        raise ValueError('Enter a valid Email: field')
    if not facts or not any(f['section'] == 'skills' for f in facts):
        raise ValueError('Add a [Skills] section and at least one skill category')
    return {'schema_version': 1, 'profile_version': 'user-upload-v1',
            'candidate': {'name': fields['name'], 'headline': fields['headline'],
                          'contact': {k: fields.get(k, '') for k in ('email', 'phone', 'location', 'availability')}, 'links': {}},
            'facts': facts, 'employers': employers, 'sources': [],
            'unresolved': [{'detail': 'User-uploaded statements are not independently verified. Review extraction, dates, and all claims.'}]}
