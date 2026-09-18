from dotenv import load_dotenv
load_dotenv()

from freeflow_llm import FreeFlowClient

with FreeFlowClient() as client:
    response = client.chat(
        messages=[{"role": "user", "content": "قل مرحبا"}]
    )
    print(response.content)
    print("المزود:", response.provider)