"""Verify deployed private managers. Read credentials from stdin; never print secrets."""
import json,sys,httpx
base=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:3042'
credentials=json.load(sys.stdin)
def request(path,cookie='',body=None,csrf=''):
    headers={'Origin':'https://brt.bordebat.fr'}
    if cookie:headers['Cookie']=cookie
    if csrf:headers['X-CSRF-Token']=csrf
    response=httpx.request('POST' if body is not None else 'GET',base+path,json=body,headers=headers,timeout=30)
    response.raise_for_status()
    return response
assert request('/api/health').json()['version']=='2.0.0'
states={}
for key in ('app','franck'):
    account=credentials[key]
    response=request('/api/login',body={k:account[k] for k in ('username','password')})
    cookie=response.headers['Set-Cookie'];login=response.json()
    assert all(flag in cookie.lower() for flag in ('secure','httponly','samesite=strict'))
    cookie=cookie.split(';')[0]
    response=request('/api/state',cookie);state=response.json();states[key]=state
    assert state['user']['username']==account['username']
    assert response.headers['Cache-Control']=='no-store'
    if key=='franck':
        assert len(state['classic_account']['team_ids'])==6
        assert len(state['academy'])==23 and len(state['squad'])==27
        assert len(state['matches'])>=1
        try:request('/api/admin/users',cookie);raise AssertionError('Manager accessed admin')
        except httpx.HTTPStatusError as error:assert error.response.status_code==403
    else:
        assert state['user']['admin']
        assert not {'72450','72444'} & {t['id'] for t in state['teams']}
    export=request('/api/export',cookie).json()
    assert 'api_manager' not in json.dumps(export) and 'api_developer' not in json.dumps(export)
    assert request('/api/logout',cookie,{},login['csrf']).status_code==200
    try:request('/api/state',cookie);raise AssertionError('Session still valid after logout')
    except httpx.HTTPStatusError as error:assert error.response.status_code==401
try:request('/api/export');raise AssertionError('Anonymous export allowed')
except httpx.HTTPStatusError as error:assert error.response.status_code==401
assert not ({t['id'] for t in states['app']['teams']} & {t['id'] for t in states['franck']['teams']})
print('Version 2, both logins, isolated clubs, 6-team import, data, secure cookies, exports, admin permissions and logout: OK')
