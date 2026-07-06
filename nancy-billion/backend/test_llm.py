from llm import llm_backend
import asyncio

async def test():
    result = await llm_backend.generate('Hello, how are you?', max_tokens=50)
    print('LLM Response:', result)

asyncio.run(test())