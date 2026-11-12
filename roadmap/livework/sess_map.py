import json, sys, os, collections
# usage: sess_map.py <list_sessions dump> ; merges into sess_map.json
M = os.path.dirname(os.path.abspath(__file__)) + '/sess_map.json'
t = open(sys.argv[1]).read()
i = t.index('{"ccr"')
d, _ = json.JSONDecoder().raw_decode(t[i:])
c = d['ccr']
m = json.load(open(M)) if os.path.exists(M) else {}
for s in c['data']:
    m[s['id']] = {'title': s.get('title', ''), 'status': s.get('session_status', ''), 'bucket': s.get('status_bucket', ''),
                  'created': s.get('created_at', ''), 'tags': s.get('tags', [])}
json.dump(m, open(M, 'w'))
print('page', len(c['data']), 'total', len(m), 'last_id', c.get('last_id'), 'has_more', c.get('has_more'))
print(collections.Counter(v['status'] for v in m.values()))
print('oldest', min(v['created'] for v in m.values()))
