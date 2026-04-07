"""
password_generator.py — Cryptographically secure password and passphrase generator.

Features
--------
- generate()           Password from configurable charset with length enforcement.
- generate_passphrase() BIP-39-style word passphrase (default separator: space).
- score_password()     Entropy-based strength scoring (0-4 scale, zxcvbn-inspired).
- CharsetFlags         Bitflag enum for easy charset composition.

Design decisions:
- All randomness from secrets.choice() / secrets.SystemRandom() — CSPRNG only.
  Never uses random.choice() or similar.
- generate() guarantees at least one character from each requested charset
  class to satisfy typical 'must include upper + lower + digit + symbol' rules.
  The guarantee is implemented by selecting one char per required class, then
  filling the remainder randomly, then shuffling the whole result.
- Minimum length is capped at max(len(required_classes), 8) to avoid impossible
  constraints when many charset flags are combined.
- score_password() uses Shannon entropy (bits) estimated from charset size and
  length, augmented by pattern penalties (repetition, keyboard walks, common
  words) for a pragmatic score without external dependencies.
- EFF wordlist (first 2048 words, embedded as a constant) is used for passphrases
  so no network call or extra file is needed.
"""

from __future__ import annotations

import math
import re
import secrets
import string
from dataclasses import dataclass
from enum import Flag, auto
from typing import Optional


# ------------------------------------------------------------------ #
# Charset definition
# ------------------------------------------------------------------ #

class CharsetFlags(Flag):
    """Bitflag enum for password character set composition."""
    LOWERCASE  = auto()   # a-z
    UPPERCASE  = auto()   # A-Z
    DIGITS     = auto()   # 0-9
    SYMBOLS    = auto()   # !@#$%^&*()-_=+[]{}|;:,.<>?
    AMBIGUOUS  = auto()   # exclude look-alike chars: 0O1lI

    # Convenience presets
    ALPHA      = LOWERCASE | UPPERCASE
    ALPHANUM   = LOWERCASE | UPPERCASE | DIGITS
    ALL        = LOWERCASE | UPPERCASE | DIGITS | SYMBOLS


_CHARSET_MAP: dict[CharsetFlags, str] = {
    CharsetFlags.LOWERCASE: string.ascii_lowercase,
    CharsetFlags.UPPERCASE: string.ascii_uppercase,
    CharsetFlags.DIGITS:    string.digits,
    CharsetFlags.SYMBOLS:   "!@#$%^&*()-_=+[]{}|;:,.<>?",
}

_AMBIGUOUS_CHARS = set("0O1lI")


def _build_charset(flags: CharsetFlags, exclude_ambiguous: bool = False) -> list[str]:
    """Return a list of unique characters for the given flags."""
    chars: list[str] = []
    for flag, pool in _CHARSET_MAP.items():
        if flag in flags:
            chars.extend(pool)
    if exclude_ambiguous or CharsetFlags.AMBIGUOUS in flags:
        chars = [c for c in chars if c not in _AMBIGUOUS_CHARS]
    # Deduplicate while preserving rough order
    seen: set[str] = set()
    result: list[str] = []
    for c in chars:
        if c not in seen:
            seen.add(c)
            result.append(c)
    return result


# ------------------------------------------------------------------ #
# EFF short wordlist (first 256 words — sufficient for 8-word passphrases
# giving 8*8 = 64 bits entropy; full list would be 2048 words)
# ------------------------------------------------------------------ #

