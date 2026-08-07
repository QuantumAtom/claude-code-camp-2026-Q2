require "json"
require_relative "base"

module Boukensha
  module Backends
    # https://docs.z.ai/api-reference/llm/chat-completion
    #
    # Z.ai (GLM models) speaks the standard OpenAI Chat Completions wire
    # format (not the Responses API that Backends::OpenAI targets) --
    # messages list with role/content, tools wrapped in
    # {type: "function", function: {...}}, tool results as
    # {role: "tool", tool_call_id: ...}, and assistant tool calls under
    # message.tool_calls[].function.arguments as a JSON string.
    # finish_reason is "tool_calls" or "stop".
    class Zai < Base
      BASE_URL = "https://api.z.ai/api/paas/v4/chat/completions"
      MODELS = {
        "glm-5.2" => {
          context_window: 1_000_000,
          cost_per_million: { input: 1.4, output: 4.4 },
          usage_unit: :tokens
        },
        "glm-4.6" => {
          context_window: 200_000,
          cost_per_million: { input: 0.6, output: 2.2 },
          usage_unit: :tokens
        },
        "glm-4.5" => {
          context_window: 128_000,
          cost_per_million: { input: 0.6, output: 2.2 },
          usage_unit: :tokens
        },
        "glm-4.5-air" => {
          context_window: 128_000,
          cost_per_million: { input: 0.2, output: 1.1 },
          usage_unit: :tokens
        },
        "glm-4.5-flash" => {
          context_window: 128_000,
          cost_per_million: { input: nil, output: nil },
          usage_unit: :tokens
        }
      }.freeze

      def initialize(api_key:, model:)
        @api_key = api_key
        configure_model(model)
      end

      def to_messages(system, messages)
        conversation = messages.flat_map do |msg|
          case msg.role
          when :tool_result
            [{ role: "tool", tool_call_id: msg.tool_use_id, content: msg.content.to_s }]
          when :assistant
            [assistant_message(msg.content)]
          else
            [{ role: msg.role.to_s, content: msg.content }]
          end
        end
        [{ role: "system", content: system }] + conversation
      end

      def to_tools(tools)
        tools.values.map do |tool|
          {
            type: "function",
            function: {
              name: tool.name,
              description: tool.description,
              parameters: {
                type: "object",
                properties: tool.parameters,
                required: tool.parameters.keys.map(&:to_s)
              }
            }
          }
        end
      end

      def to_payload(context, max_output_tokens: 1024, tools: nil)
        {
          model: @model,
          messages: to_messages(context.system, context.messages),
          tools: tools.nil? ? to_tools(context.tools) : tools,
          max_tokens: max_output_tokens
        }
      end

      def headers
        {
          "Content-Type"  => "application/json",
          "Authorization" => "Bearer #{@api_key}"
        }
      end

      def url
        BASE_URL
      end

      def parse_response(response)
        message = (response["choices"] || [{}]).first["message"] || {}
        tool_calls = message["tool_calls"] || []

        content = []
        content << { "type" => "reasoning", "text" => message["reasoning_content"] } if message["reasoning_content"]
        content << { "type" => "text", "text" => message["content"] } if message["content"]

        tool_calls.each do |tc|
          fn = tc["function"] || {}
          args = fn["arguments"]
          args = JSON.parse(args.nil? || args.empty? ? "{}" : args) if args.is_a?(String)
          content << {
            "type"  => "tool_use",
            "id"    => tc["id"],
            "name"  => fn["name"],
            "input" => args || {}
          }
        end

        { stop_reason: tool_calls.empty? ? "end_turn" : "tool_use", content: content }
      end

      private

      def assistant_message(content)
        blocks = content.is_a?(String) ? [{ "type" => "text", "text" => content }] : content
        text_blocks = blocks.select { |b| b["type"] == "text" }
        tool_blocks = blocks.select { |b| b["type"] == "tool_use" }

        text = text_blocks.map { |b| b["text"] }.join
        message = { role: "assistant", content: text.empty? ? nil : text }
        unless tool_blocks.empty?
          message[:tool_calls] = tool_blocks.map do |b|
            {
              id: b["id"],
              type: "function",
              function: { name: b["name"], arguments: b["input"].to_json }
            }
          end
        end
        message
      end
    end
  end
end
