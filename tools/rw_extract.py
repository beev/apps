"""Extract structured content from a RapidWeaver 8 Styled Text Data.archive.

The page body is an NSAttributedString. Headings are not font styling: they are
RapidWeaver "markup directives" (kRWTextViewMarkupDirectivesAttribute) carrying
an explicit HTML tag. Images are NSTextAttachment runs, each one character wide
(U+FFFC) in the string, wrapping an NSFileWrapper with the original filename.
"""
import plistlib, sys, json, os

def decode_runs(data, nattrs):
    """NSAttributeInfo: (length, attrIndex) pairs. A length byte with the high
    bit set is low 7 bits of a 14-bit little-endian length."""
    runs, i = [], 0
    while i < len(data):
        b = data[i]
        if b & 0x80:
            length = (b & 0x7F) | (data[i + 1] << 7); i += 2
        else:
            length = b; i += 1
        runs.append((length, data[i])); i += 1
    return runs

def extract(path):
    d = plistlib.load(open(path, 'rb')); o = d['$objects']
    R = lambda x: o[x.data] if isinstance(x, plistlib.UID) else x
    s = R(o[1]['text'])
    text = R(s['NSString'])
    attrs = [R(a) for a in R(s['NSAttributes'])['NS.objects']]

    parsed = []
    for ad in attrs:
        keys = [R(k) for k in ad['NS.keys']]
        entry = {'tag': None, 'italic': False, 'image': None}
        for k, v in zip(keys, ad['NS.objects']):
            if k == 'kRWTextViewMarkupDirectivesAttribute':
                dd = R(v)
                m = dict(zip([R(x) for x in dd['NS.keys']],
                             [R(x) for x in dd['NS.objects']]))
                entry['tag'] = m.get('tag')
            elif k == 'NSFont':
                entry['italic'] = 'Oblique' in R(R(v)['NSName']) or 'Italic' in R(R(v)['NSName'])
            elif k == 'NSAttachment':
                entry['image'] = find_filename(R(v), R)
        parsed.append(entry)

    runs = decode_runs(R(s['NSAttributeInfo'])['NS.data'], len(attrs))
    out, pos = [], 0
    for length, idx in runs:
        chunk = text[pos:pos + length]; pos += length
        a = parsed[idx] if idx < len(parsed) else {'tag': None, 'italic': False, 'image': None}
        out.append({'text': chunk, **a})
    return out

def find_filename(node, R, depth=0):
    """Walk the attachment's object graph for the NSFileWrapper's filename."""
    if depth > 8: return None
    if isinstance(node, dict):
        for k, v in node.items():
            if k == '$class': continue
            rv = R(v)
            if k == 'NS.keys':
                names = [R(x) for x in v] if isinstance(v, list) else []
                if 'filename' in names:
                    i = names.index('filename')
                    val = R(R(node['NS.objects'][i]))
                    if isinstance(val, dict): val = R(val.get('NS.string'))
                    return val
            f = find_filename(rv, R, depth + 1)
            if f: return f
    elif isinstance(node, list):
        for v in node:
            f = find_filename(R(v), R, depth + 1)
            if f: return f
    return None

if __name__ == '__main__':
    for r in extract(sys.argv[1]):
        label = r['tag'] or ('IMG' if r['image'] else ('i' if r['italic'] else 'p'))
        body = r['image'] or r['text'].replace('\n', '\\n')
        print(f"[{label:3}] {body[:110]}")
