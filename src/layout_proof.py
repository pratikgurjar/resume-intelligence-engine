"""ReportLab layout proof, NOT a LaTeX compilation. No fabricated validation."""
from __future__ import annotations
import html
import json
import re
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle, Flowable
from src.main import ROOT, load_profile, tailor, validate_content, dump, validate_pdf

NAVY = colors.HexColor('#17365D')
MUTED = colors.HexColor('#7F8C9D')
RULE = colors.HexColor('#B8C6D8')

def markup(f, highlights=None, additions=None):
    text = html.escape(f['approved_text'])
    emphasis = json.loads((ROOT / 'templates/emphasis.json').read_text(encoding='utf-8'))
    for phrase in sorted(emphasis.get(f['id'], []), key=len, reverse=True):
        token = html.escape(phrase)
        text = text.replace(token, '<b>' + token + '</b>')
    if f['section'] == 'skills':
        label, rest = text.split(':', 1)
        text = '<b><font color="#17365D">' + label + ':</font></b>' + rest
        for phrase in sorted(highlights or [], key=len, reverse=True):
            token = html.escape(phrase)
            text = re.sub(r'(?<!\w)' + re.escape(token) + r'(?!\w)', lambda _: '<b>' + token + '</b>', text)
        if additions:
            from src.skill_actions import suffix
            text += html.escape(suffix(additions))
    if f['section'] == 'certifications' and f.get('url'):
        label = html.escape(f['link_label'])
        text = text.replace('(' + label + ',', '(' + link_markup(f['url'], label) + ',')
    return text


def link_markup(url, label):
    if not re.fullmatch(r'https://[A-Za-z0-9._~:/?#\[\]@!$&\x27()*+,;=%-]+', url):
        raise ValueError('Invalid HTTPS link')
    return '<link href="' + html.escape(url, quote=True) + '"><font color="#0000CC"><u>' + label + '</u></font></link>'


class Section(Flowable):
    def __init__(self, text):
        super().__init__()
        self.text = text.upper()
        self.height = 18

    def wrap(self, available_width, available_height):
        self.width = available_width
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.setFillColor(NAVY)
        c.setFont('CalibriB', 8.6)
        c.drawString(0, 6.5, self.text)
        c.setStrokeColor(RULE)
        c.setLineWidth(0.65)
        c.line(0, 2, self.width, 2)


def create_proof(profile, content, output):
    validate_content(profile, content)
    from src.skill_actions import plan
    highlights, additions = plan(profile, content.get('selected_skills', []))
    font_root = Path('C:/Windows/Fonts')
    for name, file in [('Calibri', 'calibri.ttf'), ('CalibriB', 'calibrib.ttf'),
                       ('CalibriI', 'calibrii.ttf'), ('CalibriBI', 'calibriz.ttf')]:
        path = font_root / file
        if not path.is_file():
            raise ValueError('Calibri is unavailable. Supply the licensed font files; no silent font substitution.')
        pdfmetrics.registerFont(TTFont(name, str(path)))
    pdfmetrics.registerFontFamily('Calibri', normal='Calibri', bold='CalibriB', italic='CalibriI', boldItalic='CalibriBI')
    body = ParagraphStyle('body', fontName='Calibri', fontSize=9.5, leading=11.6,
                          textColor=colors.black, spaceAfter=1)
    bullet = ParagraphStyle('bullet', parent=body, leftIndent=9, firstLineIndent=-9, spaceAfter=0.2)
    context = ParagraphStyle('context', parent=body, fontName='CalibriI', fontSize=8.5,
                             leading=10.4, textColor=MUTED, spaceAfter=4)
    by_id = {f['id']: f for f in profile['facts']}
    width = 540
    story = []

    def paragraph(text, style=body):
        return Paragraph(text, style)

    def row(left, right, style=body, date_width=120):
        t = Table([[paragraph(left, style), paragraph(html.escape(right), ParagraphStyle('date', parent=style, alignment=2))]],
                  colWidths=[width - date_width, date_width])
        t.setStyle(TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                               ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
                               ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
        return t

    for section in ('summary', 'skills', 'experience', 'projects', 'education', 'achievements', 'certifications'):
        story.append(Section(section))
        ids = content['sections'].get(section, [])
        if section == 'experience':
            for employer in profile['employers']:
                story += [row('<b>' + html.escape(employer['name']) + '</b>, ' + html.escape(employer['title']), employer['dates']),
                          paragraph(html.escape(employer['context']), context)]
                for fid in ids:
                    if by_id[fid].get('employer_id') == employer['id']:
                        story.append(paragraph('• ' + markup(by_id[fid]), bullet))
                story.append(Spacer(1, 3))
        elif section == 'projects':
            for fid in ids:
                f = by_id[fid]
                name, rest = f['title'].split(' ', 1)
                heading = link_markup(f['url'], html.escape(name)) if f.get('url') else '<u>' + html.escape(name) + '</u>'
                story.append(paragraph('<b>' + heading + '</b>  <font color="#7F8C9D"><i>' + html.escape(rest) + '</i></font>'))
                story.append(paragraph('• ' + markup(f), bullet))
                story.append(Spacer(1, 2))
        else:
            for fid in ids:
                f = by_id[fid]
                if section == 'education':
                    story.append(row(markup(f), f['date'], date_width=35))
                else:
                    story.append(paragraph(('• ' if section in ('achievements', 'certifications') else '') + markup(f, highlights.get(fid), additions.get(fid)),
                                           bullet if section in ('achievements', 'certifications') else body))

        if section == 'skills':
            story.append(Spacer(1, 4))

    def header(c, doc):
        c.saveState()
        c.setFillColor(NAVY)
        c.setFont('CalibriB', 17.5)
        c.drawCentredString(306, 744, profile['candidate']['name'])
        c.setFont('Calibri', 8.3)
        c.setFillColor(MUTED)
        c.drawCentredString(306, 730.5, profile['candidate']['headline'])
        c.setFont('Calibri', 8.5)
        info = profile['candidate']['contact']
        links = []
        for label, url in profile['candidate'].get('links', {}).items():
            if not url or not re.fullmatch(r'https://[A-Za-z0-9._~:/?#\[\]@!$&\x27()*+,;=%-]+', url):
                raise ValueError('Missing or invalid profile link: ' + label)
            links.append('<link href="' + html.escape(url, quote=True) + '"><font color="#0000CC"><u>'
                         + html.escape(label) + '</u></font></link>')
        header_text = (html.escape(info['email'] + '  |  ' + info['phone']) +
                       '  |  '.join([''] + links + ['']) +
                       html.escape(info['location'] + '  |  ' + info['availability']))
        hp = Paragraph(header_text, ParagraphStyle('header', fontName='Calibri', fontSize=8.5,
                                                 leading=10, textColor=MUTED, alignment=1))
        _, hh = hp.wrap(540, 30)
        hp.drawOn(c, 36, 715.5)
        c.restoreState()

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError('Proof output already exists; choose a new path')
    doc = BaseDocTemplate(str(output), pagesize=(612, 792), title='Resume layout preview', author=profile['candidate']['name'])
    frame = Frame(36, 26, 540, 686, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id='resume', frames=[frame], onPage=header)])
    doc.build(story)
    validation = validate_pdf(output, profile, content)
    validation.update(renderer='ReportLab layout proof; not LaTeX-compiled',
                      visual_fidelity='ReportLab proof only; no pixel comparison with the source PDF',
                      application_ready=False)
    dump(output.with_suffix('.validation.json'), validation)
    return validation


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    p = load_profile()
    c = tailor(p, [])
    print(json.dumps(create_proof(p, c, args.output), indent=2))
