require_relative "errors"
require "opentelemetry/sdk"

module Boukensha
  class Registry
    TRACER = OpenTelemetry.tracer_provider.tracer('boukensha')

    def initialize(context)
      @context = context
    end

    def tool(name, description:, parameters: {}, &block)
      tool = Tool.new(name.to_s, description, parameters, block)
      @context.register_tool(tool)
      tool
    end

    def dispatch(name, args = {})
      TRACER.in_span('tool.dispatch') do |span|
        span.set_attribute('tool.name', name.to_s)
        span.set_attribute('tool.args', args.to_s)

        tool = @context.tools[name.to_s]
        unless tool
          span.status = OpenTelemetry::Trace::Status.error("Unknown tool: #{name}")
          raise UnknownToolError, "No tool registered as '#{name}'"
        end

        result = tool.block.call(**args.transform_keys(&:to_sym))
        span.set_attribute('tool.result', result.to_s[0..200])
        result
      end
    end
  end
end
