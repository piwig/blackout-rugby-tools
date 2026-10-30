"""Verify deployed private managers. Read credentials from stdin; never print secrets."""
import json,sys,urllib.request,urllib.error
base=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:3042'
credentials=json.load(sys.stdin)
def request(path,cookie='',body=None,csrf=''):
    headers={'Origin':'https://brt.bordebat.fr'}
    if cookie:headers['Cookie']=cookie
    if csrf:headers['X-CSRF-Token']=csrf
    if body is not None:headers['Content-Type']='application/json'
    return urllib.request.urlopen(urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers),timeout=30)
with request('/api/health') as response:assert json.load(response)['version']=='2.0.0'
states={}
for key in ('app','franck'):
    account=credentials[key]
    with request('/api/login',body={k:account[k] for k in ('username','password')}) as response:
        cookie=response.headers['Set-Cookie'];login=json.load(response)
        assert all(flag in cookie.lower() for flag in ('secure','httponly','samesite=strict'))
        cookie=cookie.split(';')[0]
    with request('/api/state',cookie) as response:
        state=json.load(response);states[key]=state
        assert state['user']['username']==account['username']
        assert response.headers['Cache-Control']=='no-store'
    if key=='franck':
        assert len(state['classic_account']['team_ids'])==6
        assert len(state['academy'])==23 and len(state['squad'])==27
        assert len(state['matches'])>=1
        try:request('/api/admin/users',cookie);raise AssertionError('Manager accessed admin')
        except urllib.error.HTTPError as error:assert error.code==403
    else:
        assert state['user']['admin']
        assert not {'72450','72444'} & {t['id'] for t in state['teams']}
    with request('/api/export',cookie) as response:
        export=json.load(response)
        assert 'api_manager' not in json.dumps(export) and 'api_developer' not in json.dumps(export)
    with request('/api/logout',cookie,{},login['csrf']) as response:assert response.status==200
    try:request('/api/state',cookie);raise AssertionError('Session still valid after logout')
    except urllib.error.HTTPError as error:assert error.code==401
try:request('/api/export');raise AssertionError('Anonymous export allowed')
except urllib.error.HTTPError as error:assert error.code==401
assert not ({t['id'] for t in states['app']['teams']} & {t['id'] for t in states['franck']['teams']})
print('Version 2, both logins, isolated clubs, 6-team import, data, secure cookies, exports, admin permissions and logout: OK')
