# class AsyncMCPLogger:
#     def __init__(self):
#         self._fallback_db_uri = os.getenv(
#             "DB_URI", "postgresql://user:password@localhost:5432/langgraph_db"
#         )
#         self._mcp_client = None

#     async def init_client(self) -> MultiServerMCPClient:
#         """Call this once during app startup."""
#         if self._mcp_client is not None:
#             return self._mcp_client

#         self._mcp_client = MultiServerMCPClient(
#             {
#                 "logger_server": {
#                     "transport": "stdio",
#                     "command": "python",
#                     "args": ["/app/logging_server.py"],
#                     "env": {"DB_URI": self._fallback_db_uri},
#                 }
#             },
#             handle_tool_errors=True,
#         )
#         await self._mcp_client.__aenter__()
#         logger.info("MCP Logging Client started successfully.")
#         return self._mcp_client

#     async def close_client(self):
#         """Call this once during app shutdown."""
#         if self._mcp_client:
#             await self._mcp_client.__aexit__(None, None, None)
#             self._mcp_client = None
#             logger.info("MCP Logging Client closed safely.")

#     async def log_async(self, log_type: str, message: str, details: dict = None):
#         """Main non-blocking async logger."""
#         if details is None:
#             details = {}

#         try:
#             client = await self.init_client()
#             tool_payload = {
#                 "log_type": log_type,
#                 "message": message,
#                 "details": details,
#             }

#             result = await client.ainvoke("log_event", tool_payload)

#             if "success" not in str(result):
#                 logger.warning(
#                     f"MCP server rejected log layout. Invoking fallback. Result: {result}"
#                 )
#                 await self._log_to_postgresql_direct_async(log_type, message, details)
#                 return

#         except Exception as e:
#             logger.error(
#                 f"Error invoking FastMCP tool: {e}. Falling back to direct database."
#             )
#             await self._log_to_postgresql_direct_async(log_type, message, details)

#     async def _log_to_postgresql_direct_async(
#         self, log_type: str, message: str, details: dict
#     ):
#         """Async fallback database wrapper."""
#         try:
#             async with await psycopg.AsyncConnection.connect(
#                 self._fallback_db_uri
#             ) as conn:
#                 async with conn.cursor() as cur:
#                     await cur.execute(
#                         "INSERT INTO logs (log_type, message, details) VALUES (%s, %s, %s)",
#                         (log_type, message, json.dumps(details)),
#                     )
#                 await conn.commit()
#         except Exception as e:
#             logger.critical(
#                 f"FATAL PRODUCTION ERROR: Logging fallback failed completely: {e}"
#             )


# # Instantiate a single global instance for the application to import
# mcp_logger = AsyncMCPLogger()


"""
@wrap_tool_call
def tool_error_handler(request, handler):
    try:
        return handler(request)
    except Exception as e:
        error_message = str(e)
        # Log the error to MSSQL
        log_to_mssql(
            log_type="TOOL_ERROR",
            message=f"Tool call failed for {request.tool.name}",
            details={
                "tool_name": request.tool.name,
                "tool_args": request.tool_args,
                "error": error_message,
            },
        )
        return {"error": error_message}


@wrap_model_call
def model_logging(request, handler):
    response = handler(request)
    # Log model invocation to MSSQL
    log_to_mssql(
        log_type="MODEL_INVOCATION",
        message=f"Model {request.model} was invoked.",
        details={
            "model_name": request.model,
            "input": str(request.input),  # Convert input to string for logging
        },
    )
    return response

"""


# Following is the non-class version of the same

# # @title
# import os
# import json
# import logging
# import psycopg  # Keep for local fallback
# from langchain_mcp_adapters.client import MultiServerMCPClient

# # Set up logging for error visibility
# logger = logging.getLogger("mcp_client")

# _fallback_db_uri = os.getenv("DB_URI", "postgresql://user:password@localhost:5432/langgraph_db")

# # A single placeholder for our client instance
# _mcp_client = None

