#!/usr/bin/env ruby
# frozen_string_literal: true

# MCP server exposing the standard file-system tools, sandboxed to a single
# root directory. Run as a stdio subprocess by
# lib/boukensha/tools/file_system.rb — the root directory is passed via the
# BOUKENSHA_MCP_FS_ROOT environment variable, since that's how the parent
# process (mcp_client.rb) launches it.
#
# Tool logic here is identical to the pre-MCP tools/file_system.rb
# implementation — only the transport changed (local closures -> an MCP
# server the framework talks to over stdio).

require "bundler/setup" if ENV["BUNDLE_GEMFILE"]
require "mcp"
require "fileutils"

ROOT = File.expand_path(ENV.fetch("BOUKENSHA_MCP_FS_ROOT"))

def resolve(path)
  absolute = File.expand_path(path.to_s, ROOT)
  if absolute == ROOT || absolute.start_with?("#{ROOT}/")
    absolute
  else
    "error: path '#{path}' escapes the working directory"
  end
end

def oops(msg) = "error: #{msg}"

def text_response(str)
  MCP::Tool::Response.new([{ type: "text", text: str }])
end

server = MCP::Server.new(name: "boukensha-file-system")

server.define_tool(
  name: "pwd",
  description: "Return the working directory — the root that all file paths are relative to."
) do |server_context:, **_args|
  text_response(ROOT)
end

server.define_tool(
  name: "list_directory",
  description: "List files and subdirectories at a path relative to the working directory. Defaults to the working directory itself.",
  input_schema: { properties: { path: { type: "string", description: "Relative path to list (default '.')" } } }
) do |server_context:, **args|
  path   = args[:path] || "."
  target = resolve(path)
  next text_response(target) if target.start_with?("error:")
  next text_response(oops("'#{path}' is not a directory")) unless File.directory?(target)

  entries = Dir.entries(target)
               .reject { |e| e == "." || e == ".." }
               .sort
               .map { |name| File.directory?(File.join(target, name)) ? "#{name}/" : name }

  text_response(entries.empty? ? "(empty)" : entries.join("\n"))
end

server.define_tool(
  name: "read_file",
  description: "Read and return the full contents of a file. Path is relative to the working directory.",
  input_schema: { properties: { path: { type: "string", description: "Relative path to the file" } }, required: ["path"] }
) do |server_context:, **args|
  target = resolve(args[:path])
  next text_response(target) if target.start_with?("error:")
  next text_response(oops("'#{args[:path]}' is not a file")) unless File.file?(target)

  begin
    text_response(File.read(target))
  rescue => e
    text_response(oops(e.message))
  end
end

server.define_tool(
  name: "write_file",
  description: "Write content to a file, creating it (and any missing parent directories) if needed, overwriting if it exists. Path is relative to the working directory.",
  input_schema: {
    properties: {
      path:    { type: "string", description: "Relative path to the file" },
      content: { type: "string", description: "Text content to write" }
    },
    required: ["path", "content"]
  }
) do |server_context:, **args|
  target = resolve(args[:path])
  next text_response(target) if target.start_with?("error:")

  begin
    FileUtils.mkdir_p(File.dirname(target))
    File.write(target, args[:content])
    rel = target.delete_prefix("#{ROOT}/")
    text_response("ok: wrote #{args[:content].bytesize} bytes to #{rel}")
  rescue => e
    text_response(oops(e.message))
  end
end

server.define_tool(
  name: "delete_file",
  description: "Delete a file. Directories are not deleted. Path is relative to the working directory.",
  input_schema: { properties: { path: { type: "string", description: "Relative path to the file to delete" } }, required: ["path"] }
) do |server_context:, **args|
  target = resolve(args[:path])
  next text_response(target) if target.start_with?("error:")
  next text_response(oops("'#{args[:path]}' is not a file")) unless File.file?(target)

  begin
    File.delete(target)
    text_response("ok: deleted #{args[:path]}")
  rescue => e
    text_response(oops(e.message))
  end
end

server.define_tool(
  name: "search_files",
  description: "Search for a text pattern (literal string or Ruby regex) across all files in the working directory tree. Returns matching lines in 'path:line_number:content' format.",
  input_schema: {
    properties: {
      pattern: { type: "string", description: "The text or regex pattern to search for" },
      path:    { type: "string", description: "Subdirectory or file to search within (default '.' = entire working directory)" },
      glob:    { type: "string", description: "File glob to restrict which files are searched, e.g. '*.rb' (default '*')" }
    },
    required: ["pattern"]
  }
) do |server_context:, **args|
  path, glob = args[:path] || ".", args[:glob] || "*"
  target = resolve(path)
  next text_response(target) if target.start_with?("error:")

  file_glob = File.file?(target) ? target : File.join(target, "**", glob)

  begin
    regex = Regexp.new(args[:pattern])
  rescue RegexpError => e
    next text_response(oops("invalid pattern: #{e.message}"))
  end

  matches = []
  Dir.glob(file_glob).sort.each do |file|
    next unless File.file?(file)
    rel = file.delete_prefix("#{ROOT}/")
    begin
      File.foreach(file).with_index(1) do |line, lineno|
        matches << "#{rel}:#{lineno}:#{line.chomp}" if line.match?(regex)
      end
    rescue => e
      matches << "#{rel}: error reading file: #{e.message}"
    end
  end

  text_response(matches.empty? ? "no matches" : matches.join("\n"))
end

MCP::Server::Transports::StdioTransport.new(server).open
