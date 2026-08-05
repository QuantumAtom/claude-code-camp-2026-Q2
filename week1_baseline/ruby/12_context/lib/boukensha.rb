require 'opentelemetry/sdk'
require 'opentelemetry/exporter/otlp'

require_relative "boukensha/version"
require_relative "boukensha/config"

module Boukensha
  @debug  = false
  @config = nil
  @telemetry_configured = false

  def self.config
    @config ||= Config.new
  end

  # Looks up the tracer *lazily*, at call time, rather than caching it in a
  # constant. OpenTelemetry::SDK.configure swaps in a brand-new
  # TracerProvider object each time it runs (confirmed: re-running configure
  # does not mutate the existing provider), and configure_telemetry! always
  # runs after this file (and client.rb/registry.rb/agent.rb) has already
  # loaded. A `TRACER = OpenTelemetry.tracer_provider.tracer(...)` constant
  # would therefore bind to the pre-configuration provider -- which has no
  # exporter -- and every span created through it would be silently dropped.
  def self.tracer
    OpenTelemetry.tracer_provider.tracer('boukensha')
  end

  # Configures the OpenTelemetry SDK exactly once. Must run *after* `config`
  # has loaded .env (see Config#load_env) -- OTLP::Exporter.new reads
  # OTEL_EXPORTER_OTLP_ENDPOINT/HEADERS from ENV at construction time, so
  # configuring the SDK any earlier would silently point the exporter at the
  # OTLP default (localhost:4318) instead of Honeycomb.
  def self.configure_telemetry!
    return if @telemetry_configured
    @telemetry_configured = true

    OpenTelemetry::SDK.configure do |c|
      c.service_name = ENV.fetch('OTEL_SERVICE_NAME', 'boukensha')
      c.add_span_processor(
        OpenTelemetry::SDK::Trace::Export::BatchSpanProcessor.new(
          OpenTelemetry::Exporter::OTLP::Exporter.new
        )
      )
      c.add_span_processor(ConversationSpanProcessor.new)
    end
  end
  private_class_method :configure_telemetry!

  def self.debug!
    @debug = true
  end

  def self.debug?
    @debug
  end

  # One-shot run: send a single task, get a response, return.
  #
  # working_dir:      roots all tool calls to this directory (default: Dir.pwd).
  #                   Registers Boukensha::Tools::FileSystem (pwd, list_directory,
  #                   read_file, write_file, delete_file, search_files) and
  #                   Boukensha::Tools::Shell (run_command) automatically.
  #                   Pass working_dir: false to opt out entirely.
  #
  # allowed_commands: Array of shell-executable names the agent is allowed to
  #                   run via run_command (e.g. ["ruby", "git"]).
  #                   nil (default) permits everything — useful for demos.
  #                   Pass an empty Array [] to disable run_command entirely.
  #
  # shell_timeout:    Seconds before a run_command is killed (default 30).
  #
  # mud:              Hash of MUD connection options — registers all MUD gameplay
  #                   tools and keeps a single session alive across every tool call.
  #                   When nil (default), config.mud_* values are used if mud_host
  #                   is set in settings.yaml. Pass mud: false to disable entirely.
  def self.run(
    task:,
    system:           nil,
    model:            nil,
    backend:          nil,
    api_key:          nil,
    ollama_host:      "http://localhost:11434",
    log:              nil,
    context_window:   nil,
    max_output_tokens: nil,
    working_dir:      Dir.pwd,
    allowed_commands: nil,
    shell_timeout:    30,
    mud:              nil,
    &block
  )
    cfg     = config                           # loads .env; populates ENV
    configure_telemetry!
    system  ||= cfg.system_prompt
    model   ||= cfg.model
    context_window ||= Models.context_window(model)
    backend ||= cfg.provider_type.to_sym
    api_key ||= case backend
                when :anthropic    then ENV["ANTHROPIC_API_KEY"]
                when :openai       then ENV["OPENAI_API_KEY"]
                when :gemini       then ENV["GEMINI_API_KEY"]
                when :ollama_cloud then ENV["OLLAMA_API_KEY"]
                end

    ctx      = Context.new(system: system, context_window: context_window, working_dir: working_dir, compaction_threshold: cfg.agent_compaction_threshold)
    registry = Registry.new(ctx)

    if working_dir
      Tools::FileSystem.register(registry, working_dir: working_dir)
      Tools::Shell.register(registry, working_dir: working_dir,
                            timeout: shell_timeout, allowed_commands: allowed_commands)
    end

    # mud: nil means "use config if host is set"; mud: false means "skip entirely"
    resolved_mud = mud == false ? nil : (mud || mud_opts_from_config(cfg))
    Tools::Mud.register(registry, **resolved_mud) if resolved_mud

    RunDSL.new(registry).instance_eval(&block) if block

    be = case backend
         when :anthropic    then Backends::Anthropic.new(api_key: api_key, model: model)
         when :openai       then Backends::OpenAI.new(api_key: api_key, model: model)
         when :gemini       then Backends::Gemini.new(api_key: api_key, model: model)
         when :ollama       then Backends::Ollama.new(host: ollama_host, model: model)
         when :ollama_cloud then Backends::OllamaCloud.new(api_key: api_key, model: model)
         else raise ArgumentError, "Unknown backend #{backend.inspect}. Use :anthropic, :openai, :gemini, :ollama, or :ollama_cloud."
         end

    builder = PromptBuilder.new(ctx, be)
    client  = Client.new(builder)
    logger  = Logger.new(log: log, snapshot: {
      max_iterations:    cfg.agent_max_iterations,
      max_turn_tokens:   cfg.agent_max_turn_tokens,
      max_output_tokens: (max_output_tokens || cfg.agent_max_output_tokens),
      context_window:    context_window,
      model:             model,
      provider:          backend
    })
    agent   = Agent.new(context: ctx, registry: registry, builder: builder, client: client, logger: logger,
                        max_iterations: cfg.agent_max_iterations,
                        max_turn_tokens: cfg.agent_max_turn_tokens,
                        max_output_tokens: (max_output_tokens || cfg.agent_max_output_tokens))

    ctx.add_message(:user, task)
    agent.run
  ensure
    logger&.close
    # Flushes whatever spans are still sitting in the BatchSpanProcessor's
    # queue before the process exits -- without this, a short-lived run can
    # exit before the processor's next scheduled export and silently drop
    # every span it recorded.
    OpenTelemetry.tracer_provider.shutdown if @telemetry_configured
  end

  # Interactive REPL — see Boukensha.run for full option documentation.
  #
  # tui: true (default) wraps the REPL in a charm-ruby TUI.  Pass tui: false or
  # use the --no-tui CLI flag to fall back to the plain terminal REPL.
  def self.repl(
    system:           nil,
    model:            nil,
    backend:          nil,
    api_key:          nil,
    ollama_host:      "http://localhost:11434",
    log:              nil,
    context_window:   nil,
    max_output_tokens: nil,
    working_dir:      Dir.pwd,
    allowed_commands: nil,
    shell_timeout:    30,
    mud:              nil,
    tui:              true,
    &block
  )
    cfg     = config                           # loads .env; populates ENV
    configure_telemetry!
    system  ||= cfg.system_prompt
    model   ||= cfg.model
    context_window ||= Models.context_window(model)
    backend ||= cfg.provider_type.to_sym
    api_key ||= case backend
                when :anthropic    then ENV["ANTHROPIC_API_KEY"]
                when :openai       then ENV["OPENAI_API_KEY"]
                when :gemini       then ENV["GEMINI_API_KEY"]
                when :ollama_cloud then ENV["OLLAMA_API_KEY"]
                end

    ctx      = Context.new(system: system, context_window: context_window, working_dir: working_dir, compaction_threshold: cfg.agent_compaction_threshold)
    registry = Registry.new(ctx)

    if working_dir
      Tools::FileSystem.register(registry, working_dir: working_dir)
      Tools::Shell.register(registry, working_dir: working_dir,
                            timeout: shell_timeout, allowed_commands: allowed_commands)
    end

    resolved_mud = mud == false ? nil : (mud || mud_opts_from_config(cfg))
    Tools::Mud.register(registry, **resolved_mud) if resolved_mud

    RunDSL.new(registry).instance_eval(&block) if block

    be = case backend
         when :anthropic    then Backends::Anthropic.new(api_key: api_key, model: model)
         when :openai       then Backends::OpenAI.new(api_key: api_key, model: model)
         when :gemini       then Backends::Gemini.new(api_key: api_key, model: model)
         when :ollama       then Backends::Ollama.new(host: ollama_host, model: model)
         when :ollama_cloud then Backends::OllamaCloud.new(api_key: api_key, model: model)
         else raise ArgumentError, "Unknown backend #{backend.inspect}. Use :anthropic, :openai, :gemini, :ollama, or :ollama_cloud."
         end

    builder = PromptBuilder.new(ctx, be)
    client  = Client.new(builder)
    logger  = Logger.new(log: log, snapshot: {
      max_iterations:    cfg.agent_max_iterations,
      max_turn_tokens:   cfg.agent_max_turn_tokens,
      max_output_tokens: (max_output_tokens || cfg.agent_max_output_tokens),
      context_window:    context_window,
      model:             model,
      provider:          backend
    })

    repl = Repl.new(
      context:    ctx,
      registry:   registry,
      builder:    builder,
      client:     client,
      logger:     logger,
      max_iterations:    cfg.agent_max_iterations,
      max_turn_tokens:   cfg.agent_max_turn_tokens,
      max_output_tokens: (max_output_tokens || cfg.agent_max_output_tokens),
      config_dir: cfg.dir,
      provider:   backend,
      model:      model,
      version:    VERSION,
      api_key:    api_key,
      mud:        resolved_mud
    )

    if tui && defined?(Tui)
      Tui.new(repl).start
    else
      repl.start
    end
  rescue Interrupt
    puts "\nInterrupted."
  ensure
    logger&.close
    # Flushes whatever spans are still sitting in the BatchSpanProcessor's
    # queue before the process exits -- without this, a short-lived run can
    # exit before the processor's next scheduled export and silently drop
    # every span it recorded.
    OpenTelemetry.tracer_provider.shutdown if @telemetry_configured
  end

  # Build a mud options hash from config (used when mud: nil is passed to run/repl).
  # Returns nil if no MUD host is configured.
  def self.mud_opts_from_config(cfg)
    return nil unless cfg.mud_host && cfg.mud_username

    {
      host:     cfg.mud_host,
      port:     cfg.mud_port,
      name:     cfg.mud_username,
      password: cfg.mud_password
    }
  end
  private_class_method :mud_opts_from_config
end

require_relative "boukensha/conversation_span_processor"
require_relative "boukensha/tool"
require_relative "boukensha/message"
require_relative "boukensha/models"
require_relative "boukensha/context"
require_relative "boukensha/errors"
require_relative "boukensha/registry"
require_relative "boukensha/prompt_builder"
require_relative "boukensha/logger"
require_relative "boukensha/backends/base"
require_relative "boukensha/backends/anthropic"
require_relative "boukensha/backends/gemini"
require_relative "boukensha/backends/ollama"
require_relative "boukensha/backends/ollama_cloud"
require_relative "boukensha/backends/openai"
require_relative "boukensha/client"
require_relative "boukensha/agent"
require_relative "boukensha/run_dsl"
require_relative "boukensha/repl"
require_relative "boukensha/tools/file_system"
require_relative "boukensha/tools/shell"
require_relative "boukensha/tools/mud"
require_relative "boukensha/tui"
