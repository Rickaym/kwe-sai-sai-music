from spotipy import Spotify
from functools import partial

class AsyncSpotify(Spotify):
    def __init__(self, loop, auth=None, requests_session=True, client_credentials_manager=None, oauth_manager=None, auth_manager=None, proxies=None, requests_timeout=5, status_forcelist=None, retries=..., status_retries=..., backoff_factor=0.3, language=None):
        super().__init__(auth, requests_session, client_credentials_manager, oauth_manager, auth_manager, proxies, requests_timeout, status_forcelist, retries, status_retries, backoff_factor, language)
        self._loop = loop

    def __getattribute__(self, __name: str):
        if __name.startswith("async_"):
            func = super().__getattribute__(__name[6:])
            if callable(func):
                async def async_function(*args, **kwargs):
                    return await self._loop.run_in_executor(None, partial(func, *args, **kwargs))
                return async_function
        return super().__getattribute__(__name)
