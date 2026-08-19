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
#   ↓
# decompose_invention
#   ↓
# create_invention_pdf
#   ↓
# END

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.memory import InMemoryStore
from langgraph.types import RetryPolicy

from graph.nodes import create_invention_pdf, decompose_invention, generate_keywords, lookup_cpc, create_client_report
from services.state import PatentState


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
    builder = StateGraph(
        PatentState,
    )
    builder.add_node("decompose_invention", decompose_invention)
    # builder.add_node("create_invention_pdf", create_invention_pdf)
    builder.add_node("generate_keywords", generate_keywords)
    builder.add_node("lookup_cpc", lookup_cpc)
    builder.add_node("create_client_report", create_client_report)

    builder.add_edge(START, "decompose_invention")
    # builder.add_edge("decompose_invention", "create_invention_pdf")
    builder.add_edge("decompose_invention", "generate_keywords")
    builder.add_edge("generate_keywords", "lookup_cpc")
    builder.add_edge("lookup_cpc", "create_client_report")
    builder.add_edge("create_client_report", END)
    graph = builder.compile(checkpointer=checkpointer, store=store)

    return graph
