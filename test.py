from sympy import false

from config.config import Settings


settings = Settings()
# print(settings.PORT)
# print(settings.LANGSMITH_API_KEY)

## ollama run phi3
## ollama run mistral

import os
from langchain_openai import ChatOpenAI

import os

# Turn off cloud tracing completely
# os.environ["LANGCHAIN_TRACING_V2"] = "false"


# Initialize the Ollama OpenAI-compatible server
llm = ChatOpenAI(
    base_url="http://localhost:11434/v1",  # Ollama's default local port
    api_key="ollama",  # Required placeholder string
    model="mistral",  # Matches the model name from step 2
    temperature=0,
)

# Test your configuration
try:
    response = llm.invoke("Hello! how can you assist me in my patent work?")
    print(response.content)
except Exception as e:
    print(f"Error connecting to Ollama: {e}")


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
