"""Import explicitly structured resume text without inferring qualifications."""
import re
from src.main import terms

SECTIONS = ('summary', 'skills', 'experience', 'projects', 'education', 'achievements', 'certifications')


def prepare_resume(text):
    """Convert layout-preserving extraction to an editable draft, never auto-save."""
    if not isinstance(text, str) or not 50 <= len(text) <= 60000:
        raise ValueError('Resume text must contain 50 to 60,000 characters')
    if re.search(r'^Name:', text, re.M | re.I):
        return text
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    first_section = next((i for i, line in enumerate(lines) if line.strip('[]').lower() in SECTIONS), None)
    if first_section is None:
        raise ValueError('Section headings could not be detected. Upload the PDF again for improved extraction, or use the example format.')
    header = lines[:first_section]
    email = re.search(r'[^\s|<>]+@[^\s|<>]+\.[^\s|<>]+', ' '.join(header))
    contact_index = next((i for i, line in enumerate(header) if '@' in line), len(header))
    name = header[0] if contact_index > 0 else ''
    headline = ' '.join(header[1:contact_index])
    contact = ' '.join(header[contact_index:])
    phone = re.search(r'\+?\d[\d ()-]{7,}\d', contact)
    output = [f'Name: {name}', f'Headline: {headline}', f'Email: {email[0] if email else ""}',
              f'Phone: {phone[0] if phone else ""}', 'Location:', 'Availability:', '']
    section = None
    pending = ''

    def flush():
        nonlocal pending
        if pending:
            output.append(pending)
            pending = ''

    body = lines[first_section:]
    for index, line in enumerate(body):
        heading = line.strip('[]').lower()
        if heading in SECTIONS:
            flush(); section = heading; output.extend(['', '[' + heading.title() + ']'])
            continue
        if section == 'experience':
            dated = re.match(r'^(.*?)\s{2,}((?:[A-Za-z]{3,9}\s+)?\d{4}.*(?:\d{4}|Present|Current))$', line, re.I)
            if dated and ',' in dated[1]:
                flush()
                company, role = dated[1].split(',', 1)
                output.append(f'{company.strip()} | {role.strip()} | {dated[2].strip()}')
                continue
            if line.startswith(('•', '�', '-', '●', '▪')):
                flush(); pending = '- ' + line.lstrip('•�-●▪ ').strip()
            elif pending:
                pending += ' ' + line
            else:
                pending = 'Context: ' + line
        elif section == 'projects':
            following = body[index + 1] if index + 1 < len(body) else ''
            if not line.startswith(('•', '�', '-', '●', '▪')) and following.startswith(('•', '�', '-', '●', '▪')):
                flush(); output.append('Title: ' + line)
            elif line.startswith(('•', '�', '-', '●', '▪')):
                flush(); pending = line.lstrip('•�-●▪ ').strip()
            else:
                pending = (pending + ' ' + line).strip()
        elif section == 'skills':
            if re.match(r'^[^:]{1,60}:', line):
                flush(); pending = line
            else:
                pending += ' ' + line
        elif line.startswith(('•', '�', '-', '●', '▪')):
            flush(); pending = line.lstrip('•�-●▪ ').strip()
        else:
            pending = (pending + ' ' + line).strip()
    flush()
    return '\n'.join(output) + '\n'


def parse_resume(text):
    if not isinstance(text, str) or not 50 <= len(text) <= 60000:
        raise ValueError('Resume text must contain 50 to 60,000 characters')
    fields, facts, employers = {}, [], []
    section = None
    employer = None
    project_title = 'Project details'
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
        if section == 'experience' and line.startswith('Context:'):
            if employer is None:
                raise ValueError('Add an employer before Context:')
            employer['context'] = line.partition(':')[2].strip()
            continue
        if section == 'projects' and line.startswith('Title:'):
            project_title = line.partition(':')[2].strip()
            if ' ' not in project_title:
                project_title += ' details'
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
            fact['title'] = project_title
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
