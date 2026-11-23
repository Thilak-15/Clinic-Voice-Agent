"""Start the server:  python main.py"""

import uvicorn

from app import config

if __name__ == "__main__":
    uvicorn.run("app.server:app", host=config.HOST, port=config.PORT)
