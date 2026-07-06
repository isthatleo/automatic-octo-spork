from llm import llm_backend
import asyncio

async def test():
    result = await llm_backend.generate('Hello, how are you?', max_tokens=50)
    # Convert to ASCII safe string for display
    ascii_result = ''.join(c for c in result if ord(c) < 128)
    print('LLM Response (ASCII safe):', ascii_result)
    print('Response length:', len(result), 'characters')
    print('Response preview:', ascii_result[:100])

asyncio.run(test())