
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from routes.auth import routes as auth_router


app=FastAPI()
app.include_router(auth_router)
@app.get('/')
async def root():
    return {
        "message":"api run"
    }
'''
templates=Jinja2Templates(directory="templates")

app.mount("/static",StaticFiles(directory="static"),name='static')
'''