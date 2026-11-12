import json, sys, os
# usage: pulls_add.py <list_pull_requests dump> ; merges rows into pulls.json keyed by number
M = os.path.dirname(os.path.abspath(__file__)) + '/pulls.json'
t = open(sys.argv[1]).read()
rows = json.loads(t[t.index('['):])
m = json.load(open(M)) if os.path.exists(M) else {}
for r in rows:
    m[str(r['number'])] = {'number': r['number'], 'title': r.get('title', ''), 'draft': bool(r.get('draft')),
                           'branch': (r.get('head') or {}).get('ref'), 'head': (r.get('head') or {}).get('sha'),
                           'createdAt': r.get('created_at'), 'body': r.get('body') or ''}
json.dump(m, open(M, 'w'))
print('page', len(rows), 'total', len(m), 'oldest', min(v['createdAt'] for v in m.values()), 'drafts', sum(v['draft'] for v in m.values()))
