from corpus_refinery import RefineryPolicy, refine_entry, sha256_text


def test_refinery_preserves_exact_source_offsets():
    source = (
        "Micky Yamatani appeared in the docket on August 3, 2026. "
        "I first connected that event to the Rule 60 argument.\n\n"
        "Unrelated housekeeping text."
    )
    result = refine_entry(
        "entry-1",
        source,
        tag_rules={
            "entity:yamatani": ["Micky Yamatani", "Yamatani"],
            "concept:rule-60": ["Rule 60"],
        },
    )

    assert result.source_sha256 == sha256_text(source)
    for span in result.spans:
        assert source[span.start_char:span.end_char] == span.text


def test_refinery_is_progressive_not_every_word_tag_spam():
    source = (
        "Routine note about groceries.\n\n"
        "Micky Yamatani was discussed on August 3, 2026 in connection with Rule 60."
    )
    result = refine_entry(
        "entry-2",
        source,
        tag_rules={
            "entity:yamatani": ["Micky Yamatani"],
            "concept:rule-60": ["Rule 60"],
        },
    )

    levels = [span.level for span in result.spans]
    assert levels.count("message") == 1
    assert levels.count("paragraph") == 2
    assert "sentence" in levels
    assert len([tag for tag in result.tags if tag.tag_key == "entity:yamatani"]) >= 1
    assert not any(span.level == "token" and span.text.lower() == "groceries" for span in result.spans)


def test_high_interest_tagged_phrase_can_reach_token_level():
    source = (
        'On August 3, 2026 at 10:13 PM, Micky Yamatani appeared in Dkt. 193; '
        '"Rule 60 corruption issue" was the phrase I recorded.'
    )
    policy = RefineryPolicy(
        sentence_interest_threshold=0.20,
        phrase_interest_threshold=0.40,
        token_interest_threshold=0.65,
        vector_interest_threshold=0.30,
    )
    result = refine_entry(
        "entry-3",
        source,
        policy=policy,
        tag_rules={
            "entity:yamatani": ["Micky Yamatani"],
            "concept:corruption": ["corruption"],
            "concept:rule-60": ["Rule 60"],
        },
    )

    token_texts = {span.text.lower() for span in result.spans if span.level == "token"}
    assert "corruption" in token_texts
    assert any(tag.tag_key == "concept:corruption" for tag in result.tags)
    assert result.vector_candidates


def test_stable_span_ids_are_repeatable():
    source = "Micky Yamatani was mentioned on August 3, 2026."
    rules = {"entity:yamatani": ["Micky Yamatani"]}
    first = refine_entry("entry-4", source, tag_rules=rules)
    second = refine_entry("entry-4", source, tag_rules=rules)

    assert [span.span_id for span in first.spans] == [span.span_id for span in second.spans]
    assert first.tags == second.tags
