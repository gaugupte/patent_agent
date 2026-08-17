"""
/**
* ? Author: Gautam
* ? Date: 2026-02-20
* ? Description:  this file is responsible for bootstrapping the application by initializing the necessary components and creating the application context. It sets up the LLM, embeddings, vector store, runtime, checkpointer, graph, and audit service based on the provided settings. The ApplicationBootstrap class provides a build method that returns an instance of ApplicationContext containing all the initialized components.
* ? Usage:  The ApplicationBootstrap class can be used to create an instance of ApplicationContext
*/
"""


## GG: Use following approach of having individual factory methods for each component instead of having a single factory method for the entire application context. This allows for more flexibility and easier testing of individual components.
## when implementation gets complex, we can move the factory methods to separate files and import them here. This will help in keeping the code organized and maintainable.

# from llm.llm_factory import create_llm
# from memory.checkpointer_factory import create_checkpointer
# from runtime.runtime_factory import create_runtime
# from vectorstore.vectorstore_factory import create_vectorstore
# from embeddings.embedding_factory import create_embeddings
# from langchain.agents.middleware import wrap_model_call, wrap_tool_call

from langchain_openai import ChatOpenAI

from config.config import ApplicationContext, Settings
from graph.graph_builder import build_graph
from services.pdf_service import PDFService
from services.utils import AuditService, init_db


def create_llm(settings: Settings):

    # This function should initialize and return an instance of the LLM used in the application.

    # llm = create_llm(settings)
    # llm = llm.with_middleware(model_logging, tool_error_handler)

    print("llm created")
    llm = ChatOpenAI(
        base_url="http://localhost:11434/v1",  # Ollama's default local port
        api_key="ollama",  # Required placeholder string
        model="mistral",  # Matches the model name from step 2
        temperature=0,
    )
    return llm


def create_embeddings(settings: Settings):
    # TODO: Add the actual implementation for creating the embeddings based on the settings.
    # This function should initialize and return an instance of the embeddings used in the application.

    print("Embeddings created")
    return "Embeddings created"


def build_checkpointer(settings: Settings):
    # TODO: Add the actual implementation for building the checkpointer based on the settings.
    # This function should initialize and return an instance of the checkpointer used in the application.

    print("Checkpointer built")
    return "Checkpointer built"


def create_vectorstore(settings: Settings, embeddings: any):
    # TODO: Add the actual implementation for creating the vector store based on the settings and embeddings.
    # This function should initialize and return an instance of the vector store used in the application.

    print("Vector store created")
    return "Vector store created"


def create_runtime(settings: Settings):

    # TODO: Add the actual implementation for creating the runtime based on the settings and embeddings.
    # This function should initialize and return an instance of the runtime used in the application.

    print("Runtime created")
    return "Runtime created"


class ApplicationBootstrap:
    def build() -> ApplicationContext:
        settings = Settings()
        llm = create_llm(settings)
        embeddings = create_embeddings(settings)
        vector_store = create_vectorstore(settings, embeddings)
        # retriever = vector_store.as_retriever()
        runtime = create_runtime(settings)
        checkpointer = build_checkpointer(settings)
        graph = build_graph()
        db_engine = init_db()
        audit = AuditService(db_engine)
        pdf_service = PDFService(output_dir="output")
        return ApplicationContext(
            settings=settings,
            llm=llm,
            embeddings=embeddings,
            vector_store=vector_store,
            retriever="retriever",
            runtime=runtime,
            checkpointer=checkpointer,
            graph=graph,
            audit=audit,
            db_engine=db_engine,
            pdf_service=pdf_service,
        )
