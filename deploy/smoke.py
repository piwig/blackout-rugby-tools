"""Check the running service over loopback. Password is read from stdin, never logged."""
import json,sys,urllib.request,urllib.error

base='http://127.0.0.1:3042'
credentials=json.load(sys.stdin)['app']
request=urllib.request.Request(base+'/api/login',data=json.dumps(credentials).encode(),headers={'Content-Type':'application/json','Origin':'https://brt.bordebat.fr'})
with urllib.request.urlopen(request) as response:
    cookie=response.headers['Set-Cookie'];doc=json.load(response)
    assert all(flag in cookie.lower() for flag in ('secure','httponly','samesite=strict'))
with urllib.request.urlopen(urllib.request.Request(base+'/api/state',headers={'Cookie':cookie.split(';')[0]})) as response:
    state=json.load(response)
    assert len(state['academy'])==23 and len(state['squad'])==27
    assert state['settings']['developer_ready'] and state['settings']['manager_ready']
    assert len(state['matches'])>=1
    assert response.headers['Cache-Control']=='no-store'
try:
    urllib.request.urlopen(base+'/api/export')
    raise AssertionError('Unauthenticated export must be refused')
except urllib.error.HTTPError as error:assert error.code==401
logout=urllib.request.Request(base+'/api/logout',data=b'{}',headers={'Content-Type':'application/json','Cookie':cookie.split(';')[0],'X-CSRF-Token':doc['csrf']})
with urllib.request.urlopen(logout) as response:assert response.status==200
print('Production login, secure cookie, actual datasets, protected export and logout: OK')
