import aiohttp

async def mystBin_upload(output: str, *, content_type: str = "application/json") -> str:
    data = bytes(output, 'utf-8')

    async with aiohttp.ClientSession() as cs:
        async with cs.post('https://mystb.in/documents', data=data) as r:
            res = await r.json(content_type=content_type)
            key = res["key"]

    return f'https://mystb.in/{key}'