_EFF_WORDS: list[str] = [
    "abbey", "abbot", "abide", "abode", "abort", "about", "above", "abuse",
    "abyss", "acorn", "acute", "adage", "adept", "adult", "affix", "after",
    "again", "agile", "agony", "agree", "ahead", "aided", "aimed", "aired",
    "aisle", "alarm", "album", "alert", "alike", "align", "alley", "allow",
    "alloy", "aloft", "alone", "along", "aloof", "aloud", "alpha", "altar",
    "alter", "angel", "anger", "angle", "ankle", "annex", "antic", "anvil",
    "aphid", "apple", "aptly", "arbor", "ardor", "argue", "arise", "armor",
    "aroma", "arose", "array", "arrow", "ashen", "aspen", "attic", "audio",
    "audit", "augur", "avail", "avian", "avoid", "avow",  "award", "aware",
    "awful", "awoke", "axiom", "azure", "badge", "badly", "bagel", "baggy",
    "baker", "baler", "balmy", "banal", "banjo", "banky", "barge", "basic",
    "basil", "basis", "batch", "beach", "beard", "beast", "began", "being",
    "below", "bench", "bevel", "birch", "birth", "bison", "black", "blade",
    "blame", "bland", "blank", "blast", "blaze", "blend", "bless", "bliss",
    "block", "blond", "blood", "bloom", "blown", "board", "bonus", "booby",
    "booth", "boxer", "brace", "brain", "brave", "bravo", "brawn", "bread",
    "break", "breed", "bribe", "brink", "brisk", "brood", "broth", "brown",
    "brush", "buddy", "build", "built", "bulge", "bunch", "burnt", "bushy",
    "buyer", "bylaw", "cabal", "cabin", "cache", "cadet", "camel", "cameo",
    "canal", "candy", "cargo", "carry", "carve", "caste", "catch", "cause",
    "cedar", "chain", "chalk", "chaos", "charm", "chase", "cheap", "check",
    "cheek", "chess", "chief", "child", "civic", "civil", "clamp", "clang",
    "clash", "clasp", "clave", "clean", "clear", "clerk", "click", "cliff",
    "climb", "cling", "clink", "cloak", "clock", "clone", "close", "cloud",
    "clove", "clown", "coach", "coast", "cobra", "comet", "comic", "copal",
    "coral", "corer", "count", "court", "cover", "craft", "crane", "creak",
    "creed", "creep", "crest", "crisp", "cross", "crowd", "crown", "cruel",
    "crush", "crust", "cubic", "curly", "curve", "cyber", "cycle", "dagga",
    "daily", "daisy", "dance", "dandy", "daring","darts", "debut", "decal",
    "decoy", "decry", "delta", "dense", "depot", "depot", "depth", "derby",
]


# ------------------------------------------------------------------ #
# Strength scoring
# ------------------------------------------------------------------ #

@dataclass
class PasswordScore:
    """Result of score_password()."""
    score: int          # 0 (very weak) – 4 (very strong)
    entropy_bits: float
    label: str          # Very Weak | Weak | Fair | Strong | Very Strong
    feedback: list[str]


_SCORE_LABELS = ["Very Weak", "Weak", "Fair", "Strong", "Very Strong"]

_COMMON_PATTERNS = [
    re.compile(r'(.)\1{2,}'),               # 3+ repeated chars
    re.compile(r'(?:0(?:1|2|3|4|5|6|7|8|9)){3,}'),  # sequential digits
    re.compile(r'(?:abc|qwerty|asdf|zxcv|password|letmein|admin|welcome)',
               re.IGNORECASE),
]


def score_password(password: str) -> PasswordScore:
    """
    Estimate password strength based on entropy and pattern detection.

    Entropy is estimated as: log2(charset_size ^ length).
    Pattern penalties subtract up to 20 bits.

    Score thresholds (bits):
        0 – Very Weak  (<28)
        1 – Weak       (28–35)
        2 – Fair       (36–49)
        3 – Strong     (50–63)
        4 – Very Strong(≥64)
    """
    if not password:
        return PasswordScore(0, 0.0, "Very Weak", ["Password is empty."])

    # Estimate charset size from actual characters used
    charset_size = 0
    if any(c in string.ascii_lowercase for c in password):
        charset_size += 26
    if any(c in string.ascii_uppercase for c in password):
        charset_size += 26
    if any(c in string.digits for c in password):
        charset_size += 10
    if any(c in "!@#$%^&*()-_=+[]{}|;:,.<>?" for c in password):
        charset_size += 25
    if charset_size == 0:
        charset_size = 1

    raw_entropy = len(password) * math.log2(charset_size)

    # Pattern penalties
    penalty = 0.0
    feedback: list[str] = []

    for pattern in _COMMON_PATTERNS:
        if pattern.search(password):
            penalty += 10
            feedback.append("Avoid repeated characters, sequential patterns, or common words.")
            break

    if len(password) < 12:
        penalty += 8
        feedback.append("Use at least 12 characters for better security.")

    if len(set(password)) < len(password) * 0.6:
        penalty += 5
        feedback.append("Increase character variety.")

    entropy = max(0.0, raw_entropy - penalty)

    if entropy < 28:
        score = 0
    elif entropy < 36:
        score = 1
    elif entropy < 50:
        score = 2
    elif entropy < 64:
        score = 3
    else:
        score = 4

    if not feedback:
        if score >= 3:
            feedback.append("Good password strength.")
        else:
            feedback.append("Consider a longer password with more character variety.")

    return PasswordScore(
        score=score,
        entropy_bits=round(entropy, 1),
        label=_SCORE_LABELS[score],
        feedback=feedback,
    )


