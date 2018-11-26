import pickle

from starlette.endpoints import HTTPEndpoint
from starlette.routing import Route, Router
from starlette.responses import JSONResponse
import uvicorn


class Homepage(HTTPEndpoint):
    async def get(self, request):
        print(request)
        body = await request.json()
        fn = body['fn']
        resp = {'response': fn}

        return JSONResponse(resp)


app = Router([
    Route('/', endpoint=Homepage, methods=['POST']),
])

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=9999, debug=True)
