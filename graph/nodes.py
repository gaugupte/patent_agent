"""
/**
* ? Author: Gautam
* ? Date: 2026-02-20
* ? Description:  file has acutually the nodes for the graph, defining the logic for intent routing, RAG decision-making, and parallel execution. It includes functions for fast intent routing, LLM-based intent routing, and conditional routing based on confidence scores. The nodes are designed to be used within the state graph built in graph_builder.py.
* ? Usage:  graph_builder.py imports this file to access the node functions when constructing the state graph for the application.
*/
"""

from inspect import currentframe

from langchain_core.runnables import RunnableConfig

from config.config import ApplicationContext, Settings
from services.state import GraphState, IntentResult


# 1. intent router
def fast_intent_router(state: GraphState):
    # retuns if billing or account intent is detected, otherwise returns unknown intent
    q = state.get("question", "").lower()
    BILLING_WORDS = {
        "billing",
        "invoice",
        "payment",
        "charge",
        "refund",
        "subscription",
    }
    ACCOUNT_WORDS = {"account", "profile", "settings", "preferences"}
    billing_score = sum(word in q for word in BILLING_WORDS)
    account_score = sum(word in q for word in ACCOUNT_WORDS)

    if billing_score > 0:
        return {"intent": "billing", "confidence": min(0.95, 0.7 + billing_score * 0.1)}
    if account_score > 0:
        return {"intent": "account", "confidence": min(0.95, 0.7 + account_score * 0.1)}
    return {"intent": "unknown", "confidence": 0.3}


# 2. Conditional Edge
def route_after_intent(state: GraphState):
    if state["confidence"] >= 0.8:
        return "fast_path"
    return "llm_intent_router"


# 2. Conditional Edge
# def llm_intent_router(state: GraphState, config: RunnableConfig):
#     # 1. Access runtime variables safely from the configurable dictionary
#     configurable = config.get("configurable", {})
#     llm = configurable.get("llm")

#     if not llm:
#         raise ValueError("LLM instance was not passed in the runtime config.")

#     # 2. Force structured JSON output matching your Pydantic schema
#     structured_llm = llm.with_structured_output(IntentResult)

#     # 3. Invoke model and update state
#     result = structured_llm.invoke(state["query"])

#     # Returning a dictionary modifies only these specific keys in the state
#     return {"intent": result.intent, "confidence": result.confidence}


# 2. Conditional Edge
def llm_intent_router(state: GraphState, config: RunnableConfig):

    configurable = config.get("configurable", {})
    context = configurable.get("context")
    thread_id = configurable.get("thread_id")
    audit = context.audit
    llm = context.llm
    if not llm:
        raise ValueError("LLM instance was not passed in the runtime config.")

    # 2. Force structured JSON output matching your Pydantic schema
    structured_llm = llm.with_structured_output(IntentResult)
    import inspect

    # 3. Invoke model and update state
    function_name = inspect.currentframe().f_code.co_name
    result = structured_llm.invoke(state["question"])
    audit.log_model_call(thread_id, function_name, state["question"], result.response)
    print(result.response)
    # Returning a dictionary modifies only these specific keys in the state
    # return {"intent": result.intent, "confidence": result.confidence}
    return {
        "intent": result.intent,
        "confidence": result.confidence,
        "response": result.response,
    }


# # 7. Determine Whether RAG Is Needed
# def rag_decision_node(state: GraphState):
#     rag_terms = ["policy", "refund", "cancel", "charged twice"]
#     user_query = state.get("query", "") or ""
#     requires_rag = any(term in user_query.lower() for term in rag_terms)
#     return {"requires_rag": requires_rag}


# # 8. Parallel Execution Using Send API
# def parallel_router(state: GraphState):
#     # Create an empty list to collect our parallel routing instructions
#     sends = []

#     # 1. Always trigger the account lookup process in parallel
#     # Pass a specific piece of data (e.g., user_id) or a shallow copy of the required fields
#     sends.append(Send("account_lookup", {"query": state["query"]}))

#     # 2. Conditionally trigger the RAG lookup process in parallel
#     if state.get("requires_rag"):
#         sends.append(Send("rag_lookup", {"query": state["query"]}))

#     # Return the list of Send objects to fork the execution graph
#     return sends


# # 9. Account Node

# from langchain_core.runnables import RunnableConfig


# def account_lookup_node(state: GraphState, config: RunnableConfig):
#     # 1. Safely retrieve the tool from the execution context/config
#     tool = config.get("configurable", {}).get("account_tool")

#     if not tool:
#         return {"account_error": "System Configuration Error: account_tool missing."}

#     try:
#         # Try running the tool
#         account_data = tool.invoke(state["query"])
#         return {"account_data": account_data, "account_error": None}

#     except Exception as e:
#         # Catch any API/Database failures and save the error message
#         return {
#             "account_data": None,
#             "account_error": f"Failed to fetch account: {str(e)}",
#         }


# #  from langgraph.prebuilt import RetryPolicy

# # # Retry up to 3 times, waiting longer between each try (exponential backoff)
# # my_retry_policy = RetryPolicy(max_attempts=3, backoff_factor=2.0)

# # # Apply it specifically to your account node
# # builder.add_node(
# #     "account_lookup",
# #     account_lookup_node,
# #     retry=my_retry_policy
# # )

# # 10. RAG Node

# from langchain_core.runnables import RunnableConfig


# def rag_lookup_node(state: GraphState, config: RunnableConfig):
#     # 1. Extract the retriever safely from the LangGraph config context
#     retriever = config.get("configurable", {}).get("retriever")

#     if not retriever:
#         # Graceful error handling if the retriever was forgotten at runtime
#         return {
#             "rag_error": "System Error: Retriever tool is missing from configuration."
#         }

#     try:
#         # 2. Invoke the retriever using the query from the state
#         docs = retriever.invoke(state["query"])

#         # 3. Return ONLY the state update dictionary
#         return {"rag_context": docs, "rag_error": None}

#     except Exception as e:
#         # Catch vector database timeouts or network issues safely
#         return {"rag_context": [], "rag_error": f"RAG Lookup failed: {str(e)}"}


# # 11. Billing Agent


# class BillingResponse(BaseModel):
#     answer: str


# from langchain_core.runnables import RunnableConfig


# def billing_agent_node(state: GraphState, config: RunnableConfig):
#     # 1. Pull the LLM out of the standard LangGraph config
#     llm = config.get("configurable", {}).get("llm")
#     if not llm:
#         return {"response": "System Error: LLM is not configured."}
#     # 2. Attach your structured schema format
#     structured_llm = llm.with_structured_output(BillingResponse)
#     # 3. Build the prompt using data gathered from your parallel steps
#     # We use .get() with fallback values in case a parallel step failed
#     prompt = f""""""
#     Account Data:
#     {state.get("account_data", "No account data available.")}
#     Knowledge:
#     {state.get("rag_context", "No relevant knowledge articles found.")}
#     User:
#     {state.get("query")}
#     """
#     try:
#         # 4. Invoke the model
#         result = structured_llm.invoke(prompt)

#         # 5. Return ONLY the state updates as a dictionary
#         return {"response": result.answer}

#     except Exception as e:
#         return {
#             "response": f"Sorry, I encountered an issue generating your response: {str(e)}"
#         }