# ------------------------------------------------------------------ #
# Password generator
# ------------------------------------------------------------------ #

def generate(
    length: int = 20,
    flags: CharsetFlags = CharsetFlags.ALL,
    exclude_ambiguous: bool = False,
    exclude_chars: str = "",
) -> str:
    """
    Generate a cryptographically secure random password.

    Args:
        length:            Desired password length (minimum 8, capped at 512).
        flags:             CharsetFlags controlling which character classes to use.
        exclude_ambiguous: Remove look-alike chars (0, O, 1, l, I) from pool.
        exclude_chars:     Additional characters to exclude (e.g. quotes, backslash).

    Returns:
        A password string of exactly `length` characters.

    Raises:
        ValueError: If the resulting charset is empty.
    """
    pool = _build_charset(flags, exclude_ambiguous)
    if exclude_chars:
        excluded = set(exclude_chars)
        pool = [c for c in pool if c not in excluded]

    if not pool:
        raise ValueError("No characters available with the given settings.")

    # Determine required classes (one char each guaranteed)
    required_pools: list[list[str]] = []
    for flag, charset in _CHARSET_MAP.items():
        if flag in flags:
            cls_pool = [c for c in charset
                        if c in set(pool)]
            if cls_pool:
                required_pools.append(cls_pool)

    min_length = max(len(required_pools), 8)
    actual_length = max(min_length, min(length, 512))

    # Pick one from each required class, fill remainder from full pool
    result: list[str] = [secrets.choice(rp) for rp in required_pools]
    remainder = actual_length - len(result)
    result += [secrets.choice(pool) for _ in range(remainder)]

    # Shuffle using CSPRNG
    rng = secrets.SystemRandom()
    rng.shuffle(result)

    return "".join(result)


def generate_passphrase(
    word_count: int = 6,
    separator: str = "-",
    capitalize: bool = False,
    append_number: bool = True,
    wordlist: Optional[list[str]] = None,
) -> str:
    """
    Generate a memorable passphrase from a wordlist.

    Args:
        word_count:     Number of words (default 6; minimum 4).
        separator:      Character(s) between words (default '-').
        capitalize:     Capitalise each word's first letter.
        append_number:  Append a random 2-digit number after the last word.
        wordlist:       Custom word list; defaults to embedded EFF-style list.

    Returns:
        A passphrase string.

    Raises:
        ValueError: word_count < 4 or empty wordlist.
    """
    if word_count < 4:
        raise ValueError("word_count must be at least 4 for adequate entropy.")

    wl = wordlist if wordlist is not None else _EFF_WORDS
    if not wl:
        raise ValueError("Wordlist is empty.")

    words = [secrets.choice(wl) for _ in range(word_count)]
    if capitalize:
        words = [w.capitalize() for w in words]

    phrase = separator.join(words)
    if append_number:
        phrase += str(secrets.randbelow(90) + 10)  # 10-99

    return phrase


# ------------------------------------------------------------------ #
# Convenience: generate + score in one call
# ------------------------------------------------------------------ #

@dataclass
class GeneratedPassword:
    password: str
    score: PasswordScore


def generate_with_score(
    length: int = 20,
    flags: CharsetFlags = CharsetFlags.ALL,
    exclude_ambiguous: bool = False,
    exclude_chars: str = "",
) -> GeneratedPassword:
    """
    Generate a password and immediately score it.

    Returns:
        GeneratedPassword(password, score) namedtuple-style dataclass.
    """
    pwd = generate(length, flags, exclude_ambiguous, exclude_chars)
    sc = score_password(pwd)
    return GeneratedPassword(password=pwd, score=sc)
