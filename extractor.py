import anthropic                  # brings in the Claude API tool
import json                       # brings in the tool that handles JSON data
from dotenv import load_dotenv    # brings in the tool that reads our .env file

load_dotenv()                     # loads our API key from the .env file

client = anthropic.Anthropic()    # creates our connection to Claude

tools = [
    {
        "name": "extract_obligation",
        "description": "Extract a single contract obligation from the provided clause text and return it as structured data",
        "input_schema": {
            "type": "object",
            "properties": {
                "plain_english_obligation": {
                    "type": "string",
                    "description": "The obligation written in plain English — what the contractor must actually do"
                },
                "obligation_type": {
                    "type": "string",
                    "description": "Category of obligation — reporting, compliance, flow_down, insurance, one_time, or recurring"
                },
                "trigger_or_deadline": {
                    "type": "string",
                    "description": "When this obligation must be fulfilled — e.g. within 72 hours, quarterly, upon contract award"
                },
                "responsible_party": {
                    "type": "string",
                    "description": "Who is responsible — usually contractor or subcontractor"
                },
                "source_clause_id": {
                    "type": "string",
                    "description": "The FAR or DFARS clause number this obligation comes from — e.g. 252.204-7012"
                },
                "verbatim_quote": {
                    "type": "string",
                    "description": "The exact words from the contract that prove this obligation exists — copy word for word"
                },
                "confidence": {
                    "type": "number",
                    "description": "How confident you are this is a real obligation — 0.0 to 1.0"
                }
            },
            "required": [
                "plain_english_obligation",
                "obligation_type",
                "trigger_or_deadline",
                "responsible_party",
                "source_clause_id",
                "verbatim_quote",
                "confidence"
            ]
        }
    }
]

system_prompt = """You are an expert government contract analyst specializing in FAR and DFARS regulations. 
Your job is to read federal contract clause text and identify real legal obligations — things the contractor is actually required to do.

An obligation is a specific requirement the contractor MUST fulfill. Look for language like:
- "shall", "must", "is required to", "will", "is obligated to"

Do NOT flag these as obligations:
- General definitions or background information
- Things the government must do
- Optional actions ("may", "can", "is permitted to")
- Boilerplate introductory language

For every real obligation you find, use the extract_obligation tool to return it as structured data.
Always copy the verbatim quote exactly as it appears in the clause text — word for word, no paraphrasing."""


def extract_obligations_from_clause(clause_text, clause_id):
    """
    Takes raw clause text and a clause ID and returns a list of structured obligations
    clause_text = the actual text of the FAR/DFARS clause
    clause_id = the clause number like 252.204-7012
    """

    message = client.messages.create(
        model="claude-sonnet-4-6",           # which Claude model we're using
        max_tokens=1024,                      # maximum length of response
        system=system_prompt,                 # gives Claude its instructions
        tools=tools,                          # gives Claude the form to fill out
        messages=[
            {
                "role": "user",
                "content": f"Extract all obligations from this contract clause:\n\nClause ID: {clause_id}\n\nClause Text:\n{clause_text}"
            }
        ]
    )

    obligations = []
    for block in message.content:                          # loops through everything Claude returned
        if block.type == "tool_use":                       # only grab the structured JSON responses
            # adds each obligation to our list
            obligations.append(block.input)

    # returns the complete list of obligations
    return obligations


test_clause = """
252.204-7012 SAFEGUARDING COVERED DEFENSE INFORMATION AND CYBER INCIDENT REPORTING

The Contractor shall provide adequate security on all contractor information systems that process, 
store, or transmit covered defense information.

The Contractor shall rapidly report cyber incidents directly to DoD at http://dibnet.dod.mil. 
The Contractor shall report cyber incidents within 72 hours of discovery.

The Contractor shall submit to DoD a malware analysis report within 60 days of the discovery 
of a cyber incident.

The Contractor shall flow down the requirements of this clause to all subcontractors that 
process, store, or transmit covered defense information.
"""

if __name__ == "__main__":
    # tells you the program started
    print("Running Contract Obligation Extractor...\n")

    results = extract_obligations_from_clause(
        clause_text=test_clause,
        clause_id="252.204-7012"
    )

    # tells you how many obligations were found
    print(f"Found {len(results)} obligations:\n")

    # loops through each obligation
    for i, obligation in enumerate(results, 1):
        # prints the obligation number
        print(f"Obligation {i}:")
        # prints the obligation as formatted JSON
        print(json.dumps(obligation, indent=2))
        # prints a divider line
        print("-" * 50)
