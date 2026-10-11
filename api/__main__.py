from api.config import settings
import uvicorn

if __name__ == "__main__":
    uvicorn.run("api.main:app", host=settings.host, port=settings.port, reload=False)
