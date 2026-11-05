"""Import supplied 2026 A-form PDFs; requires pdftotext (Poppler).
Usage: python3 tools/import_2026.py <session-1.pdf> <session-2.pdf>
The answer key in data/answers-2026.json is transcribed from user-provided images.
"""
import collections
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
KEY = json.loads((ROOT / 'data/answers-2026.json').read_text())
MARKERS = '①②③④⑤'


def extract_questions(pdf, session):
    text = subprocess.run(['pdftotext', '-raw', str(pdf), '-'], check=True,
                          capture_output=True, text=True).stdout
    assert f'2026년도 제25회 3급 청소년상담사 1차 {session}교시' in text
    text = text.replace('\f', '\n')
    text = re.sub(r'^.*2026년도 제25회.*$', '', text, flags=re.M)
    text = re.sub(r'^.*제\d과목.*$', '', text, flags=re.M)
    starts = list(re.finditer(r'^\s*(\d+)\.\s*', text, re.M))
    expected = 100 if session == 1 else 75
    assert [int(m[1]) for m in starts] == list(range(1, expected + 1))
    questions = []
    for i, match in enumerate(starts):
        number = int(match[1])
        block = text[match.end():starts[i+1].start() if i+1 < len(starts) else len(text)].strip()
        markers = list(re.finditer(f'[{MARKERS}]', block))
        assert [m[0] for m in markers] == list(MARKERS), (session, number)
        prompt = block[:markers[0].start()].strip()
        choices = [block[m.end():markers[j+1].start() if j+1 < 5 else len(block)].strip()
                   for j, m in enumerate(markers)]
        assert prompt and all(choices), (session, number)
        subject = next(s for s in KEY['subjects'] if s['session'] == session
                       and s['firstNumber'] <= number < s['firstNumber'] + 25)
        answers = subject['answers'][number - subject['firstNumber']]
        assert answers and all(isinstance(a, int) and 1 <= a <= 5 for a in answers)
        questions.append(dict(id=f'2026-{session}-A-{number}', year=2026,
                              session=session, form='A', number=number,
                              subject=subject['subject'], prompt=prompt, choices=choices,
                              answers=answers, canonical=True))
    return questions


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    target = ROOT / 'questions-data.js'
    existing = target.read_text()
    data = json.loads(existing.split('=', 1)[1].strip().rstrip(';'))
    previous = [q for q in data['questions'] if q['year'] != 2026]
    added = extract_questions(sys.argv[1], 1) + extract_questions(sys.argv[2], 2)
    assert len(added) == 175
    assert all(n == 25 for n in collections.Counter(q['subject'] for q in added).values())
    data['questions'] = previous + added
    assert len({q['id'] for q in data['questions']}) == len(data['questions'])
    data['generatedAt'] = '2026-10-30'
    data['canonicalCount'] = sum(q['canonical'] for q in data['questions'])
    data['totalCount'] = len(data['questions'])
    target.write_text('window.QUIZ_DATA = ' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';\n')
    print(f'Imported {len(added)} questions; total {data["totalCount"]}')


if __name__ == '__main__':
    main()
