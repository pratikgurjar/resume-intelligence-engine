"""Import explicitly structured resume text without inferring qualifications."""
import re
from src.main import terms, tex_link

SECTIONS = ('summary', 'skills', 'experience', 'projects', 'education', 'achievements', 'certifications')


def review_text(profile):
    candidate = profile['candidate']
    lines = ['Name: ' + candidate['name'], 'Headline: ' + candidate['headline']]
    lines.extend(key.title() + ': ' + candidate['contact'][key] for key in ('email', 'phone', 'location', 'availability'))
    lines.extend(f'Link: {label} | {url}' for label, url in candidate.get('links', {}).items())
    for section in SECTIONS:
        facts = [fact for fact in profile['facts'] if fact['section'] == section]
        if not facts:
            continue
        lines.extend(['', '[' + section.title() + ']'])
        if section == 'experience':
            for employer in profile['employers']:
                lines.append(' | '.join(employer[key] for key in ('name', 'title', 'dates')))
                if employer['context']:
                    lines.append('Context: ' + employer['context'])
                lines.extend('- ' + f['approved_text'] for f in facts if f['employer_id'] == employer['id'])
        else:
            for fact in facts:
                if section == 'projects':
                    lines.append('Title: ' + fact['title'])
                    if fact.get('url'):
                        lines.append('URL: ' + fact['url'])
                lines.append(fact['approved_text'])
                if section == 'certifications' and fact.get('url'):
                    lines.append(f'Link: {fact["link_label"]} | {fact["url"]}')
    return '\n'.join(lines) + '\n'


def prepare_resume(text, links=None):
    """Convert layout-preserving extraction to an editable draft, never auto-save."""
    if not isinstance(text, str) or not 50 <= len(text) <= 60000:
        raise ValueError('Resume text must contain 50 to 60,000 characters')
    if re.search(r'^Name:', text, re.M | re.I):
        return attach_links(text, links)
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
    extra = [part.strip() for part in contact.split('|') if part.strip()
             and '@' not in part and not re.search(r'\d[\d ()-]{7,}\d', part)
             and part.strip().lower() not in ('linkedin', 'github', 'portfolio', 'website')
             and not part.strip().startswith('https://')]
    availability = [part for part in extra if re.search(r'\b(immediate|joiner|available|availability|notice)\b', part, re.I)]
    location = [part for part in extra if part not in availability]
    output = [f'Name: {name}', f'Headline: {headline}', f'Email: {email[0] if email else ""}',
              f'Phone: {phone[0] if phone else ""}', 'Location: ' + ' | '.join(location),
              'Availability: ' + ' | '.join(availability), '']
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
        elif section == 'certifications' and pending.endswith(')'):
            flush(); pending = line
        else:
            pending = (pending + ' ' + line).strip()
    flush()
    return attach_links('\n'.join(output) + '\n', links)


def attach_links(text, links):
    if links is None:
        return text
    if not isinstance(links, list) or len(links) > 100:
        raise ValueError('Expected at most 100 PDF links')
    lines = text.splitlines()
    for item in links:
        if not isinstance(item, dict) or not all(isinstance(item.get(k), str) for k in ('label', 'url')):
            raise ValueError('Invalid PDF link')
        label, url = item['label'], item['url']
        if not label or len(label) > 200 or any(c in label for c in '\r\n|'):
            raise ValueError('PDF link label needs correction')
        tex_link(url, label)
        if any(line.endswith(url) and line.startswith(('Link:', 'URL:')) for line in lines):
            continue
        section = None
        matched = False
        for index, line in enumerate(lines):
            if line.strip('[]').lower() in SECTIONS:
                section = line.strip('[]').lower()
            if section == 'projects' and line.startswith('Title:') and label.casefold() in line.casefold():
                lines.insert(index + 1, 'URL: ' + url)
                matched = True
                break
            if section == 'certifications' and not line.startswith('Link:') and label.casefold() in line.casefold():
                lines.insert(index + 1, f'Link: {label} | {url}')
                matched = True
                break
        if not matched:
            index = next((i for i, line in enumerate(lines) if line.startswith('[')), len(lines))
            lines.insert(index, f'Link: {label} | {url}')
    return '\n'.join(lines) + '\n'


def parse_resume(text):
    if not isinstance(text, str) or not 50 <= len(text) <= 60000:
        raise ValueError('Resume text must contain 50 to 60,000 characters')
    fields, facts, employers, links = {}, [], [], {}
    section = None
    employer = None
    project_title = 'Project details'
    project_url = None
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        heading = line.strip('[]').lower()
        if heading in SECTIONS:
            section = heading
            continue
        if line.startswith('Link:'):
            label, separator, url = line[5:].strip().partition('|')
            label, url = label.strip(), url.strip()
            if not separator or not label:
                raise ValueError('Use Link: label | https://destination')
            tex_link(url, label)
            if section is None:
                if label in links and links[label] != url:
                    raise ValueError('Use distinct labels for different contact links')
                links[label] = url
            elif section == 'certifications' and facts and facts[-1]['section'] == section and label in facts[-1]['approved_text']:
                if facts[-1].get('url') not in (None, url):
                    raise ValueError('Use one reviewed URL per certification')
                facts[-1].update(url=url, link_label=label)
            else:
                raise ValueError('Place contact links before sections or a certificate link after its matching text')
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
            project_url = None
            project_title = line.partition(':')[2].strip()
            if ' ' not in project_title:
                project_title += ' details'
            continue
        if section == 'projects' and line.startswith('URL:'):
            if project_url is not None:
                raise ValueError('Use one reviewed URL per project')
            project_url = line[4:].strip()
            tex_link(project_url, 'project')
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
            if project_url:
                fact['url'] = project_url
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
                          'contact': {k: fields.get(k, '') for k in ('email', 'phone', 'location', 'availability')}, 'links': links},
            'facts': facts, 'employers': employers, 'sources': [],
            'unresolved': [{'detail': 'User-uploaded statements are not independently verified. Review extraction, dates, and all claims.'}]}
