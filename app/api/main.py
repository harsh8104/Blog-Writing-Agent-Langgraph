from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(title="Blog Writer API")
app.include_router(router)
