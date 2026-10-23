"""Bound incoming HTTP bodies, including chunked payloads, before JSON decoding."""
from starlette.responses import JSONResponse

class BodyLimitMiddleware:
    def __init__(self, app, max_bytes=65536):
        self.app,self.max_bytes=app,max_bytes

    async def __call__(self, scope, receive, send):
        if scope['type']!='http':
            return await self.app(scope,receive,send)
        async def reject():
            response=JSONResponse(status_code=413,content={'schema_version':'1.0','error':{
                'code':'request_too_large','message':'Request body exceeds configured byte limit'}})
            await response(scope,receive,send)
        lengths=[v for k,v in scope.get('headers',[]) if k.lower()==b'content-length']
        for length in lengths:
            try:
                if int(length)>self.max_bytes: return await reject()
            except ValueError:
                pass  # Server/protocol or JSON validation handles malformed metadata.
        data=bytearray()
        while True:
            message=await receive()
            if message['type']=='http.disconnect': return
            chunk=message.get('body',b'')
            if len(data)+len(chunk)>self.max_bytes: return await reject()
            data.extend(chunk)
            if not message.get('more_body',False): break
        delivered=False
        async def replay():
            nonlocal delivered
            if not delivered:
                delivered=True
                return {'type':'http.request','body':bytes(data),'more_body':False}
            return await receive()
        await self.app(scope,replay,send)
