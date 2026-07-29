#!/usr/bin/env ruby
# frozen_string_literal: true

# MCP server exposing the run_command shell tool. Run as a stdio subprocess
# by lib/boukensha/tools/shell.rb — configuration comes from environment
# variables (root dir, timeout, allowed-commands list) rather than a CLI
# argument, since that's how the parent process (mcp_client.rb) launches it.
#
# Tool logic here is identical to the pre-MCP tools/shell.rb implementation
# — only the transport changed.

require "bundler/setup" if ENV["BUNDLE_GEMFILE"]
require "mcp"
require "open3"
require "timeout"

ROOT    = File.expand_path(ENV.fetch("BOUKENSHA_MCP_SHELL_ROOT"))
TIMEOUT = Integer(ENV.fetch("BOUKENSHA_MCP_SHELL_TIMEOUT", "30"))

# Same three-state env-var convention as Python's shell_server.py: unset =
# allow all; set-but-empty = empty list (reject everything); "a,b,c" = that
# allow-list.
raw_allowed      = ENV["BOUKENSHA_MCP_SHELL_ALLOWED"]
ALLOWED_COMMANDS = raw_allowed.nil? ? nil : raw_allowed.split(",").reject(&:empty?)

allowed_note = ALLOWED_COMMANDS ? " Allowed executables: #{ALLOWED_COMMANDS.join(', ')}." : ""

def text_response(str)
  MCP::Tool::Response.new([{ type: "text", text: str }])
end

server = MCP::Server.new(name: "boukensha-shell")

server.define_tool(
  name: "run_command",
  description: "Run a shell command inside the working directory and return its combined stdout+stderr output. " \
               "Commands run with a #{TIMEOUT}-second timeout.#{allowed_note}",
  input_schema: { properties: { command: { type: "string", description: "The shell command to execute (e.g. 'ruby script.rb', 'ls -la', 'git status')" } }, required: ["command"] }
) do |server_context:, **args|
  command = args[:command]

  if ALLOWED_COMMANDS
    executable = command.to_s.strip.split(/\s+/).first.to_s
    unless ALLOWED_COMMANDS.include?(executable)
      next text_response("error: '#{executable}' is not in the allowed-commands list (#{ALLOWED_COMMANDS.join(', ')})")
    end
  end

  stdout_err, status = nil, nil
  begin
    Timeout.timeout(TIMEOUT) { stdout_err, status = Open3.capture2e(command, chdir: ROOT) }
  rescue Errno::ENOENT => e
    next text_response("error: command not found: #{e.message}")
  rescue Timeout::Error
    next text_response("error: command timed out after #{TIMEOUT}s: #{command}")
  end

  exit_note = status.success? ? "" : "\n[exit #{status.exitstatus}]"
  output    = stdout_err.to_s.strip
  text_response(output.empty? ? "(no output)#{exit_note}" : "#{output}#{exit_note}")
end

MCP::Server::Transports::StdioTransport.new(server).open
