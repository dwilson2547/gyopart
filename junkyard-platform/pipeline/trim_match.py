"""
Which catalogue trims an NHTSA (or yard) trim string means (matching-v2-design §2.1).

NHTSA trims rarely equal the catalogue's: GM writes "1LT" / "SLT2" / "LT (1LT)" for LT / SLT, others add engine or
drive ("EX-V6", "SEL FWD", "quattro Premium Plus"), some list alternatives ("L/LE/SE/XLE/XSE"), and many carry no trim
at all (Toyota chassis codes "ZZE130L", GM "1500 (1/2 Ton)"). `trims_meant` reads the string against the trims the
candidates actually have and answers only when it is sure: a wrong narrowing can turn into a wrong exact match, while
no answer just leaves the vehicle "one of these".
"""
from __future__ import annotations

import re

_FRACTION = re.compile(r"\b\d/\d\b")                       # "1/2 Ton": a weight class, not two alternatives
_WITH = re.compile(r"\bw/\s*", re.IGNORECASE)                # "w/" is "with", not two alternatives
_OPTIONS = re.compile(r"(?:^|\s)with\s(.*)$", re.IGNORECASE)  # "SEL with Convenience Pkg": options, not trim
_BRACKETED = re.compile(r"\(([^)]*)\)")
_ALTERNATIVES = re.compile(r"\s*[/,]\s*")
_TOKEN_SPLIT = re.compile(r"[^a-z0-9.]+")
_GRADE = re.compile(r"^(?:\d([a-z]{1,4})|([a-z]{1,4})\d)$")  # 1LT, 2LT, 1LS, SLT2

# Words that never count against a match: they describe the engine, drive, body, weight class or transmission.
_NOISE_WORDS = {
    "awd", "fwd", "rwd", "4wd", "2wd", "4x4", "4x2", "4motion", "quattro", "xdrive", "4matic", "sh",
    "auto", "automatic", "manual", "cvt", "ton", "nominal", "sedan", "coupe", "wagon", "hatchback", "convertible",
    "door", "dr", "and",
}
_NOISE = re.compile(
    r"^(?:\d+"                       # bare numbers: "SLE 2", "1500"
    r"|\d\.\d[lt]?"                  # displacement: "2.0T", "1.8"
    r"|[vli]\d{1,2}"                 # cylinders: "V6", "L4", "I4"
    r"|[a-z]{2,4}\d{2,3}[a-z]?"      # Toyota/Honda chassis codes: "ZZE130L", "ACV40L"
    r")$"
)


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _tokens(text: str) -> list[str]:
    return [t.strip(".") for t in _TOKEN_SPLIT.split(text.lower()) if t.strip(".")]


def _effective(token: str, vocab: set[str]) -> str:
    """A token as the catalogue would write it: '1LT' -> 'lt', unless the catalogue has the token itself ('SR5')."""
    if token in vocab or token in _NOISE_WORDS or _NOISE.match(token):
        return token                            # "V6" is a cylinder count, not grade V
    m = _GRADE.match(token)
    return (m.group(1) or m.group(2)) if m else token


def _is_noise(token: str, vocab: set[str]) -> bool:
    return token not in vocab and (token in _NOISE_WORDS or bool(_NOISE.match(token)))


def _one_alternative(text: str, optional: list[str], trims: dict[str, set[str]], vocab: set[str]) -> set[str] | None:
    """The trims one alternative means, or None. `optional` (bracketed words) may help match but never block."""
    words = [_effective(t, vocab) for t in _tokens(text)]
    extra = [_effective(t, vocab) for t in optional]
    have = set(words) | set(extra)
    hits = [name for name, toks in trims.items() if toks and toks <= have]
    if not hits:
        return None
    best = max(len(trims[h]) for h in hits)     # "Premium Plus" over "Premium", "EX-L" over "EX"
    chosen = {h for h in hits if len(trims[h]) == best}
    explained = set().union(*(trims[h] for h in chosen))
    if any(w not in explained and not _is_noise(w, vocab) for w in words):
        return None                             # "LX Premium" vs catalogue LX / LX-P: not sure it is LX
    return chosen


def trims_meant(text: str | None, catalogue_trims) -> set[str] | None:
    """The catalogue trims `text` means; an empty set when it is only noise (it says nothing about the trim);
    None when anything is in doubt, which is what a person or a trim mapping has to settle."""
    names = {t for t in catalogue_trims if t and t.strip()}
    if not text or not text.strip() or not names:
        return None
    exact = {n for n in names if _key(n) == _key(text)}
    if exact:
        return exact                            # also covers catalogue names with a slash ("X/C")
    trims = {n: set(_tokens(n)) for n in names}
    vocab = set().union(*trims.values())

    cleaned = _WITH.sub("with ", _FRACTION.sub(" ", text))
    optional = [t for group in _BRACKETED.findall(cleaned) for t in _tokens(group)]
    cleaned = _BRACKETED.sub(" ", cleaned)
    alternatives = []
    dropped_options = False
    for alt in _ALTERNATIVES.split(cleaned):
        options = _OPTIONS.search(alt)
        if options:
            if any(t in vocab for t in _tokens(options.group(1))):
                return None                     # "w/ Technology R-Line": the options name a trim
            alt = alt[:options.start()]
            dropped_options = True
        # Drop alternatives that are only noise: "LE ASA44L/ASA42L" lists chassis codes, not trims.
        if any(not _is_noise(_effective(t, vocab), vocab) for t in _tokens(alt)):
            alternatives.append(alt)
    if not alternatives:
        return set()                            # noise only: "1500", "ACV40L/GSV40L"
    meant: set[str] = set()
    for alt in alternatives:
        hit = _one_alternative(alt, optional, trims, vocab)
        if hit is None:
            return None                         # "Sport, SXT" with no SXT in the catalogue: it may be the SXT
        meant |= hit
    if dropped_options and any(trims[m] < toks for m in meant for toks in trims.values()):
        return None                             # "EX with leather" vs catalogue EX / EX-L: the options may be the "-L"
    return meant
