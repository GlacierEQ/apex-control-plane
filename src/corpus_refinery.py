from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

SPAN_NAMESPACE = uuid.UUID("8143dd75-3c71-45c4-9561-0404c451c36f")

LEVEL_ORDER = {
    "message": 0,
    "paragraph": 1,
    "sentence": 2,
    "phrase": 3,
    "token": 4,
}

_DATE_RE = re.compile(
    r"\b(?:"
    r"(?:19|20)\d{2}-\d{1,2}-\d{1,2}"
    r"|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+\d{1,2}(?:,\s*(?:19|20)\d{2})?"
    r")\b",
    re.IGNORECASE,
)
_TIME_RE = re.compile(r"\b(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?(?:\s*[AP]M)?\b", re.IGNORECASE)
_DOCKET_RE = re.compile(r"\b(?:Dkt\.?|Docket|ECF|Doc(?:ument)?\.?)\s*#?\s*\d+\b", re.IGNORECASE)
_CITATION_RE = re.compile(
    r"\b(?:HRS|HRE|FRCP|Fed\.?\s*R\.?\s*Civ\.?\s*P\.?|Rule)\s*§?\s*\d+(?:\.\d+)*(?:\([a-z0-9]+\))*",
    re.IGNORECASE,
)
_QUOTE_RE = re.compile(r'["“][^"”]{8,}["”]')
_CAP_ENTITY_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}\b")
_WORD_RE = re.compile(r"\b[\w’'-]+\b", re.UNICODE)
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])(?:[\"'”’)\]]*)\s+(?=(?:[\"'“‘(\[]*)[A-Z0-9])")
_PARAGRAPH_GAP_RE = re.compile(r"\n[ \t]*\n+")
_PHRASE_SPLIT_RE = re.compile(r"(?<=[,;:])\s+|\s+[—–-]\s+")


@dataclass(frozen=True)
class RefineryPolicy:
    """Controls progressive enrichment depth without restricting source retrieval."""

    sentence_interest_threshold: float = 0.30
    phrase_interest_threshold: float = 0.58
    token_interest_threshold: float = 0.80
    vector_interest_threshold: float = 0.42
    min_sentence_chars: int = 12
    min_phrase_chars: int = 8
    max_phrase_chars: int = 260

    def __post_init__(self) -> None:
        for name in (
            "sentence_interest_threshold",
            "phrase_interest_threshold",
            "token_interest_threshold",
            "vector_interest_threshold",
        ):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")


@dataclass(frozen=True)
class TextSpan:
    span_id: str
    journal_entry_id: str
    parent_span_id: str | None
    level: str
    ordinal: int
    start_char: int
    end_char: int
    text: str
    text_sha256: str
    interest_score: float
    vector_candidate: bool
    source_anchor: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.level not in LEVEL_ORDER:
            raise ValueError(f"unsupported span level: {self.level}")
        if self.start_char < 0 or self.end_char < self.start_char:
            raise ValueError("invalid character bounds")
        if self.end_char - self.start_char != len(self.text):
            raise ValueError("text length does not match character bounds")


@dataclass(frozen=True)
class TagCandidate:
    span_id: str
    tag_key: str
    matched_text: str
    start_char: int
    end_char: int
    confidence: float = 1.0


@dataclass(frozen=True)
class RefineryResult:
    journal_entry_id: str
    source_sha256: str
    spans: tuple[TextSpan, ...]
    tags: tuple[TagCandidate, ...]

    @property
    def vector_candidates(self) -> tuple[TextSpan, ...]:
        return tuple(span for span in self.spans if span.vector_candidate)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_span_id(
    journal_entry_id: str,
    level: str,
    start_char: int,
    end_char: int,
    text_sha256: str,
) -> str:
    material = "\x1f".join(
        [journal_entry_id, level, str(start_char), str(end_char), text_sha256]
    )
    return str(uuid.uuid5(SPAN_NAMESPACE, material))


def _iter_nonempty_ranges(text: str, splitter: re.Pattern[str]) -> Iterable[tuple[int, int]]:
    cursor = 0
    for match in splitter.finditer(text):
        start, end = cursor, match.start()
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if start < end:
            yield start, end
        cursor = match.end()

    start, end = cursor, len(text)
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    if start < end:
        yield start, end


def paragraph_ranges(text: str) -> list[tuple[int, int]]:
    return list(_iter_nonempty_ranges(text, _PARAGRAPH_GAP_RE))


def sentence_ranges(text: str, base_start: int = 0) -> list[tuple[int, int]]:
    return [
        (base_start + start, base_start + end)
        for start, end in _iter_nonempty_ranges(text, _SENTENCE_BOUNDARY_RE)
    ]


def phrase_ranges(text: str, base_start: int = 0) -> list[tuple[int, int]]:
    return [
        (base_start + start, base_start + end)
        for start, end in _iter_nonempty_ranges(text, _PHRASE_SPLIT_RE)
    ]


def token_ranges(text: str, base_start: int = 0) -> list[tuple[int, int]]:
    return [
        (base_start + match.start(), base_start + match.end())
        for match in _WORD_RE.finditer(text)
    ]


def _normalized_aliases(tag_rules: Mapping[str, Sequence[str]]) -> dict[str, tuple[str, ...]]:
    normalized: dict[str, tuple[str, ...]] = {}
    for key, aliases in tag_rules.items():
        cleaned = tuple(
            sorted(
                {alias.strip() for alias in aliases if alias and alias.strip()},
                key=len,
                reverse=True,
            )
        )
        if cleaned:
            normalized[key.strip()] = cleaned
    return normalized


def tag_matches(text: str, tag_rules: Mapping[str, Sequence[str]]) -> list[tuple[str, str, int, int]]:
    matches: list[tuple[str, str, int, int]] = []
    for tag_key, aliases in _normalized_aliases(tag_rules).items():
        seen_ranges: set[tuple[int, int]] = set()
        for alias in aliases:
            pattern = re.compile(rf"(?<![\w]){re.escape(alias)}(?![\w])", re.IGNORECASE)
            for match in pattern.finditer(text):
                bounds = (match.start(), match.end())
                if bounds in seen_ranges:
                    continue
                seen_ranges.add(bounds)
                matches.append((tag_key, match.group(0), match.start(), match.end()))
    matches.sort(key=lambda item: (item[2], item[3], item[0]))
    return matches


def interest_score(text: str, *, tag_hit_count: int = 0) -> float:
    """Score routing value, not truth or importance to the Operator."""

    if not text.strip():
        return 0.0

    score = 0.0
    length = len(text.strip())
    if length >= 40:
        score += 0.08
    if length >= 120:
        score += 0.06
    if length >= 300:
        score += 0.04
    if "?" in text:
        score += 0.04
    if _DATE_RE.search(text):
        score += 0.12
    if _TIME_RE.search(text):
        score += 0.06
    if _DOCKET_RE.search(text):
        score += 0.16
    if _CITATION_RE.search(text):
        score += 0.16
    if _QUOTE_RE.search(text):
        score += 0.08

    entity_like = len(_CAP_ENTITY_RE.findall(text))
    score += min(entity_like * 0.05, 0.15)
    score += min(tag_hit_count * 0.18, 0.42)
    return round(min(score, 1.0), 4)


def _build_span(
    *,
    journal_entry_id: str,
    parent_span_id: str | None,
    level: str,
    ordinal: int,
    start_char: int,
    end_char: int,
    source_text: str,
    score: float,
    vector_threshold: float,
    source_anchor: Mapping[str, object] | None = None,
) -> TextSpan:
    text = source_text[start_char:end_char]
    digest = sha256_text(text)
    return TextSpan(
        span_id=stable_span_id(journal_entry_id, level, start_char, end_char, digest),
        journal_entry_id=journal_entry_id,
        parent_span_id=parent_span_id,
        level=level,
        ordinal=ordinal,
        start_char=start_char,
        end_char=end_char,
        text=text,
        text_sha256=digest,
        interest_score=score,
        vector_candidate=score >= vector_threshold,
        source_anchor=dict(source_anchor or {}),
    )


def refine_entry(
    journal_entry_id: str,
    text: str,
    *,
    tag_rules: Mapping[str, Sequence[str]] | None = None,
    policy: RefineryPolicy | None = None,
    source_anchor: Mapping[str, object] | None = None,
) -> RefineryResult:
    """Build progressively finer derived spans over one immutable journal entry.

    Character offsets always point into the supplied source string. Annotation
    depth is an enrichment decision only. It never limits access to source text.
    """

    policy = policy or RefineryPolicy()
    rules = tag_rules or {}
    spans: list[TextSpan] = []
    tags: list[TagCandidate] = []

    whole_matches = tag_matches(text, rules)
    message_score = interest_score(text, tag_hit_count=len(whole_matches))
    message = _build_span(
        journal_entry_id=journal_entry_id,
        parent_span_id=None,
        level="message",
        ordinal=0,
        start_char=0,
        end_char=len(text),
        source_text=text,
        score=message_score,
        vector_threshold=policy.vector_interest_threshold,
        source_anchor=source_anchor,
    )
    spans.append(message)

    for paragraph_ordinal, (p_start, p_end) in enumerate(paragraph_ranges(text)):
        paragraph_text = text[p_start:p_end]
        p_matches = tag_matches(paragraph_text, rules)
        p_score = interest_score(paragraph_text, tag_hit_count=len(p_matches))
        paragraph = _build_span(
            journal_entry_id=journal_entry_id,
            parent_span_id=message.span_id,
            level="paragraph",
            ordinal=paragraph_ordinal,
            start_char=p_start,
            end_char=p_end,
            source_text=text,
            score=p_score,
            vector_threshold=policy.vector_interest_threshold,
            source_anchor=source_anchor,
        )
        spans.append(paragraph)
        tags.extend(
            TagCandidate(
                span_id=paragraph.span_id,
                tag_key=tag_key,
                matched_text=matched_text,
                start_char=p_start + local_start,
                end_char=p_start + local_end,
            )
            for tag_key, matched_text, local_start, local_end in p_matches
        )

        for sentence_ordinal, (s_start, s_end) in enumerate(sentence_ranges(paragraph_text, p_start)):
            sentence_text = text[s_start:s_end]
            if len(sentence_text.strip()) < policy.min_sentence_chars:
                continue
            s_matches = tag_matches(sentence_text, rules)
            s_score = interest_score(sentence_text, tag_hit_count=len(s_matches))
            if s_score < policy.sentence_interest_threshold:
                continue

            sentence = _build_span(
                journal_entry_id=journal_entry_id,
                parent_span_id=paragraph.span_id,
                level="sentence",
                ordinal=sentence_ordinal,
                start_char=s_start,
                end_char=s_end,
                source_text=text,
                score=s_score,
                vector_threshold=policy.vector_interest_threshold,
                source_anchor=source_anchor,
            )
            spans.append(sentence)
            tags.extend(
                TagCandidate(
                    span_id=sentence.span_id,
                    tag_key=tag_key,
                    matched_text=matched_text,
                    start_char=s_start + local_start,
                    end_char=s_start + local_end,
                )
                for tag_key, matched_text, local_start, local_end in s_matches
            )

            if s_score < policy.phrase_interest_threshold:
                continue

            for phrase_ordinal, (ph_start, ph_end) in enumerate(phrase_ranges(sentence_text, s_start)):
                phrase_text = text[ph_start:ph_end]
                if not (policy.min_phrase_chars <= len(phrase_text.strip()) <= policy.max_phrase_chars):
                    continue
                ph_matches = tag_matches(phrase_text, rules)
                ph_score = interest_score(phrase_text, tag_hit_count=len(ph_matches))
                if ph_score < policy.phrase_interest_threshold and not ph_matches:
                    continue

                phrase = _build_span(
                    journal_entry_id=journal_entry_id,
                    parent_span_id=sentence.span_id,
                    level="phrase",
                    ordinal=phrase_ordinal,
                    start_char=ph_start,
                    end_char=ph_end,
                    source_text=text,
                    score=max(ph_score, s_score if ph_matches else ph_score),
                    vector_threshold=policy.vector_interest_threshold,
                    source_anchor=source_anchor,
                )
                spans.append(phrase)
                phrase_tags = [
                    TagCandidate(
                        span_id=phrase.span_id,
                        tag_key=tag_key,
                        matched_text=matched_text,
                        start_char=ph_start + local_start,
                        end_char=ph_start + local_end,
                    )
                    for tag_key, matched_text, local_start, local_end in ph_matches
                ]
                tags.extend(phrase_tags)

                if phrase.interest_score < policy.token_interest_threshold or not phrase_tags:
                    continue

                for token_ordinal, (t_start, t_end) in enumerate(token_ranges(phrase_text, ph_start)):
                    token_text = text[t_start:t_end]
                    overlapping_tags = [
                        candidate.tag_key
                        for candidate in phrase_tags
                        if t_start < candidate.end_char and t_end > candidate.start_char
                    ]
                    if not overlapping_tags:
                        continue
                    token = _build_span(
                        journal_entry_id=journal_entry_id,
                        parent_span_id=phrase.span_id,
                        level="token",
                        ordinal=token_ordinal,
                        start_char=t_start,
                        end_char=t_end,
                        source_text=text,
                        score=phrase.interest_score,
                        vector_threshold=policy.vector_interest_threshold,
                        source_anchor=source_anchor,
                    )
                    spans.append(token)
                    for tag_key in sorted(set(overlapping_tags)):
                        tags.append(
                            TagCandidate(
                                span_id=token.span_id,
                                tag_key=tag_key,
                                matched_text=token_text,
                                start_char=t_start,
                                end_char=t_end,
                            )
                        )

    unique_tags: dict[tuple[str, str, int, int], TagCandidate] = {}
    for candidate in tags:
        unique_tags[(candidate.span_id, candidate.tag_key, candidate.start_char, candidate.end_char)] = candidate

    return RefineryResult(
        journal_entry_id=journal_entry_id,
        source_sha256=sha256_text(text),
        spans=tuple(spans),
        tags=tuple(unique_tags.values()),
    )