# async def init_mcp_client() -> MultiServerMCPClient:
#     """
#     Initializes and boots up the MultiServerMCPClient connection.
#     In production, call this EXACTLY ONCE during your app's startup hook.
#     """
#     global _mcp_client
#     if _mcp_client is not None:
#         return _mcp_client

#     _mcp_client = MultiServerMCPClient(
#         {
#             "logger_server": {
#                 "transport": "stdio",
#                 "command": "python",
#                 "args": ["/app/logging_server.py"], # Change to your absolute production path
#                 "env": {"DB_URI": _fallback_db_uri}
#             }
#         },
#         handle_tool_errors=True
#     )

#     # Securely open the persistent background process/pipe connection
#     await _mcp_client.__aenter__()
#     logger.info("MCP Logging Client started successfully.")
#     return _mcp_client


# async def close_mcp_client():
#     """
#     Safely shuts down the background server connection.
#     In production, call this EXACTLY ONCE during your app's shutdown hook.
#     """
#     global _mcp_client
#     if _mcp_client:
#         await _mcp_client.__aexit__(None, None, None)
#         _mcp_client = None
#         logger.info("MCP Logging Client closed safely.")


# async def log_to_mssql_async(log_type: str, message: str, details: dict = None):
#     """
#     Production-grade logging tool. Non-blocking and safely async.
#     """
#     if details is None:
#         details = {}

#     try:
#         # Get our running connection
#         client = await init_mcp_client()

#         tool_payload = {
#             "log_type": log_type,
#             "message": message,
#             "details": details
#         }

#         # 'await' lets the web server process other user requests
#         # while waiting for the logging server process to finish writing
#         result = await client.ainvoke("log_event", tool_payload)

#         # Why this structure matters now:
#         # The if block now handles logical failures (the MCP server is alive and talking, but it rejected your payload or
#         # internal database save failed).
#         # The except block handles runtime/infrastructure failures (the MCP server crashed, the pipe broke, or the code
#         # timed out trying to talk to it).

#         if "success" not in str(result):
#             logger.warning(f"MCP server rejected log layout. Invoking fallback. Result: {result}")
#             await _log_to_postgresql_direct_async(log_type, message, details)
#             return

#     except Exception as e:
#         logger.error(f"Error invoking FastMCP tool: {e}. Falling back to direct database.")
#         await _log_to_postgresql_direct_async(log_type, message, details)


# async def _log_to_postgresql_direct_async(log_type: str, message: str, details: dict = None):
#     """Asynchronous direct database fallback for high-throughput protection."""
#     try:
#         # psycopg3 supports native async out-of-the-box
#         async with await psycopg.AsyncConnection.connect(_fallback_db_uri) as conn:
#             async with conn.cursor() as cur:
#                 await cur.execute(
#                     """
#                     CREATE TABLE IF NOT EXISTS logs (
#                         id SERIAL PRIMARY KEY,
#                         log_type VARCHAR(255) NOT NULL,
#                         message TEXT NOT NULL,
#                         details JSONB,
#                         timestamp TIMESTAMPTZ DEFAULT NOW()
#                     );
#                     """
#                 )

#                 details_json = json.dumps(details) if details is not None else None
#                 await cur.execute(
#                     "INSERT INTO logs (log_type, message, details) VALUES (%s, %s, %s)",
#                     (log_type, message, details_json)
#                 )
#             await conn.commit()
#     except Exception as e:
#         logger.critical(f"FATAL PRODUCTION ERROR: Logging fallback failed completely: {e}")

# 2. ainvoke (Asynchronous Invoke)
# This is a standard method provided by the LangChain MCP adapter framework. The efix "a" stands for Asynchronous, meaning it is designed to be paired with the await keyword.What it does: It sends a specific command (in this case, "log_event") along with data
#   payload (tool_payload) across the pipe to the external MCP server, and waits for a response.Why it is crucial for production: If you used a
#   synchronous (blocking) function to write logs, your entire web application would completely freeze and pause for every single user while
#   waiting for the database write to finish. Because it uses await client.ainvoke(...), Python pauses only this specific logging task, immediately
#   freeing up your web server to handle thousands of other active user requests in the meantime.If you are optimizing your async code, let me know:

