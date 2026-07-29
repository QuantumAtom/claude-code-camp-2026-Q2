require_relative "../mcp_client"

module Boukensha
  module Tools
    # Shell registers command-execution tools against a registry.
    #
    # Tools registered:
    #   run_command  — run an arbitrary shell command inside the working directory
    #
    # Options:
    #   working_dir:      (required) all commands run with this as their cwd
    #   timeout:          seconds before a command is killed (default 30)
    #   allowed_commands: optional Array of allowed executable names (e.g. ["ruby", "git"]).
    #                     When nil (the default) all commands are permitted.
    #                     When set, any command whose first token is not in the list
    #                     is rejected before execution.
    #
    # The tool itself runs inside a separate MCP server process
    # (mcp_servers/shell_server.rb), spawned over stdio and bridged into this
    # Registry via McpClient.register_mcp_tools — same bridge pattern as
    # tools/file_system.rb.
    #
    # Usage (handled automatically by Boukensha.run / Boukensha.repl when working_dir:
    # is set):
    #
    #   Boukensha::Tools::Shell.register(
    #     registry,
    #     working_dir:      "/my/project",
    #     allowed_commands: ["ruby", "bundle", "rspec", "git"]
    #   )
    #
    module Shell
      SERVER_SCRIPT = File.expand_path("../mcp_servers/shell_server.rb", __dir__)

      def self.register(registry, working_dir:, timeout: 30, allowed_commands: nil)
        McpClient.register_mcp_tools(
          registry,
          command: RbConfig.ruby,
          args:    [SERVER_SCRIPT],
          env:     mcp_env(working_dir, timeout, allowed_commands)
        )
      end

      # See tools/file_system.rb's mcp_env for why BUNDLE_GEMFILE is forwarded.
      def self.mcp_env(working_dir, timeout, allowed_commands)
        env = {
          "BOUKENSHA_MCP_SHELL_ROOT"    => File.expand_path(working_dir),
          "BOUKENSHA_MCP_SHELL_TIMEOUT" => timeout.to_s
        }
        env["BOUKENSHA_MCP_SHELL_ALLOWED"] = allowed_commands.map(&:to_s).join(",") if allowed_commands
        env["BUNDLE_GEMFILE"] = ENV["BUNDLE_GEMFILE"] if ENV["BUNDLE_GEMFILE"]
        env
      end
      private_class_method :mcp_env
    end
  end
end
