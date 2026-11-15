#!/usr/bin/env python3
"""Rebuild data/liturgy.json.

1962 (traditional): runs Divinum Officium's missa.pl under the 1960 rubrics for each day
   and reads the Epistle/Lesson and Gospel citations from the generated Mass.
1969 (modern): reads calendar + reading citations from the catholic-readings-api dataset
   (scraped from USCCB). Days that dataset does not cover yet keep any previously saved
   entry, or are left without a 1969 side.

Usage: python3 scripts/regenerate.py [--start YYYY-MM-DD] [--end YYYY-MM-DD]
                                     [--do-dir DIR] [--cra-dir DIR] [--out FILE]
"""
import argparse, datetime, html, json, os, re, subprocess, sys, tempfile
from multiprocessing import Pool

DO_URL = 'https://github.com/DivinumOfficium/divinum-officium'
CRA_URL = 'https://github.com/cpbjr/catholic-readings-api'

BOOK = {'1 Cor':'1 Corinthians','2 Cor':'2 Corinthians','1 John':'1 John','1 Pet':'1 Peter','2 Pet':'2 Peter',
 '1 Thess':'1 Thessalonians','2 Thess':'2 Thessalonians','1 Tim':'1 Timothy','2 Tim':'2 Timothy','2 Esd':'2 Esdras',
 '2 Mach':'2 Maccabees','3 Kgs':'3 Kings','3 Kings':'3 Kings','4 Kings':'4 Kings','Acts':'Acts','Amos':'Amos',
 'Apoc':'Revelation','Rev':'Revelation','Col':'Colossians','Dan':'Daniel','Deut':'Deuteronomy','Eccli':'Sirach',
 'Ecclus':'Sirach','Sir':'Sirach','Eph':'Ephesians','Ex':'Exodus','Exod':'Exodus','Ezech':'Ezekiel','Ezek':'Ezekiel',
 'Gal':'Galatians','Gen':'Genesis','Heb':'Hebrews','Isa':'Isaiah','James':'James','Jas':'James','Jc':'James',
 'Jer':'Jeremiah','Joann':'John','Joel':'Joel','John':'John','Jonas':'Jonah','Judith':'Judith','Lev':'Leviticus',
 'Luc':'Luke','Luke':'Luke','Mal':'Malachi','Marc':'Mark','Mark':'Mark','Matt':'Matthew','Mich':'Micah',
 'Num':'Numbers','Osee':'Hosea','Phil':'Philippians','Prov':'Proverbs','Rom':'Romans','Song':'Song of Songs',
 'Titus':'Titus','Wis':'Wisdom','Zach':'Zechariah'}
NAMEFIX = {'Dominica II Post Pentecosten':'Second Sunday after Pentecost',
 'In Commemoratione Omnium Fidelium Defunctorum':"All Souls' Day (Commemoration of All the Faithful Departed)",
 'Sanctæ Mariæ Sabbato':'Saturday Mass of the Blessed Virgin Mary',
 'Die Quarta Januarii':'Feria (January 4)','Die Quinta Januarii':'Feria (January 5)'}
RANK = {'I':1,'II':2,'III':3,'IV':4}
TYPE = {'SUNDAY':'Sunday','SOLEMNITY':'Solemnity','FEAST':'Feast','MEMORIAL':'Memorial','OPT_MEMORIAL':'Optional memorial',
 'FERIA':'Weekday','COMMEMORATION':'Commemoration','HOLY_WEEK':'Holy Week','TRIDUUM':'Triduum'}

HEAD = re.compile(r"<FONT SIZE='\+1' COLOR=\"red\"><B><I>([^<]+)</I></B></FONT>")
REDI = re.compile(r'<FONT COLOR="red"><I>([^<]+)</I></FONT>')
FALLBACK = re.compile(r"((?:[1-3]\s)?[A-Z][a-z]{1,8}\.?)\s+(\d+\s*[.:]\s*\d+[\d,\-; .:]*?)(?=\s+[A-Z]|\s*$)")
LESSON_HEADS = {'lesson','lectio','prophecy','prophetia','epistle'}
GOSPEL_HEADS = {'gospel','evangelium','passion'}
MISSA = None  # set per process


def init(do_dir):
    global MISSA
    MISSA = os.path.join(do_dir, 'web', 'cgi-bin', 'missa')


