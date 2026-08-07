# Static model -> capability table.
#
# context_window is a known *model* fact -- the physical input ceiling --
# not a value the user sets. The agent looks it up from its configured
# model id; the user never configures it in settings.yaml. Unknown models
# fall back to a conservative default so an unrecognised id can't silently
# assume a huge window.
#
# NOTE: this table is independent of (and disagrees with) each backend's
# own MODELS[model]["context_window"] -- ported faithfully from Ruby.
# Non-Anthropic models fall through to DEFAULT_CONTEXT_WINDOW regardless
# of their real window; claude-sonnet-4-6/claude-opus-4-8 are listed here
# at 200_000 even though Backends::Anthropic.MODELS lists them at
# 1_000_000. This is a real, unreconciled discrepancy in the source this
# was ported from, preserved as-is rather than silently fixed.
TABLE = {
    "claude-opus-4-8":   {"context_window": 200_000},
    "claude-sonnet-4-6": {"context_window": 200_000},
    "claude-haiku-4-5":  {"context_window": 200_000},
}

DEFAULT_CONTEXT_WINDOW = 32_000


class Models:
    @staticmethod
    def context_window(model):
        entry = TABLE.get(str(model))
        return entry["context_window"] if entry else DEFAULT_CONTEXT_WINDOW
