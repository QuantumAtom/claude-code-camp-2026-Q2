from opentelemetry import baggage
from opentelemetry.sdk.trace import SpanProcessor


# Reads gen_ai.conversation.id (and, if present, enduser.id) out of OTel
# Baggage (set once per agent run -- see Agent.run) and stamps them onto
# every span as it starts, so both reach child spans (llm.call,
# tool.dispatch) without threading them through every function signature.
class ConversationSpanProcessor(SpanProcessor):
    def on_start(self, span, parent_context=None):
        conversation_id = baggage.get_baggage("gen_ai.conversation.id", context=parent_context)
        if conversation_id:
            span.set_attribute("gen_ai.conversation.id", conversation_id)

        user_id = baggage.get_baggage("enduser.id", context=parent_context)
        if user_id:
            span.set_attribute("enduser.id", user_id)
