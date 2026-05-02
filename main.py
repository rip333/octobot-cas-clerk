import functions_framework

@functions_framework.http
def handle_nomination_webhook(request):
    """
    DEPRECATED: Webhook disabled. The system now uses the /tally-nominations
    Discord slash command to process thread history in bulk.
    """
    return 'Polling and silent clerk functionality disabled. Use /tally-nominations.', 200
