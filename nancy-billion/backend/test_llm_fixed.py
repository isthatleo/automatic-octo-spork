from llm import llm_backend
import asyncio

async def test():
    result = await llm_backend.generate('Hello, how are you?', max_tokens=50)
    # Encode to ASCII to avoid Unicode display issues
    ascii_result = result.encode('ascii', errors='ignore').decode('ascii')
    print('LLM Response (ASCII):', ascii_result)
    print('Response length:', len(result), 'characters')
    print('Response preview:', result[:100])

asyncio.run(test())