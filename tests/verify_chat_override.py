import requests
import json
import sys

BASE_URL = "http://localhost:8001"
SESSION_ID = "test-session-override"

def test_chat_model_override():
    print(f"Testing POST {BASE_URL}/chat with model override...")
    payload = {
        "session_id": SESSION_ID,
        "message": "Qual modelo é você?",
        "model_override": "gemini-3-flash-preview"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/chat", json=payload)
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Chat response received.")
            print(f"   Model: {data['model']}")
            print(f"   Reply: {data['reply']}")
            
            if "gemini-3-flash-preview" in data['model']:
                print("✅ Model override confirmed in response.")
            else:
                print(f"⚠️ Model match warning: Expected 'gemini-3-flash-preview', got {data['model']}")
        else:
            print(f"❌ Chat request failed. Status: {response.status_code}")
            print(f"   Response: {response.text}")
            sys.exit(1)

    except Exception as e:
        print(f"❌ Error in chat request: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_chat_model_override()
