import asyncio
import os
from finbot.config import settings
import resend

def test():
    print(f"--- DIAGNOSTIC START ---")
    print(f"Provider: {settings.EMAIL_PROVIDER}")
    print(f"From Address: {settings.EMAIL_FROM_ADDRESS}")
    
    resend.api_key = settings.RESEND_API_KEY
    
    try:
        params = {
            "from": f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM_ADDRESS}>",
            "to": ["noriko@gmail.com"], # Ensure this matches your Resend login email if not verified
            "subject": "Diagnostic Test",
            "html": "<strong>It works!</strong>"
        }
        r = resend.Emails.send(params)
        print(f"RESULT: SUCCESS")
        print(f"RESPONSE: {r}")
    except Exception as e:
        print(f"RESULT: FAILED")
        print(f"ERROR TYPE: {type(e).__name__}")
        print(f"ERROR MESSAGE: {str(e)}")

if __name__ == "__main__":
    test()
