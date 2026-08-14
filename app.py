"""
/**
* ? Author: Gautam
* ? Date: 2026-02-20
* ? Description:  this file is responsible for bootstrapping the application by initializing the necessary components and creating the application context. It sets up the LLM, embeddings, vector store, runtime, checkpointer, graph, and audit service based on the provided settings. The ApplicationBootstrap class provides a build method that returns an instance of ApplicationContext containing all the initialized components.
* ? Usage:  This is the entry point for the agent application.


* * My method
* ! remove this code
* ? what is this?
* TODO: add something here
* @param myparam input
*/
"""

from contextlib import asynccontextmanager

# from xxlimited import Str
from fastapi import FastAPI, Request
from httpcore import request

from bootstrap.bootstrap import ApplicationBootstrap
from config import config
from config.config import PredictRequest
from services import state


@asynccontextmanager
async def lifespan(app: FastAPI):

    app.state.context = ApplicationBootstrap.build()
    print(app.state.context.graph)
    yield


app = FastAPI(title="LLM Service", version="1.0", lifespan=lifespan)


@app.get("/health")
async def health():

    return {"status": "UP"}


@app.post("/predict")
# async def predict(request: Request, body: PredictRequest):
async def predict(request: Request, body: PredictRequest):
    try:
        print(f"Print 1: {body}")
        context = request.app.state.context
        print(f"Print 2: {body}")
        state = {
            "question": body.question,
            "session_id": body.session_id,
            "answer": None,
        }
        print(f"Print 3: {body}")
        result = state  # Placeholder for the actual prediction logic using the context and state.
        config = {
            "configurable": {"thread_id": body.session_id},
            "context": app.state.context,
        }

        result = request.app.state.context.graph.invoke(state, config=config)
        return result
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise


"""
/**

* ? additional information regarding how to start & and use this on local
uvicorn app:app --reload --port 8000 #-- to start the server

* ? single line curl command to test the endpoint
curl -X POST http://127.0.0.1:8000/predict -H "Content-Type: application/json" -d "{\"question\":\"What is LangGraph?\",\"session_id\":\"ABC123\"}"

* ? muliti line curl command to test the endpoint
curl -X POST http://127.0.0.1:8000/predict ^
-H "Content-Type: application/json" ^
-d "{\"question\":\"What is LangGraph?\",\"session_id\":\"ABC123\"}"

"""
