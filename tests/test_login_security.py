from fastapi.testclient import TestClient
from server.main import create_app


def test_success_does_not_erase_ip_admission_history(tmp_path):
    app=create_app(tmp_path,'Testing-password-1234',secure=False)
    with TestClient(app) as client:
        for _ in range(8):
            assert client.post('/api/login',json={'username':'victim','password':'wrong'}).status_code==401
        assert client.post('/api/login',json={'username':'piwig','password':'Testing-password-1234'}).status_code==200
        assert client.post('/api/login',json={'username':'victim','password':'wrong'}).status_code==401
        assert client.post('/api/login',json={'username':'victim','password':'wrong'}).status_code==429
    with TestClient(create_app(tmp_path,'Testing-password-1234',secure=False)) as restarted:
        assert restarted.post('/api/login',json={'username':'victim','password':'wrong'}).status_code==429


def test_account_limit_covers_distributed_sources(tmp_path):
    from server.auth_security import consume_login,init_login_security
    from fastapi import HTTPException
    import pytest
    app=create_app(tmp_path,'Testing-password-1234',secure=False)
    accounts=app.state.accounts
    init_login_security(accounts)
    for i in range(30):consume_login(accounts,f'192.0.2.{i}','VICTIM')
    with pytest.raises(HTTPException) as blocked:consume_login(accounts,'192.0.2.250','victim')
    assert blocked.value.status_code==429
    consume_login(accounts,'192.0.2.251','different')


def test_bad_content_length_is_rejected_without_traceback(tmp_path):
    with TestClient(create_app(tmp_path,'Testing-password-1234',secure=False)) as client:
        response=client.post('/api/login',content='{}',headers={'content-length':'nonsense','content-type':'application/json'})
        assert response.status_code==400
