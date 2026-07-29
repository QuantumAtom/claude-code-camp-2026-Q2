require_relative "../mcp_client"

module Boukensha
  module Tools
    # FileSystem registers the standard set of file-oriented tools against a
    # registry, all sandboxed to a single root directory.
    #
    # Tools registered:
    #   pwd              — return the working directory
    #   list_directory   — list files and subdirectories at a path
    #   read_file        — read the full contents of a file
    #   write_file       — write (or overwrite) a file
    #   delete_file      — delete a file
    #   search_files     — grep for a pattern across files in the working tree
    #
    # The tools themselves run inside a separate MCP server process
    # (mcp_servers/file_system_server.rb), spawned over stdio and bridged
    # into this Registry via McpClient.register_mcp_tools — the
    # Registry/Tool/Agent call sites here are unchanged from the pre-MCP
    # version; only where the tool logic actually executes has moved.
    #
    # Usage (handled automatically by Boukensha.run / Boukensha.repl when working_dir:
    # is set, but you can call it directly too):
    #
    #   Boukensha::Tools::FileSystem.register(registry, working_dir: "/my/project")
    #
    module FileSystem
      SERVER_SCRIPT = File.expand_path("../mcp_servers/file_system_server.rb", __dir__)

      def self.register(registry, working_dir:)
        McpClient.register_mcp_tools(
          registry,
          command: RbConfig.ruby,
          args:    [SERVER_SCRIPT],
          env:     mcp_env(working_dir)
        )
      end

      # Propagates the Gemfile this step's own bundle resolved to, so the
      # spawned server subprocess activates the same "mcp" gem regardless of
      # the *caller's* cwd (Open3.popen3 inherits Dir.pwd, not the gem's
      # install directory) — the same self-locating-path discipline
      # boukensha_loader.rb already uses for BOUKENSHA_PATH resolution.
      def self.mcp_env(working_dir)
        env = { "BOUKENSHA_MCP_FS_ROOT" => File.expand_path(working_dir) }
        env["BUNDLE_GEMFILE"] = ENV["BUNDLE_GEMFILE"] if ENV["BUNDLE_GEMFILE"]
        env
      end
      private_class_method :mcp_env
    end
  end
end