# # # Make sure you've saved logging_server.py to this path first!
# # # The `&` runs it in the background, allowing the notebook to continue.
# # !export DB_URI="{DB_URI}" && python /content/drive/MyDrive/logging_server.py &

# # print("MCP Logger Server started in the background. Check logs for output."

# """

# Here is the short answer: Writing async def only gives a function the ability to pause and release resources. The await keyword is the actual trigger
# that tells Python to pause right now and switch tasks

# When you define a function with async def, you aren't writing a normal function anymore. You are creating a Coroutine.

# async def fetch_data():
#     return "Data ready!"

# # If you call it like a normal function:
# result = fetch_data()
# print(result)
# # Output: <coroutine object fetch_data at 0x102...>

# Notice that it didn't return "Data ready!". It returned a Coroutine object. An async def function does absolutely nothing when called; it just
# packages up your code into a box (the coroutine object) and waits.To open the box and actually execute the code inside, you must use await.

# Why doesn't Python just automate this?You might wonder: "If it's inside an async function, why can't Python just assume every line should release resources automatically?"There are two major reasons why explicit await syntax is required:1. Explicit Yield Points (The "Cooperative" Rule)Python uses Cooperative Multitasking. This means the Event Loop cannot forcibly rip control away from a running function. The function must voluntarily surrender control.The await keyword is a visible, explicit marker that says: "I am about to do something slow (like a database read). Event Loop, you may pause me here and run other code while I wait."Without await, Python has no idea which lines are slow network calls and which lines are fast CPU calculations.2. Running Tasks in ParallelBecause async def functions don't run automatically, you gain the superpower to schedule multiple things to happen at the exact same time before waiting for them.If Python automatically awaited everything, your code would run sequentially (one after the other). Because it doesn't, you can do this:pythonasync def download_all():
#     # Calling these creates the coroutine boxes, but does NOT start them yet
#     task1 = download_file_A()
#     task2 = download_file_B()
#     task3 = download_file_C()

#     # Now, we fire all three into the background loop simultaneously
#     # and await their collective finish!
#     results = await asyncio.gather(task1, task2, task3)
# Use code with caution.If await wasn't an explicit keyword, you could never group tasks together like this to speed up your code


# Why this structure prevents runtime bugs:Persistent Server Process: Instead of querying get_tools() into a disconnected variable, this script
# calls __aenter__() directly inside a persistent background event loop (_loop). The Python background subprocess stays open and listening.Direct
# Client Invocation: It utilizes _mcp_client.ainvoke("log_event", ...) instead of breaking apart the tool object. This allows LangChain's adapter to
#  parse and route the schema conversion cleanly to FastMCP.No Closed Loop Exceptions: It maps all future async actions directly back into the
#  safe _loop.run_until_complete(), preventing the script from crashing when called sequentially across different cells in notebooks like Google Colab.


# """

# from fastapi import FastAPI
# from contextlib import asynccontextmanager
# from your_utils_file import init_mcp_client, close_mcp_client, log_to_mssql_async

# @asynccontextmanager
# async def app_lifespan(app: FastAPI):
#     # 1. Boot up the MCP background server process cleanly on server start
#     await init_mcp_client()
#     yield
#     # 2. Kill the subprocess and release RAM cleanly when the server stops
#     await close_mcp_client()

# app = FastAPI(lifespan=app_lifespan)

# @app.post("/do_something")
# async def execute_task():
#     # ... your logic ...

#     # 3. Log data completely out of the way without blocking any other network traffic
#     await log_to_mssql_async("info", "Task processed smoothly", {"user_id": 42})
#     return {"status": "complete"}

# adad

# ass
