"""Bound request bodies before JSON and multipart parsers allocate resources."""
from starlette.responses import JSONResponse


class RequestSizeLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        limit = 6 * 1024 * 1024 if scope["path"] == "/api/share/upload" else 256 * 1024
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            await JSONResponse({"detail": "Некорректный размер запроса"}, status_code=400)(scope, receive, send)
            return
        if declared > limit:
            await JSONResponse({"detail": "Слишком большой запрос"}, status_code=413)(scope, receive, send)
            return
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > limit:
                await JSONResponse({"detail": "Слишком большой запрос"}, status_code=413)(scope, receive, send)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
