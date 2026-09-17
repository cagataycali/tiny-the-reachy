"""resolve_emotion: plain English → real library move (pure, no SDK)."""
import importlib.util, pathlib, sys, types

# Load tools/reachy_expression.py standalone (no SDK needed) WITHOUT leaving stubs in sys.modules,
# so the other tests still import the real `tools` package afterwards.
_root = pathlib.Path(__file__).resolve().parents[1]


def _load():
    saved = {k: sys.modules.get(k) for k in ("tools", "tools._reachy_common", "tools.reachy_expression")}
    try:
        pkg = types.ModuleType("tools"); pkg.__path__ = [str(_root / "tools")]; sys.modules["tools"] = pkg
        common = types.ModuleType("tools._reachy_common"); common.get_mini = lambda: None
        common.ok = lambda *a, **k: {}; common.err = lambda *a, **k: {}; sys.modules["tools._reachy_common"] = common
        spec = importlib.util.spec_from_file_location("tools.reachy_expression", _root / "tools" / "reachy_expression.py")
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        return mod
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


rx = _load()

LIB = ("amazed1 anxiety1 attentive1 attentive2 boredom1 boredom2 calming1 cheerful1 come1 confused1 contempt1 "
       "curious1 dance1 dance2 dance3 disgusted1 displeased1 displeased2 downcast1 dying1 electric1 enthusiastic1 "
       "enthusiastic2 exhausted1 fear1 frustrated1 furious1 go_away1 grateful1 helpful1 helpful2 impatient1 "
       "impatient2 incomprehensible2 indifferent1 inquiring1 inquiring2 inquiring3 irritated1 irritated2 laughing1 "
       "laughing2 lonely1 lost1 loving1 no1 no_excited1 no_sad1 oops1 oops2 proud1 proud2 proud3 rage1 relief1 "
       "relief2 reprimand1 reprimand2 reprimand3 resigned1 sad1 sad2 scared1 serenity1 shy1 sleep1 success1 "
       "success2 surprised1 surprised2 thoughtful1 thoughtful2 tired1 uncertain1 uncomfortable1 understanding1 "
       "understanding2 welcoming1 welcoming2 yes1 yes_sad1").split()  # the daemon's list, 2026-09-17 (81)


def test_library_size_pinned():
    assert len(LIB) == 81


def test_exact_names_pass_through():
    for n in ("cheerful1", "dance2", "yes_sad1"):
        assert rx.resolve_emotion(n, LIB) == n


def test_prompt_names_resolve():
    # every name the prompts in tiny.py / thinker_loop.py use
    assert rx.resolve_emotion("happy", LIB) == "cheerful1"
    assert rx.resolve_emotion("curious", LIB) == "curious1"
    assert rx.resolve_emotion("surprised", LIB) == "surprised1"
    assert rx.resolve_emotion("sad", LIB) == "sad1"
    assert rx.resolve_emotion("yes", LIB) == "yes1"
    assert rx.resolve_emotion("no", LIB) == "no1"
    assert rx.resolve_emotion("angry", LIB) == "rage1"


def test_suffix_and_prefix_fallbacks():
    assert rx.resolve_emotion("displeased", LIB) == "displeased1"
    assert rx.resolve_emotion("incomprehensible", LIB) == "incomprehensible2"
    assert rx.resolve_emotion("Go Away", LIB) == "go_away1"


def test_every_alias_target_exists():
    missing = {k: v for k, v in rx.EMOTION_ALIASES.items() if v not in LIB}
    assert not missing, missing


def test_unknown_is_none():
    assert rx.resolve_emotion("teleport", LIB) is None
    assert rx.resolve_emotion("", LIB) is None
