"""Read visible anchor labels and HTTPS destinations from uploaded PDFs."""
import re
import pypdfium2
from src.main import tex_link


def extract_links(data, reader):
    links = []
    seen = set()
    with pypdfium2.PdfDocument(data) as document:
        for index, source_page in enumerate(reader.pages):
            page = document[index]
            text_page = page.get_textpage()
            try:
                for ref in source_page.get('/Annots', []):
                    annotation = ref.get_object()
                    url = str(annotation.get('/A', {}).get('/URI', ''))
                    if url.lower().startswith('http://'):
                        raise ValueError('A PDF link uses HTTP. Add a reviewed HTTPS destination in the TXT format instead.')
                    if not url.lower().startswith('https://'):
                        continue  # Do not turn executable or local actions into web links.
                    tex_link(url, 'link')
                    rect = annotation.get('/Rect')
                    if not rect or len(rect) != 4:
                        raise ValueError('A PDF link has no usable label bounds; add its URL in the review editor')
                    left, bottom, right, top = map(float, rect)
                    label = re.sub(r'\s+', ' ', text_page.get_text_bounded(left, bottom, right, top)).strip()
                    label = label or 'Website'
                    if (label, url) not in seen:
                        links.append({'label': label, 'url': url})
                        seen.add((label, url))
                    if len(links) > 100:
                        raise ValueError('Resume contains more than 100 web links')
            finally:
                text_page.close()
                page.close()
    return links