def run_missa(date, num=None):
    q = f'date={date:%m-%d-%Y}&version=Rubrics%201960%20-%201960&lang1=English&lang2=English&command=pray'
    if num: q += f'&missanumber={num}'
    env = dict(os.environ, REQUEST_METHOD='GET', QUERY_STRING=q)
    p = subprocess.run(['perl', 'missa.pl'], cwd=MISSA, env=env, capture_output=True, timeout=180)
    return p.stdout.decode('utf-8', 'replace')


def clean(t):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', t))).strip()


def cit_in(rest):
    for c in REDI.finditer(rest[:4000]):
        if re.search(r'\d+:\d+', c.group(1)): return clean(c.group(1))
    t = clean(rest[:1500]); k = t.find('Glory be to Thee')
    seg = t[k:k+400] if k >= 0 else t[:500]
    m = FALLBACK.search(seg)
    if m:
        return (m.group(1).strip() + ' ' + re.sub(r'(\d+)\s*[.:]\s*(\d)', r'\1:\2', m.group(2))).strip().rstrip('.')
    return None


def parse_mass(s):
    body = s[s.lower().find('<body'):]
    raw = re.sub(r'<script.*?</script>|<style.*?</style>', '', body, flags=re.S | re.I)
    title = next((l.strip() for l in html.unescape(re.sub(r'<[^>]+>', '\n', raw)).split('\n') if l.strip()), '')
    out = {'title': title, 'lessons': [], 'gospel': None}
    heads = list(HEAD.finditer(raw)); first_gospel = None
    for i, m in enumerate(heads):
        head = clean(m.group(1)).lower()
        rest = raw[m.end(): heads[i+1].start() if i+1 < len(heads) else len(raw)]
        if head in LESSON_HEADS:
            c = cit_in(rest)
            if c: out['lessons'].append(c)
        elif head in GOSPEL_HEADS:
            if first_gospel is None: first_gospel = m.start()
            c = cit_in(rest)
            if c: out['gospel'] = c  # last Gospel section wins (Palm Sunday)
    if not out['lessons'] and title.startswith('Good Friday') and first_gospel:
        out['lessons'] = [clean(c.group(1)) for c in REDI.finditer(raw[:first_gospel])
                          if re.search(r'\d+:\d+', c.group(1)) and not c.group(1).strip().startswith('Ps')]
    out['n_masses'] = len(re.findall(r"name='missanumber' value='\d'", raw))
    return out


def norm(c):
    c = c.strip().rstrip('.')
    m = re.match(r'^((?:[1-4]\s)?[A-Za-z]+)\.?,?\s+(\d.*)$', c)
    if not m or m.group(1) not in BOOK: raise ValueError('unmapped citation: ' + repr(c))
    return BOOK[m.group(1)] + ' ' + m.group(2).replace(' et ', ', ')


def fixname(n):
    n = re.sub(r'\s+[IVX]+\.\s+of\s+[A-Za-z]+$', '', n).strip()
    if re.match(r'^(January|February|March|April|May|June|July|August|September|October|November|December) \d+$', n):
        n = 'Feria (' + n + ')'
    return NAMEFIX.get(n, n)


def ef_day(date):
    first = parse_mass(run_missa(date))
    masses = [first]
    if first['n_masses'] > 1:
        masses = [parse_mass(run_missa(date, n)) for n in range(1, first['n_masses'] + 1)]
    name, _, rk = first['title'].partition(' ~ ')
    m = re.search(r'\b(I{1,3}|IV)\.\s*classis', rk)
    if not m: raise ValueError(f'{date}: no class in title {first["title"]!r}')
    if not first['lessons'] or not first['gospel']: raise ValueError(f'{date}: missing readings in {first["title"]!r}')
    e = {'name': fixname(name), 'rank': RANK[m.group(1)], 'octave': 'Octav' in rk,
         'epistle': [norm(x) for x in first['lessons']], 'gospel': norm(first['gospel'])}
    if len(masses) > 1:
        e['masses'] = []
        for ms in masses:
            if not ms['lessons'] or not ms['gospel']: raise ValueError(f'{date}: Mass missing readings')
            e['masses'].append({'name': fixname(ms['title'].partition(' ~ ')[0]),
                                'epistle': [norm(x) for x in ms['lessons']], 'gospel': norm(ms['gospel'])})
    return date.isoformat(), e


