"""Derive presentation-only skill actions from literal master evidence."""
import re

ADDABLE = {'java', 'go', 'python', 'sql', 'typescript', 'javascript', 'rust', 'kotlin',
           'spring boot', 'spring mvc', 'rest api', 'hibernate', 'jpa', 'react', 'node.js',
           'junit', 'mockito', 'postgresql', 'mysql', 'mongodb', 'redis', 'kafka', 'sqs',
           'rabbitmq', 'cassandra', 'dynamodb', 'aws', 'eks', 'lambda', 's3', 'kubernetes',
           'docker', 'ci/cd', 'spinnaker', 'jenkins', 'gcp', 'azure', 'llm', 'grafana',
           'sonarqube', 'jacoco', 'openshift'}


def literal_label(text, key):
    from src.main import ALIASES
    for alias in ALIASES.get(key, []):
        match = re.search(r'(?<!\w)' + re.escape(alias) + r'(?!\w)', text, re.I)
        if match:
            return match[0]
    return None


def options(profile, mapping):
    result = []
    for key in dict.fromkeys(row['canonical'] for row in mapping):
        evidence = [f for f in profile['facts'] if f['status'] != 'unverified'
                    and literal_label(f['approved_text'], key)]
        listed = [f for f in evidence if f['section'] == 'skills']
        if not listed and key not in ADDABLE:
            continue  # Do not turn incidental words such as "tests" into skills.
        professional = [f for f in evidence if f['section'] == 'experience']
        projects = [f for f in evidence if f['section'] == 'projects']
        supporting = listed or professional or projects
        if not supporting:
            continue
        label = literal_label(supporting[0]['approved_text'], key)
        result.append({'key': key, 'label': label,
                       'action': 'highlight' if listed else 'add',
                       'context': 'already listed' if listed else 'professional experience' if professional else 'project use',
                       'evidence_ids': [f['id'] for f in supporting]})
    return result


def plan(profile, selected):
    if not isinstance(selected, list) or any(not isinstance(k, str) for k in selected) or len(selected) != len(set(selected)):
        raise ValueError('Selected skills must be unique skill keys')
    allowed = {item['key']: item for item in options(profile, [{'canonical': k} for k in selected])}
    if any(key not in allowed for key in selected):
        raise ValueError('Selected skill has no literal master evidence')
    highlights, additions = {}, {}
    skills = [f for f in profile['facts'] if f['section'] == 'skills']
    for key in selected:
        item = allowed[key]
        if item['action'] == 'highlight':
            for fact in skills:
                label = literal_label(fact['approved_text'], key)
                if label:
                    highlights.setdefault(fact['id'], []).append(label)
        else:
            # Keep the existing skill row intact and append a literal technology
            # name. Evidence depth remains explicit in the change report.
            groups = {
                'Languages': {'java', 'go', 'python', 'sql', 'typescript', 'javascript', 'rust', 'kotlin'},
                'Frameworks': {'spring boot', 'spring mvc', 'rest api', 'hibernate', 'jpa', 'react', 'node.js', 'junit', 'mockito', 'testing'},
                'Data & Messaging': {'postgresql', 'mysql', 'mongodb', 'redis', 'kafka', 'sqs', 'rabbitmq', 'cassandra', 'dynamodb', 'caching'},
                'Cloud & DevOps': {'aws', 'eks', 'lambda', 's3', 'kubernetes', 'docker', 'ci/cd', 'spinnaker', 'jenkins', 'gcp', 'azure', 'disaster recovery'},
                'AI/ML': {'llm'},
            }
            group = next((name for name, keys in groups.items() if key in keys), 'Payments & Observability')
            target = next((f for f in skills if f['approved_text'].startswith(group + ':')), skills[0])
            additions.setdefault(target['id'], []).append(item)
    return highlights, additions


def suffix(items):
    return ', ' + ', '.join(item['label'] for item in items)
