from app import create_app
import json

def test_hybrid_knowledge():
    app = create_app()
    with app.test_client() as client:
        # Test a real-time query that should trigger web search
        print("--- Testing Web Search Query ---")
        response = client.post("/chat", json={"message": "What is the current population of Sargodha?"})
        data = response.get_json()
        print(f"Reply: {data.get('reply')[:200]}...")
        
        # Test a query that might be in RAG (if user uploaded something)
        # For now, just checking it doesn't crash on general chat
        print("\n--- Testing General Chat ---")
        response = client.post("/chat", json={"message": "Hello, how are you?"})
        data = response.get_json()
        print(f"Reply: {data.get('reply')}")

if __name__ == "__main__":
    test_hybrid_knowledge()