def ef_safe(date):
    try: return ef_day(date)
    except Exception as ex: return date.isoformat(), {'error': f'{type(ex).__name__}: {ex}'}


def of_day(cra_dir, date):
    k = f'{date.year}/{date:%m-%d}'
    pc = os.path.join(cra_dir, 'liturgical-calendar', k + '.json'); pr = os.path.join(cra_dir, 'readings', k + '.json')
    if not (os.path.exists(pc) and os.path.exists(pr)): return None
    c = json.load(open(pc, encoding='utf-8')); r = json.load(open(pr, encoding='utf-8'))['readings']
    if not r.get('firstReading') or not r.get('gospel') or not c['celebration'].get('name'): return None
    cl = lambda x: re.sub(r'\.$', '', x.strip())
    rd = [['First reading', cl(r['firstReading'])]]
    if r.get('psalm'): rd.append(['Psalm', cl(r['psalm'])])
    if r.get('secondReading'): rd.append(['Second reading', cl(r['secondReading'])])
    rd.append(['Gospel', cl(r['gospel'])])
    return {'name': c['celebration']['name'], 'rank': TYPE[c['celebration']['type']], 'season': c.get('season'), 'readings': rd}


def clone(url, dest):
    subprocess.run(['git', 'clone', '--depth', '1', '--quiet', url, dest], check=True)


def main():
    ap = argparse.ArgumentParser()
    today = datetime.date.today()
    ap.add_argument('--start', default=(today - datetime.timedelta(days=30)).isoformat())
    ap.add_argument('--end', default=f'{today.year + 1}-12-31')
    ap.add_argument('--do-dir'); ap.add_argument('--cra-dir')
    ap.add_argument('--out', default=os.path.join(os.path.dirname(__file__), '..', 'data', 'liturgy.json'))
    ap.add_argument('--keep-days', type=int, default=60, help='keep existing entries this far before today')
    ap.add_argument('--jobs', type=int, default=8)
    a = ap.parse_args()
    start, end = datetime.date.fromisoformat(a.start), datetime.date.fromisoformat(a.end)
    tmp = tempfile.mkdtemp()
    do_dir = a.do_dir or os.path.join(tmp, 'do'); cra_dir = a.cra_dir or os.path.join(tmp, 'cra')
    if not os.path.isdir(do_dir): clone(DO_URL, do_dir)
    if not os.path.isdir(cra_dir): clone(CRA_URL, cra_dir)
    existing = json.load(open(a.out, encoding='utf-8')) if os.path.exists(a.out) else {}
    days = [start + datetime.timedelta(i) for i in range((end - start).days + 1)]
    with Pool(a.jobs, initializer=init, initargs=(do_dir,)) as p:
        ef = dict(p.map(ef_safe, days))
    errors = {k: v['error'] for k, v in ef.items() if 'error' in v}
    if errors:
        for k, v in sorted(errors.items())[:20]: print('ERROR', k, v, file=sys.stderr)
        print(f'{len(errors)} traditional-calendar days failed; data file not changed', file=sys.stderr); sys.exit(1)
    cutoff = (today - datetime.timedelta(days=a.keep_days)).isoformat()
    out = {k: v for k, v in existing.items() if cutoff <= k < start.isoformat()}
    gaps = []
    for d in days:
        k = d.isoformat()
        of = of_day(cra_dir, d) or existing.get(k, {}).get('of')
        entry = {'ef': ef[k]}
        if of: entry['of'] = of
        else: gaps.append(k)
        out[k] = entry
    out = dict(sorted(out.items()))
    new_text = json.dumps(out, ensure_ascii=False, separators=(',', ':'))
    old_text = open(a.out, encoding='utf-8').read() if os.path.exists(a.out) else ''
    if new_text != old_text:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        open(a.out, 'w', encoding='utf-8').write(new_text)
    print(f'{len(out)} days in file ({min(out)} to {max(out)}); 1969 side missing for {len(gaps)} days'
          + (f' (first gap {gaps[0]}, last {gaps[-1]})' if gaps else ''))
    print('changed' if new_text != old_text else 'unchanged')


if __name__ == '__main__':
    main()
