"""All LLM prompts, in English, versioned.

Why English prompts with a separate output-language field: models keep
schemas and prohibitions more reliably in English, while the answer
language is an explicit parameter. Non-English prompts were producing
format drift and, worse, silent invention of numbers.

Every prompt here follows the project contract:
  - the model is an EDITOR, never a source of facts;
  - numbers may only be copied from the given facts, never inferred;
  - "not_stated" is always a legal answer;
  - output is strict JSON so the validator can check it mechanically.
"""

PROMPT_VERSION = 3

SYSTEM_GROUNDED = (
    "You are a figure-skating coaching assistant working under a strict "
    "grounding contract. You NEVER invent facts, numbers, drill names, "
    "sets, reps, seconds, degrees or revolutions. Every number you output "
    "must appear verbatim in the provided facts. If information is "
    'missing, output the literal string "not_stated" instead of '
    "guessing. You output strict JSON only, no prose, no markdown."
)

# --- 1. Turn source narration into clean numbered instructions ---
MAKE_STEPS = """Rewrite the drill instruction as 2-4 short numbered steps in
execution order.

HARD RULES
- Only actions that appear in SOURCE. Add nothing.
- Never invent numbers (sets, reps, seconds, degrees).
- Use correct figure-skating terminology in {lang}: blade, edge,
  Biellmann, camel spin, toe pick.
- Keep each step under 12 words, imperative mood.

Return strict JSON: {{"steps":["step 1","step 2"]}}

DRILL: {name}
SOURCE (narration/subtitles):
{source}"""

# --- 2. Short answer to a user question, built only from retrieved sources ---
ANSWER_QUESTION = """Answer the skater's question using ONLY the SOURCES below.

HARD RULES
- 2-4 short sentences. No headings, no lists, no markup, no citations in text.
- Only facts present in SOURCES. If SOURCES do not answer it, say so plainly.
- Never invent numbers. Copy them exactly if you use them.
- Speak to a skater or parent: simple words, practical.
- Output language: {lang}.

Return strict JSON: {{"answer":"..."}}

QUESTION: {question}

SOURCES:
{sources}"""
