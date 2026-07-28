# BoukenshaLoader resolves which step folder to load from, then boots the REPL.
#
# Resolution order:
#   1. BOUKENSHA_PATH environment variable (selects which *step* lib to load)
#   2. ~/.boukensharc  (BOUKENSHA_PATH= line, or a bare path for backward compat)
#   3. The lib/ directory bundled inside this gem (step 8 — the latest release)
#
# Config directory (settings.yaml, .env, system.md) is separate, resolved:
#   1. BOUKENSHA_DIR environment variable
#   2. ~/.boukensharc  (BOUKENSHA_DIR= line)
#   3. ~/.boukensha  (default)
#
# ~/.boukensharc format — one directive per line, KEY=VALUE:
#   BOUKENSHA_PATH=~/Sites/boukensha/08_the_repl_loop
#   BOUKENSHA_DIR=~/Sites/boukensha/.boukensha
# A line with no "=" is treated as a bare BOUKENSHA_PATH (legacy format).
#
# Examples:
#   boukensha                                                              # uses bundled lib + ~/.boukensha
#   BOUKENSHA_PATH=~/Sites/boukensha/04_api_client boukensha              # loads step 4
#   BOUKENSHA_DIR=~/projects/mybot/.boukensha boukensha                   # custom config dir
#   echo ~/Sites/boukensha/08_the_repl_loop > ~/.boukensharc && boukensha # permanent step default
module BoukenshaLoader
  # Absolute path to this gem's own bundled boukensha lib.
  BUNDLED_LIB = File.expand_path("../boukensha.rb", __FILE__)

  # Reads ~/.boukensharc into a { "BOUKENSHA_PATH" => ..., "BOUKENSHA_DIR" => ... } hash.
  def self.read_rc
    rc = File.expand_path("~/.boukensharc")
    return {} unless File.exist?(rc)

    File.read(rc).each_line.with_object({}) do |line, directives|
      line = line.strip
      next if line.empty? || line.start_with?("#")

      if line.include?("=")
        key, value = line.split("=", 2)
        directives[key.strip] = value.strip
      else
        directives["BOUKENSHA_PATH"] ||= line
      end
    end
  end

  def self.resolve
    rc = read_rc

    # BOUKENSHA_DIR: env var wins, then ~/.boukensharc. Config.rb reads this
    # lazily, so setting it here (before `require main`) is early enough.
    ENV["BOUKENSHA_DIR"] ||= rc["BOUKENSHA_DIR"] if rc["BOUKENSHA_DIR"]

    # 1. Env var wins.
    if ENV["BOUKENSHA_PATH"]
      dir  = File.expand_path(ENV["BOUKENSHA_PATH"])
      main = File.join(dir, "lib", "boukensha.rb")
      return main if File.exist?(main)

      abort <<~MSG
        boukensha: BOUKENSHA_PATH is set but no lib/boukensha.rb found at:
               #{dir}
               Make sure BOUKENSHA_PATH points to a step folder, e.g.:
               BOUKENSHA_PATH=~/Sites/boukensha/07_the_repl_loop boukensha
      MSG
    end

    # 2. ~/.boukensharc
    if rc["BOUKENSHA_PATH"]
      dir  = File.expand_path(rc["BOUKENSHA_PATH"])
      main = File.join(dir, "lib", "boukensha.rb")
      return main if File.exist?(main)

      abort <<~MSG
        boukensha: ~/.boukensharc points to #{dir}
               but no lib/boukensha.rb was found there.
               Update ~/.boukensharc or remove it to use the bundled default.
      MSG
    end

    # 3. Bundled default.
    BUNDLED_LIB
  end

  def self.load_and_start_repl
    main = resolve
    step_dir = File.dirname(File.dirname(main))

    puts "[boukensha] loading from: #{step_dir}" if ENV["BOUKENSHA_DEBUG"]

    require main

    unless Boukensha.respond_to?(:repl)
      abort <<~MSG
        boukensha: the step at #{step_dir}
               does not support the interactive REPL (added in step 7).
               Run its examples directly, e.g.:
                 ruby #{step_dir}/examples/*.rb
               Or point BOUKENSHA_PATH at step 7 or later.
      MSG
    end

    Boukensha.repl
  end
end
