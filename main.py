import functions_framework
import json
from gemini_agent import GeminiAgent

agent = GeminiAgent()

@functions_framework.http
def handle_nomination_webhook(request):
    """
    HTTP Cloud Function designed to receive webhook payloads from Discord
    or our Discord Listener bot.
    """
    request_json = request.get_json(silent=True)
    if not request_json:
        return 'Missing JSON payload', 400

    message_text = request_json.get('content')
    author_id = request_json.get('author_id')
    author_name = request_json.get('author_name')

    if not message_text or not author_id:
        return 'Missing message data', 400

    # Pass to Gemini Agent
    try:
        result = agent.process_message(message_text, author_id, author_name)
        return json.dumps(result), 200
    except Exception as e:
        print(f"Error processing message: {e}")
        return str(e), 500
