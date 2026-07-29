require "mcp"

module Boukensha
  # Synchronous bridge to an MCP server run as a stdio subprocess.
  #
  # Unlike the Python port's mcp_client.py, no event-loop bridge is needed
  # here: the mcp gem's MCP::Client::Stdio transport is already built on
  # Open3.popen3 + blocking IO#gets, so this is a thin wrapper, not a
  # concurrency primitive in its own right.
  module McpClient
    # Spawn an MCP server, discover its tools, and register each one into
    # a boukensha Registry — a bridge, not a replacement, for the existing
    # Tool/Registry/Agent/backends architecture.
    #
    # Each MCP tool's inputSchema (a JSON Schema object, string keys) is
    # unpacked back into boukensha's flat parameters shape
    # ({ name: { type:, description: } }), matching what backends/*.rb
    # already expects — this is the layer that lets the rest of the
    # framework stay exactly as it was.
    def self.register_mcp_tools(registry, command:, args: [], env: nil)
      transport = MCP::Client::Stdio.new(command: command, args: args, env: env)
      client    = MCP::Client.new(transport: transport)
      client.connect

      at_exit { transport.close }

      client.tools.each do |tool|
        properties = (tool.input_schema || {})["properties"] || {}

        registry.tool tool.name,
          description: tool.description || "",
          parameters:  properties do |**kwargs|
          response = client.call_tool(name: tool.name, arguments: kwargs)
          content  = response.dig("result", "content") || []
          text     = content.filter_map { |block| block["text"] }.join("\n")

          if response.dig("result", "isError")
            text.empty? ? "error: tool call failed" : "error: #{text}"
          else
            text
          end
        end
      end

      client
    end
  end
end
