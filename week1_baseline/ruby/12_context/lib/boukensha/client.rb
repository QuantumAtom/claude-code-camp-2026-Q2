require "net/http"
require "json"
require "openssl"
require "opentelemetry/sdk"

module Boukensha
  class Client
    RETRYABLE_STATUS_CODES = [408, 409, 429, 500, 502, 503, 504].freeze
    TRANSIENT_ERRORS = [
      EOFError,
      Errno::ECONNRESET,
      Errno::ECONNREFUSED,
      Net::OpenTimeout,
      Net::ReadTimeout,
      OpenSSL::SSL::SSLError,
      SocketError,
      Timeout::Error
    ].freeze
    MAX_RETRIES = 3
    BASE_RETRY_DELAY = 0.5

    def initialize(builder)
      @builder = builder
    end

    def call(max_output_tokens: 1024, tools: nil)
      Boukensha.tracer.in_span('llm.call') do |span|
        span.set_attribute('llm.url', @builder.url)
        span.set_attribute('llm.max_output_tokens', max_output_tokens)
        span.set_attribute('gen_ai.request.model', @builder.backend.model)
        span.set_attribute('gen_ai.operation.name', 'chat')

        uri          = URI(@builder.url)
        http         = Net::HTTP.new(uri.host, uri.port)
        http.use_ssl = uri.scheme == "https"
        http.verify_mode = OpenSSL::SSL::VERIFY_PEER

        request      = Net::HTTP::Post.new(uri, @builder.headers)
        request.body = @builder.to_api_payload(max_output_tokens: max_output_tokens, tools: tools).to_json
        span.set_attribute('gen_ai.prompt', request.body)

        attempts = 0
        response = nil

        loop do
          attempts += 1

          begin
            response = http.request(request)
          rescue *TRANSIENT_ERRORS => e
            raise ApiError, "API request failed after #{attempts} attempts: #{e.class}: #{e.message}" if attempts > MAX_RETRIES

            sleep retry_delay(attempts)
            next
          end

          if retryable_response?(response) && attempts <= MAX_RETRIES
            sleep retry_delay(attempts)
            next
          end

          break
        end

        span.set_attribute('llm.attempts', attempts)
        span.set_attribute('llm.status_code', response.code.to_i)

        unless response.is_a?(Net::HTTPSuccess)
          raise ApiError, "API request failed after #{attempts} attempt#{'s' unless attempts == 1} (#{response.code}): #{response.body}"
        end

        span.set_attribute('gen_ai.completion', response.body)

        body  = JSON.parse(response.body)
        usage = body["usage"] || {}
        span.set_attribute('gen_ai.usage.input_tokens', usage["input_tokens"]) if usage["input_tokens"]
        span.set_attribute('gen_ai.usage.output_tokens', usage["output_tokens"]) if usage["output_tokens"]
        # body["model"]/body["stop_reason"] are Anthropic's response shape --
        # same caveat as gen_ai.usage.* above: OpenAI's Responses API happens
        # to match, but Gemini (usageMetadata/finishReason nested under
        # candidates) and Ollama (no stop_reason field at all) won't populate
        # these two attributes.
        span.set_attribute('gen_ai.response.model', body["model"]) if body["model"]
        span.set_attribute('gen_ai.response.finish_reasons', [body["stop_reason"]]) if body["stop_reason"]

        body
      rescue StandardError
        # Tracer#in_span already records the exception and sets the span's
        # error status for any exception that escapes this block (see
        # opentelemetry-api's Tracer#in_span) -- no need to duplicate that
        # here. This rescue exists only to guarantee
        # gen_ai.response.finish_reasons is present even on failure; the
        # success path above only reaches its own finish_reasons line after
        # a full round trip, so this and that are mutually exclusive.
        span.set_attribute('gen_ai.response.finish_reasons', ['error'])
        raise
      end
    end

    private

    def retryable_response?(response)
      RETRYABLE_STATUS_CODES.include?(response.code.to_i)
    end

    def retry_delay(attempt)
      BASE_RETRY_DELAY * (2**(attempt - 1))
    end
  end
end
