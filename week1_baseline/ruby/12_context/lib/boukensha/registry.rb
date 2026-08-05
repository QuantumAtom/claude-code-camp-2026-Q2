require_relative "errors"
require "opentelemetry/sdk"

module Boukensha
  class Registry
    def initialize(context)
      @context = context
    end

    def tool(name, description:, parameters: {}, &block)
      tool = Tool.new(name.to_s, description, parameters, block)
      @context.register_tool(tool)
      tool
    end

    def dispatch(name, args = {}, tool_call_id: nil)
      Boukensha.tracer.in_span('tool.dispatch') do |span|
        span.set_attribute('tool.name', name.to_s)
        span.set_attribute('tool.args', args.to_s)
        span.set_attribute('gen_ai.operation.name', 'execute_tool')
        span.set_attribute('gen_ai.tool.name', name.to_s)
        span.set_attribute('gen_ai.tool.call.arguments', args.to_s)
        span.set_attribute('gen_ai.tool.call.id', tool_call_id.to_s) if tool_call_id

        tool = @context.tools[name.to_s]
        raise UnknownToolError, "No tool registered as '#{name}'" unless tool

        result = tool.block.call(**args.transform_keys(&:to_sym))
        span.set_attribute('tool.result', result.to_s[0..200])
        span.set_attribute('gen_ai.tool.call.result', result.to_s[0..200])
        result
        # No explicit rescue here: Tracer#in_span already records the
        # exception and sets error status on this span for anything that
        # escapes the block above (unknown tool or a failing tool.block).
      end
    end
  end
end
