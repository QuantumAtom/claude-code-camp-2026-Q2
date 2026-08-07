# Standalone parity check, no rspec/minitest dependency -- consistent with
# this repo's existing convention (every step's examples/example.rb is a
# runnable smoke test, not an rspec suite; see plan §6b/§11 decision #4).
#
# Run: ruby week3_capable/fixtures/check_parser_fixtures.rb

require "yaml"

$LOAD_PATH.unshift File.expand_path("../ruby/lib", __dir__)
require "boukensha/world/parser"
require "boukensha/world/observer" # for MOB_LINE_NAME_RE / MOB_LINE_STOPWORDS

Parser = Boukensha::World::Parser
World = Boukensha::World

FIXTURES_PATH = File.expand_path("parser_cases.yaml", __dir__)

STRUCT_FUNCTIONS = %w[parse_room parse_pickup parse_combat_result].freeze

def actual_for(kase)
  fn = kase["function"]
  if fn == "parse_pickup"
    Parser.parse_pickup(kase["raw_text"], item_arg: (kase["args"] || {})["item"])
  elsif fn == "detect_seed_zone"
    name, description = kase["name_desc"]
    Parser.detect_seed_zone(name, description)
  else
    Parser.public_send(fn, kase["raw_text"])
  end
end

def as_plain(value)
  value.is_a?(Struct) ? value.to_h.transform_keys(&:to_s) : value
end

def check_mob_line_case(kase)
  failures = []
  kase["cases"].each do |sub|
    m = World::MOB_LINE_NAME_RE.match(sub["line"])
    is_real = !m.nil? && !World::MOB_LINE_STOPWORDS.include?(m[1].strip.split.first.downcase)
    if is_real != sub["is_real_mob"]
      failures << "    line=#{sub['line'].inspect} expected is_real_mob=#{sub['is_real_mob']} got #{is_real}"
    end
  end
  failures
end

def check_classify_consumable_case(kase)
  failures = []
  kase["cases"].each do |sub|
    actual = Parser.classify_consumable(sub["name"])
    if actual != sub["expected"]
      failures << "    name=#{sub['name'].inspect} expected #{sub['expected'].inspect} got #{actual.inspect}"
    end
  end
  failures
end

def main
  cases = YAML.load_file(FIXTURES_PATH)
  failures = 0

  cases.each do |kase|
    if kase["function"] == "mob_line_is_real_mob"
      errs = check_mob_line_case(kase)
      if errs.empty?
        puts "ok   #{kase['name']}"
      else
        failures += 1
        puts "FAIL #{kase['name']}:"
        puts errs.join("\n")
      end
      next
    end

    if kase["function"] == "classify_consumable_cases"
      errs = check_classify_consumable_case(kase)
      if errs.empty?
        puts "ok   #{kase['name']}"
      else
        failures += 1
        puts "FAIL #{kase['name']}:"
        puts errs.join("\n")
      end
      next
    end

    actual = as_plain(actual_for(kase))
    expected = kase["expected"]
    if STRUCT_FUNCTIONS.include?(kase["function"])
      expected = expected.transform_keys(&:to_s)
      # Structs may carry extra fields the fixture doesn't assert on --
      # only compare keys the fixture actually specifies.
      actual = expected.keys.to_h { |k| [k, actual[k]] }
    end

    if actual == expected
      puts "ok   #{kase['name']}"
    else
      failures += 1
      puts "FAIL #{kase['name']}: expected #{expected.inspect}, got #{actual.inspect}"
    end
  end

  puts
  if failures.positive?
    puts "#{failures} case(s) failed"
    exit 1
  end
  puts "All #{cases.length} case(s) passed"
end

main
