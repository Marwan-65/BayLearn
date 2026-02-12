from fastapi import FastAPI
# we use dotenv to load environment variables from a .env file
# this should be done before importing any other modules that might use those environment variables
from dotenv import load_dotenv
load_dotenv(".env")
from routes import base
app = FastAPI()
# this for telling the app to use the routes defined in base.py
app.include_router(base.base_router)
