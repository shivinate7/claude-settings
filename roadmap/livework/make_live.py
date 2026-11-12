import json, os, sys
S = os.path.dirname(os.path.abspath(__file__)) + '/'
read_at = sys.argv[1]
pulls = json.load(open(S + 'pulls.json'))
sess = json.load(open(S + 'sess_map.json'))
live = {
    'readAt': read_at,
    'pulls': [{k: v[k] for k in ('number', 'title', 'branch', 'draft', 'createdAt', 'head') if v.get(k) is not None}
              for v in sorted(pulls.values(), key=lambda r: r['number'])],
    'sessions': [{'id': i, 'session_status': s['status'], 'tags': s.get('tags') or [], 'status_bucket': s.get('bucket')}
                 for i, s in sess.items()],
}
json.dump(live, open(S + 'live.json', 'w'))
print('pulls', len(live['pulls']), 'sessions', len(live['sessions']))
