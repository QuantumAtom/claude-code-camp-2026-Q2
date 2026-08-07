require "opentelemetry/sdk"

module Boukensha
  # Reads gen_ai.conversation.id (and, if present, enduser.id) out of OTel
  # Baggage (set once per agent run — see Agent#run) and stamps them onto
  # every span as it starts, so both reach child spans (llm.call,
  # tool.dispatch) without threading them through every method signature.
  class ConversationSpanProcessor < OpenTelemetry::SDK::Trace::SpanProcessor
    def on_start(span, parent_context)
      conversation_id = OpenTelemetry::Baggage.value("gen_ai.conversation.id", context: parent_context)
      span.set_attribute("gen_ai.conversation.id", conversation_id) if conversation_id

      user_id = OpenTelemetry::Baggage.value("enduser.id", context: parent_context)
      span.set_attribute("enduser.id", user_id) if user_id
    end
  end
end
