"""
/**
* ? Author: Gautam
* ? Date: 2026-02-20
* ? Description: file builds the graph for the application, defining the nodes, edges, and retry policies. It sets up the state graph
* ? with local and network nodes, conditional routing, and parallel routing. The build_graph function compiles the graph and returns it
* ? for use in the application.
* ? Usage:  The ApplicationBootstrap calls the build_graph function to create the graph for the application and stores it in the ApplicationContext.
*/
"""


# START
#   │
#   ▼
# Intent Router
#   │
#   ├─────────────► Fast Route
#   │
#   └─────────────► LLM Intent Router
#                         │
#                         ▼
#                   RAG Decision
#                         │
#                         ▼
#                  Send API Fan-Out
#                  ┌───────────────┐
#                  ▼               ▼
#           Account Lookup    RAG Lookup
#                  │               │
#                  └───────┬───────┘
#                          ▼
#                    Billing Agent
#                          │
#                          ▼
#                         END

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.memory import InMemoryStore
from langgraph.types import RetryPolicy

import graph.nodes as nodes
from services.state import GraphState


def build_graph():

    # 1. Define standard retry policies for network-dependent nodes

    # This policy retries up to 3 times, waiting longer between each try (2s, 4s, 8s)
    api_retry_policy = RetryPolicy(
        max_attempts=3,
        backoff_factor=2.0,
        initial_interval=1.0,
        jitter=True,  # Adds randomness to prevent hitting APIs at the exact same millisecond
    )

    # 2. Checkpointer and Store Setup
    checkpointer = MemorySaver()

    # for production
    # from langgraph.checkpoint.postgres import PostgresSaver
    # checkpointer = PostgresSaver.from_conn_string(
    #     CONNECTION_STRING
    # )

    # 3. Store

    store = InMemoryStore()

    # production
    # from langgraph.store.postgres import PostgresStore

    # 2. Initialize your graph builder
    builder = StateGraph(GraphState)

    # --- LOCAL / LOGICAL NODES (No Retries Needed) ---
    # These run instant, local Python logic. If they fail, it's a bug, not a network glitch.
    builder.add_node("fast_intent_router", nodes.fast_intent_router)
    # builder.add_node("rag_decision", rag_decision_node)

    # --- NETWORK / LLM NODES (Retries Applied) ---
    # This node calls an external LLM to determine intent
    builder.add_node(
        "llm_intent_router", nodes.llm_intent_router, retry=api_retry_policy
    )

    # # This node queries your central database/CRM
    # builder.add_node("account_lookup", account_lookup_node, retry=api_retry_policy)

    # # This node queries your production vector database (e.g., Pinecone, Qdrant)
    # builder.add_node("rag_lookup", rag_lookup_node, retry=api_retry_policy)

    # # This node runs your core LLM structured output generation
    # builder.add_node("billing_agent", billing_agent_node, retry=api_retry_policy)

    # # 15. Conditional Routing

    # builder.add_conditional_edges(
    #     "intent_router",
    #     route_after_intent,
    #     {"fast_path": "rag_decision", "llm_intent_router": "llm_intent_router"},
    # )

    # # 16. Parallel Routing

    # builder.add_conditional_edges("rag_decision", parallel_router)

    # # 17. Final Edges

    builder.add_edge(START, "fast_intent_router")
    # builder.add_edge("account_lookup", "billing_agent")
    builder.add_edge("fast_intent_router", "llm_intent_router")
    # builder.add_edge("rag_lookup", "billing_agent")

    # builder.add_edge("billing_agent", END)
    builder.add_edge("llm_intent_router", END)

    graph = builder.compile(checkpointer=checkpointer, store=store)

    return graph
