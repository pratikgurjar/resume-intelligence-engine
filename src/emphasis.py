"""Keep reviewed bold spans separate from factual resume wording."""
import re


def parse_marked_text(value):
    if value.count('**') % 2:
        raise ValueError('Close each bold phrase with ** in the review editor')
    emphasis = re.findall(r'\*\*(.*?)\*\*', value)
    if any(not phrase.strip() or '\n' in phrase for phrase in emphasis):
        raise ValueError('Bold phrases must contain text on one line')
    plain = re.sub(r'\*\*(.*?)\*\*', r'\1', value)
    return plain, emphasis


def marked_text(value, emphasis):
    spans = emphasized_spans(value, emphasis)
    return ''.join('**' + part + '**' if bold else part for part, bold in spans)


def emphasized_spans(value, emphasis):
    """Return disjoint literal spans, rejecting stale or overlapping emphasis."""
    positions = []
    for phrase in emphasis:
        if not isinstance(phrase, str) or not phrase.strip():
            raise ValueError('Invalid bold phrase')
        start = value.find(phrase)
        if start < 0 or any(start < end and start + len(phrase) > begin for begin, end in positions):
            raise ValueError('Bold phrase must occur once without overlapping another phrase')
        positions.append((start, start + len(phrase)))
    result = []
    cursor = 0
    for begin, end in sorted(positions):
        if begin > cursor:
            result.append((value[cursor:begin], False))
        result.append((value[begin:end], True))
        cursor = end
    if cursor < len(value):
        result.append((value[cursor:], False))
    return result
