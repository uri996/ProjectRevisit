from fastapi import HTTPException


class RequestSizeLimit:
    """Bound the actual received body, including requests without Content-Length."""

    def __init__(self, app, limit=12 * 1024 * 1024):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            return await self.app(scope, receive, send)
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > self.limit:
                raise HTTPException(413, "请求超过 12 MB 限制。")
            return message

        await self.app(scope, limited_receive, send)
