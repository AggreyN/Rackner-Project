import anthropic          # brings in the Claude API tool we installed
from dotenv import load_dotenv  # brings in the tool that reads our .env file

load_dotenv()             # actually reads the .env file and loads our API key

client = anthropic.Anthropic()  # creates our connection to Claude

message = client.messages.create(
    model="claude-sonnet-4-6",  # which Claude model we're using
    max_tokens=1024,             # maximum length of Claude's response
    messages=[
        # what we're sending to Claude
        {"role": "user", "content": "Say hello from the Contract Obligation Extractor!"}
    ]
)

print(message.content[0].text)  # prints Claude's response to the terminal
