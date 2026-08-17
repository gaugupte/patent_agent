"""
/**"""
/**
* ? Author: Gautam
* ? Date: 2026-02-20
* ? Description:  file has misc commands for execution of various individual components of the application, including starting the server, testing endpoints, and managing environment variables. It provides instructions for running the application locally, testing the /predict endpoint using curl commands, and managing environment variables for LangChain and Ollama. The file also includes installation commands for required Python packages and dependencies.
* ? Usage:  As needed, you can run the commands in this file to start the server, test endpoints, and manage environment variables for the application. The commands can be executed in a terminal or command prompt.
*/
"""

* ? additional information regarding how to start & and use this on local
uvicorn app:app --reload --port 8000 #-- to start the server

* ? single line curl command to test the endpoint
curl -X POST http://127.0.0.1:8000/predict -H "Content-Type: application/json" -d "{\"question\":\"What is LangGraph?\",\"session_id\":\"ABC123\"}"

curl -X POST http://127.0.0.1:8000/predict -H "Content-Type: application/json" -d "{\"idf_text\":\"Invention Title:
Smart Hydration Bottle with Adaptive Fluid-Intake Monitoring

Technical Field:
The invention relates to smart beverage containers and systems
for monitoring and managing fluid intake.

The system includes a beverage container having a liquid-holding
chamber, a liquid-level or weight sensor, a temperature sensor,
a motion sensor, a processor, memory, a communication module,
and an indicator.

The liquid-level sensor determines changes in the quantity of
liquid in the container.

The processor uses the sensor information to determine fluid
consumed by the user.

Environmental temperature, user activity and historical fluid
consumption information are used to determine a personalized
hydration requirement.

The system compares actual consumption with the personalized
requirement and generates an adaptive hydration recommendation.

The recommendation may be presented through the container or
communicated to a mobile device.?\",\"session_id\":\"ABC123\"}"

* ? muliti line curl command to test the endpoint
curl -X POST http://127.0.0.1:8000/predict ^
-H "Content-Type: application/json" ^
-d "{\"question\":\"What is LangGraph?\",\"session_id\":\"ABC123\"}"

"""

"""


Step 1: Download and Install OllamaGo to the official website: ollama.com
Click the Download button and select Windows.
Run the downloaded OllamaSetup.exe installer and follow the quick setup wizard.
Once installed, a small llama icon will appear in your Windows taskbar tray, meaning the server is running in the background.
## ollama run phi3
ollama run mistral


Yes. ollama run mistral does create and expose active local inference endpoints.However, there is an important detail to understand:
the background Ollama server itself exposes the endpoints, while the run command specifically tells that server to load the mistral model 
into your computer's memory (RAM/VRAM) so it is ready to handle requests.
Once you execute that command, Ollama automatically serves two types of local inference endpoints simultaneously on your machine:

1. The OpenAI-Compatible Inference EndpointsThis is exactly what you need for your LangChain ChatOpenAI python code to work:
    Chat Completions: http://localhost:11434/v1/chat/completions
    Standard Completions: http://localhost:11434/v1/completions

2. Ollama's Native REST API EndpointsIf you want to bypass LangChain and send raw web requests (like using curl or Python's requests library),
 you can use Ollama's native endpoints:
 Text Generation: http://localhost:11434/api/generateStructured 
 Chat: http://localhost:11434/api/chat

 test: 
curl http://localhost:11434/api/generate -d "{\"model\": \"mistral\", \"prompt\": \"Why is the sky blue?\", \"stream\": false}"

if you want to un cache the previous environment variables, you can run the following commands in PowerShell:
$env:LANGCHAIN_TRACING_V2="false"
Remove-Item Env:LANGCHAIN_API_KEY -ErrorAction SilentlyContinue

"""

1. create a new github repo and copy the url of the repo
2. cd /path/to/your/local/folder
3. git init
4. git add .
5. git commit -m "Initial commit"
6. git remote add origin <your-repo-url>
7. git push -u origin master

"""
# /pip install fastapi
# pip install pydantic-settings
# pip install langgraph

# pip install langchain-openai
# from langchain_openai import ChatOpenAI
# pip install langchain-anthropic
# pip install langgraph
# pip install langchain-ollama
# pip install langchain-chroma chromadb
# pip install faiss-cpu langchain-community
# pip install pinecone langchain-pinecone
# pip install qdrant-client langchain-qdrant
# pip install azure-search-documents

# pip install python-dotenv
# pip install uvicorn
# pip install gunicorn

# pip install contextlib

# pip install fastmcp langchain-mcp-adapters


# ................................
# pip install pyodbc

# pip install mlflow pyngrok  # 3CyaS1gMoWnCh9TrZgOkZwJ5hdG_2SdJ9go3KUgmmPNyraR6S

# !pip install -U \
# langgraph \
# langchain \
# langchain-core \
# langchain-community \
# langchain-openai \
# pydantic \
# langsmith

# pip install -U openai langchain-openai
# pip install -U \
# langchain-google-genai \
# google-generativeai

# pip install -U \
# transformers \
# sentence-transformers \
# langchain-huggingface

# #If You Want Production Telemetry
# pip install \
# opentelemetry-api \
# opentelemetry-sdk \
# opentelemetry-exporter-otlp

# #If You Want Better Retry Logic
# pip install tenacity

# langgraph>=0.2.0
# langchain>=0.3.0
# langchain-core>=0.3.0
# langchain-community>=0.3.0
# langchain-openai>=0.3.0
# pydantic>=2.10.0
# tenacity>=9.0.0
# redis>=5.0.0
# langsmith>=0.3.0
# opentelemetry-api>=1.30.0
# opentelemetry-sdk>=1.30.0
# opentelemetry-exporter-otlp>=1.30.0
# scikit-learn>=1.6.0

# pip install fastmcp langchain-mcp-adapters

# Install PostgreSQL dependencies
# pip install psycopg psycopg_pool
