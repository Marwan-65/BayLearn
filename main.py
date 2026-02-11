from fastapi import FastAPI

app = FastAPI()

@app.get("/welcome")
def Welcome():
    return "Welcome to FastAPI!"
