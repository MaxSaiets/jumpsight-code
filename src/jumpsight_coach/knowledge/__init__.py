"""Knowledge corpus and retrieval for the skating chat.

    python -m jumpsight_coach.knowledge build     # build the corpus and embeddings
    python -m jumpsight_coach.knowledge ask "how is under-rotation called?"

Corpus sources: the original knowledge base (drills, causes, science,
methodology, bibliography) and English Wikipedia pages on jumps and judging
(CC BY-SA). The corpus and its embeddings are written to
STATE_DIR/kb_cache/ and are never stored in git. Without them the chat still
answers through its structured lookups and says how to build the index.

Modules: corpus (sources), index (build, embeddings, warm-up), lexical (BM25 fallback),
lookups_* (deterministic answers by topic), validate (answer checks), answer (ask).
This package re-exports every name that other modules and tests use, and mirrors
assignments on the package into the modules that read them.
"""

from __future__ import annotations

from jumpsight_core.facade import install_facade

from .. import embed
from ..embed import EMBED_DIM, EMBED_MODEL
from . import answer, corpus, index, lexical, lookups_app, lookups_isu, lookups_jumps, lookups_training, validate
from .answer import (
    _MESSAGES,
    _NO_INDEX,
    _PERSONAL,
    _user_context,
    ask,
)
from .corpus import (
    _BUILD_HINT,
    _TOPIC,
    CACHE_DIR,
    CORPUS,
    EMB,
    KB,
    WIKI_EN,
    CorpusMissing,
    _chunk,
    _kb_rows,
    _kb_yaml,
    _on_topic,
    _wiki_text,
)
from .index import (
    _FALLBACK_LOCK,
    _FALLBACK_READY,
    _FALLBACK_WAIT_S,
    _digest,
    _embed,
    _load,
    _m,
    build,
    warm_fallback,
)
from .lexical import (
    _LEX,
    _LEX_STOP,
    _LEX_SUFFIX,
    _lex_stem,
    _lex_tokens,
    _lexical_hits,
)
from .lookups_app import (
    _ABOUT_Q,
    _AIRTIME_Q,
    _APP_Q,
    _COACH_Q,
    _COUNT_EN,
    _FEAR,
    _GEAR,
    _LEARN_TIME_Q,
    _MY,
    _MY_JUMP,
    _OUT_OF_SCOPE,
    _UNSURE,
    _about_lookup,
    _app_lookup,
    _my_jump_lookup,
    _personal_data_lookup,
    _personal_lookup,
    _scope_lookup,
    _sourced_lookup,
    _unsure_lookup,
)
from .lookups_isu import (
    _COUNT_WORDS,
    _EN_COUNT,
    _EN_JUMP_CODE,
    _GLOSSARY,
    _ISU_MARKS,
    _ISU_REF,
    _JUMP_WORDS,
    _glossary_lookup,
    _harder_lookup,
    _isu_lookup,
    _isu_marks_lookup,
    _lutz_flip_lookup,
    _worth_lookup,
)
from .lookups_jumps import (
    _JUMP_Q,
    _JUMPS_EN,
    _NAMES_RE,
    _ORDER_Q,
    _compare_lookup,
    _jump_def_lookup,
    _order_lookup,
)
from .lookups_training import (
    _DRILL_WORDS,
    _ERR_EN,
    _ERR_WORDS,
    _EVIDENCE_EN,
    _FIX_INTENT,
    _METHOD,
    _OFFICE,
    _OFFICE_TARGETS,
    _PAIN,
    _SCIENCE_TOPICS,
    _drill_lookup,
    _error_fix_lookup,
    _methodology_lookup,
    _office_lookup,
    _rest_lookup,
    _safety_lookup,
    _science_lookup,
)
from .validate import (
    _PARA_STOP,
    _grounded_paraphrase,
    _tidy_excerpt,
)

install_facade(
    __name__, (answer, corpus, index, lexical, lookups_app, lookups_isu, lookups_jumps, lookups_training, validate)
)

__all__ = [
    "CACHE_DIR",
    "CORPUS",
    "CorpusMissing",
    "EMB",
    "EMBED_DIM",
    "EMBED_MODEL",
    "KB",
    "WIKI_EN",
    "_ABOUT_Q",
    "_AIRTIME_Q",
    "_APP_Q",
    "_BUILD_HINT",
    "_COACH_Q",
    "_COUNT_EN",
    "_COUNT_WORDS",
    "_DRILL_WORDS",
    "_EN_COUNT",
    "_EN_JUMP_CODE",
    "_ERR_EN",
    "_ERR_WORDS",
    "_EVIDENCE_EN",
    "_FALLBACK_LOCK",
    "_FALLBACK_READY",
    "_FALLBACK_WAIT_S",
    "_FEAR",
    "_FIX_INTENT",
    "_GEAR",
    "_GLOSSARY",
    "_ISU_MARKS",
    "_ISU_REF",
    "_JUMPS_EN",
    "_JUMP_Q",
    "_JUMP_WORDS",
    "_LEARN_TIME_Q",
    "_LEX",
    "_LEX_STOP",
    "_LEX_SUFFIX",
    "_MESSAGES",
    "_METHOD",
    "_MY",
    "_MY_JUMP",
    "_NAMES_RE",
    "_NO_INDEX",
    "_OFFICE",
    "_OFFICE_TARGETS",
    "_ORDER_Q",
    "_OUT_OF_SCOPE",
    "_PAIN",
    "_PARA_STOP",
    "_PERSONAL",
    "_SCIENCE_TOPICS",
    "_TOPIC",
    "_UNSURE",
    "_about_lookup",
    "_app_lookup",
    "_chunk",
    "_compare_lookup",
    "_digest",
    "_drill_lookup",
    "_embed",
    "_error_fix_lookup",
    "_glossary_lookup",
    "_grounded_paraphrase",
    "_harder_lookup",
    "_isu_lookup",
    "_isu_marks_lookup",
    "_jump_def_lookup",
    "_kb_rows",
    "_kb_yaml",
    "_lex_stem",
    "_lex_tokens",
    "_lexical_hits",
    "_load",
    "_lutz_flip_lookup",
    "_m",
    "_methodology_lookup",
    "_my_jump_lookup",
    "_office_lookup",
    "_on_topic",
    "_order_lookup",
    "_personal_data_lookup",
    "_personal_lookup",
    "_rest_lookup",
    "_safety_lookup",
    "_science_lookup",
    "_scope_lookup",
    "_sourced_lookup",
    "_tidy_excerpt",
    "_unsure_lookup",
    "_user_context",
    "_wiki_text",
    "_worth_lookup",
    "ask",
    "build",
    "embed",
    "warm_fallback",
]
