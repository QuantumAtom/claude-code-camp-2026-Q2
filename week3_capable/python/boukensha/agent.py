import os
import uuid

from opentelemetry import baggage, context as otel_context, trace
from opentelemetry.trace import Status, StatusCode

from .errors import ApiError
from .logger import Logger
from .telemetry import tracer


class Agent:
    # There's currently only one agent type in this codebase; this is the
    # stable gen_ai.agent.name value used for every run.
    AGENT_NAME = "boukensha"

    MAX_ITERATIONS = 25
    WRAP_UP_OUTPUT_TOKENS = 400
    WRAP_UP_DIRECTIVE = (
        "You have reached your action limit for this turn. Do not call any more tools.\n"
        "Briefly summarize what you accomplished, what is still unfinished, and the\n"
        "single next action you would take."
    )

    def __init__(self, *, context, registry, builder, client, logger=None,
                 max_iterations=None, max_turn_tokens=None, max_output_tokens=None):
        self.context = context
        self.registry = registry
        self.builder = builder
        self.client = client
        # logger=None (not logger=Logger()) is deliberate: a literal default
        # argument is evaluated once at class-definition time, which would
        # share a single Logger (and its open file) across every Agent that
        # doesn't pass its own.
        self.logger = logger if logger is not None else Logger()
        self.max_iterations = int(max_iterations) if max_iterations else self.MAX_ITERATIONS
        self.max_turn_tokens = int(max_turn_tokens or 0)  # 0 = disabled
        self.max_output_tokens = max_output_tokens
        self.iteration = 0

    # Conversation id is generated once per run: reuses the logger's session
    # id when one exists (so the Honeycomb trace and the .jsonl log file
    # correlate under the same id), otherwise falls back to a fresh uuid.
    # It's pushed into OTel Baggage before the invoke_agent span opens, so
    # ConversationSpanProcessor.on_start can stamp it onto every span created
    # for the rest of this run -- llm.call and tool.dispatch included --
    # without conversation_id having to be threaded through their signatures.
    def run(self):
        conversation_id = str(getattr(self.logger, "session_id", None) or uuid.uuid4())
        baggage_context = baggage.set_baggage("gen_ai.conversation.id", conversation_id)

        # No request/session concept exists in this single-operator CLI
        # agent, so the environment is the closest stand-in for "user
        # context." Absent -> skipped silently, both here and in
        # ConversationSpanProcessor.
        user_id = os.environ.get("BOUKENSHA_USER_ID")
        if user_id:
            baggage_context = baggage.set_baggage("enduser.id", user_id, context=baggage_context)

        token = otel_context.attach(baggage_context)
        try:
            with tracer().start_as_current_span("invoke_agent") as span:
                span.set_attribute("gen_ai.operation.name", "invoke_agent")
                span.set_attribute("gen_ai.agent.name", self.AGENT_NAME)
                if user_id:
                    span.set_attribute("enduser.id", user_id)

                return self._run_loop()
                # No explicit except here: an exception escaping this block
                # (e.g. ApiError from self.client.call after retries are
                # exhausted) is already recorded and marked as error status
                # on this invoke_agent span by start_as_current_span itself.
                # The one case that genuinely needs help is a tool failure
                # that's handled in-band rather than re-raised -- see the
                # except in _handle_tool_calls below.
        finally:
            otel_context.detach(token)

    def _run_loop(self):
        self.context.reset_turn_tokens()
        self._compact_if_needed()

        while True:
            # Two independent ceilings; stop at whichever trips first. Limits
            # are *trigger thresholds*, not hard caps: when one is reached we
            # stop starting new work iterations and make exactly one terminal
            # wind-down call (counted in tokens, but not as another iteration).
            if self._iteration_limit_reached():
                self.logger.limit_reached(kind="max_iterations", n=self.iteration, max=self.max_iterations)
                return self._wrap_up("max_iterations")
            if self._token_limit_reached():
                self.logger.limit_reached(kind="max_tokens", n=self.context.turn_tokens, max=self.max_turn_tokens)
                return self._wrap_up("max_tokens")

            self.iteration += 1
            self.logger.iteration(n=self.iteration, max=self.max_iterations)
            self.logger.prompt(messages=self.context.messages, tools=self.context.tools,
                                context_window=self.context.context_window)

            response = self.client.call(**self._call_opts())
            self.logger.raw(data=response)
            parsed = self.builder.parse_response(response)
            self._record_usage(response)
            self._log_reasoning(parsed["content"])

            if parsed["stop_reason"] == "tool_use":
                self._handle_tool_calls(parsed["content"], response)
            else:
                text = self._extract_text(parsed["content"])
                self.logger.response(text=text, usage=response.get("usage"), stop_reason=parsed["stop_reason"])
                self.logger.turn_end(reason="completed", iterations=self.iteration, tokens=self.context.turn_tokens)
                self.context.add_message("assistant", text)
                return text

    def _iteration_limit_reached(self):
        return self.max_iterations > 0 and self.iteration >= self.max_iterations

    def _token_limit_reached(self):
        return self.max_turn_tokens > 0 and self.context.turn_tokens >= self.max_turn_tokens

    def _call_opts(self):
        return {"max_output_tokens": self.max_output_tokens} if self.max_output_tokens else {}

    # Add this call's input+output to the cumulative turn total (the spend
    # budget) and refresh the known context size from input_tokens
    # (compaction pressure). The trigger is evaluated on pre-wrap-up spend;
    # the reported total includes the wind-down call too.
    def _record_usage(self, response):
        usage = response.get("usage") or {}
        self.context.add_turn_tokens(usage.get("input_tokens"), usage.get("output_tokens"))
        self.context.update_tokens(usage.get("input_tokens"))

    def _compact_if_needed(self):
        if not self.context.needs_compaction():
            return

        before = self.context.current_tokens
        dropped = self.context.compact_messages()
        self.logger.compaction(before=before, dropped=dropped, context_window=self.context.context_window)

    # One final, tools-disabled model call so the agent ends the turn in
    # character rather than aborting. Runs *outside* the counted loop: it
    # never re-checks the limits (so it cannot re-trigger) and does not
    # increment self.iteration, though its tokens still count toward the
    # reported turn total. Falls back to a deterministic message if the
    # call fails.
    def _wrap_up(self, reason):
        self.context.add_message("user", self.WRAP_UP_DIRECTIVE)
        try:
            response = self.client.call(tools=[], max_output_tokens=self.WRAP_UP_OUTPUT_TOKENS)
            parsed = self.builder.parse_response(response)
            text = self._extract_text(parsed["content"])
            text = text if text.strip() else self._fallback_message(reason)
            self._record_usage(response)
            self.logger.response(text=text, usage=response.get("usage"), stop_reason=parsed["stop_reason"])
            self.logger.turn_end(reason=reason, iterations=self.iteration, tokens=self.context.turn_tokens)
            self.context.add_message("assistant", text)
            return text
        except ApiError:
            msg = self._fallback_message(reason)
            self.logger.turn_end(reason=reason, iterations=self.iteration, tokens=self.context.turn_tokens)
            self.context.add_message("assistant", msg)
            return msg

    def _fallback_message(self, reason):
        return (
            f"I reached my {self.max_iterations}-action limit for this turn before "
            f"finishing ({reason}). Ask me to continue and I'll pick up from here."
        )

    @staticmethod
    def _extract_text(content):
        return "\n".join(b["text"] for b in content if b.get("type") == "text")

    # Emit one `reasoning` event per reasoning block so the viewer can show
    # the model's thinking as a first-class step. Empty, non-redacted blocks
    # are skipped to avoid noise (a redacted/omitted block still renders,
    # since it tells the viewer "the model thought here").
    def _log_reasoning(self, content):
        for block in content:
            if block.get("type") != "reasoning":
                continue

            redacted = block.get("redacted") is True
            text = str(block.get("text") or "")
            if not text.strip() and not redacted:
                continue

            self.logger.reasoning(text=text, redacted=redacted)

    def _handle_tool_calls(self, content, response):
        tool_calls = [b for b in content if b.get("type") == "tool_use"]

        # Log any preamble text that accompanied the tool call (carries no
        # usage -- the placeholder below owns the turn's usage chip), then
        # the placeholder.
        preamble = self._extract_text(content)
        if preamble.strip():
            self.logger.plan(text=preamble)
        suffix = "s" if len(tool_calls) != 1 else ""
        self.logger.response(
            text=f"(tool use — {len(tool_calls)} call{suffix})",
            usage=response.get("usage"), stop_reason="tool_use",
        )

        self.context.add_message("assistant", content)

        for block in tool_calls:
            name = block["name"]
            args = block["input"]
            use_id = block["id"]

            self.logger.tool_call(name=name, args=args)
            try:
                result = self.registry.dispatch(name, args, tool_call_id=use_id)
                self.logger.tool_result(name=name, result=result, ok=True)
            except Exception as e:
                result = f"ERROR: {type(e).__name__}: {e}"
                self.logger.tool_result(name=name, result=result, ok=False, error=str(e))

                # Registry.dispatch already recorded the exception on its own
                # tool.dispatch span before re-raising; that span has since
                # closed (its context-manager __exit__ ran during unwind),
                # so trace.get_current_span() here resolves to the parent
                # invoke_agent span. This error is handled in-band (fed back
                # to the model as a result string, not re-raised) so it
                # would otherwise never touch invoke_agent's status at all.
                trace.get_current_span().set_status(Status(StatusCode.ERROR, f"tool {name} failed: {e}"))

            self.context.add_message("tool_result", str(result), tool_use_id=use_id)
