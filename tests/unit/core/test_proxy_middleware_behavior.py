import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

def create_test_app(trusted_hosts):
    app = FastAPI()
    
    @app.get("/ip")
    def get_ip(request: Request):
        return {"client_ip": request.client.host}
        
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=trusted_hosts)
    return app

@pytest.mark.parametrize("trusted_hosts, peer_ip, x_forwarded_for, expected_ip", [
    # When unset, we pass ["*"], so ANY peer is trusted to provide X-Forwarded-For
    (["*"], "192.168.1.100", "8.8.8.8", "8.8.8.8"),
    
    # When set to specific IPs, only those peers can provide X-Forwarded-For
    (["10.0.0.1"], "10.0.0.1", "8.8.8.8", "8.8.8.8"),
    
    # Negative Branch: A peer NOT in the trusted list tries to spoof IP
    (["10.0.0.1"], "192.168.1.100", "8.8.8.8", "192.168.1.100"),
])
def test_proxy_middleware_spoofing_behavior(trusted_hosts, peer_ip, x_forwarded_for, expected_ip):
    """
    Assert that X-Forwarded-For from a non-listed peer doesn't influence the application's
    perceived client_ip when strict trusted hosts are configured.
    """
    app = create_test_app(trusted_hosts)
    
    # We must explicitly set the client IP on the TestClient to simulate the physical peer IP
    # that Uvicorn would see on the TCP socket.
    with TestClient(app, client=(peer_ip, 12345)) as client:
        response = client.get("/ip", headers={"X-Forwarded-For": x_forwarded_for})
        assert response.status_code == 200
        assert response.json()["client_ip"] == expected_ip
