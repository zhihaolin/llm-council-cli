"""
Tests for the ranking parser in council.py.

The ranking parser extracts structured rankings from model evaluation text.
These tests cover various edge cases and formats that models might produce.
"""

from llm_council.council import parse_ranking_from_text


class TestParseRankingFromText:
    """Tests for parse_ranking_from_text function."""

    def test_standard_format(self):
        """Test parsing standard FINAL RANKING format."""
        text = """
Response A is thorough and well-reasoned.
Response B lacks detail.
Response C is concise but accurate.

FINAL RANKING:
1. Response A
2. Response C
3. Response B
"""
        result = parse_ranking_from_text(text)
        assert result == ["Response A", "Response C", "Response B"]

    def test_no_spaces_after_number(self):
        """Test parsing when there's no space after the period."""
        text = """
FINAL RANKING:
1.Response A
2.Response B
3.Response C
"""
        result = parse_ranking_from_text(text)
        assert result == ["Response A", "Response B", "Response C"]

    def test_extra_whitespace(self):
        """Test parsing with extra whitespace."""
        text = """
FINAL RANKING:
1.   Response A
2.    Response B
3.  Response C
"""
        result = parse_ranking_from_text(text)
        assert result == ["Response A", "Response B", "Response C"]

    def test_five_responses(self):
        """Test parsing with 5 responses (typical council size)."""
        text = """
FINAL RANKING:
1. Response A
2. Response D
3. Response B
4. Response E
5. Response C
"""
        result = parse_ranking_from_text(text)
        assert result == ["Response A", "Response D", "Response B", "Response E", "Response C"]

    def test_lowercase_header(self):
        """Test that lowercase 'final ranking' is NOT matched (requires exact format)."""
        text = """
final ranking:
1. Response A
2. Response B
"""
        # Should fall back to finding Response patterns anywhere
        result = parse_ranking_from_text(text)
        # Fallback finds all Response X patterns
        assert "Response A" in result
        assert "Response B" in result

    def test_no_header_fallback(self):
        """Test fallback when FINAL RANKING header is missing."""
        text = """
My ranking is:
Response C is best
Response A is second
Response B is third
"""
        result = parse_ranking_from_text(text)
        # Fallback extracts Response X patterns in order of appearance
        assert result == ["Response C", "Response A", "Response B"]

    def test_text_after_ranking(self):
        """Test that text after ranking section doesn't interfere."""
        text = """
FINAL RANKING:
1. Response B
2. Response A
3. Response C

Note: This was a difficult decision.
"""
        result = parse_ranking_from_text(text)
        assert result == ["Response B", "Response A", "Response C"]

    def test_response_mentioned_in_evaluation(self):
        """Test that Response mentions in evaluation text don't pollute ranking."""
        text = """
Response A provides excellent detail on the topic.
Response B is lacking in depth but is accurate.
Response C offers a balanced view.

FINAL RANKING:
1. Response C
2. Response A
3. Response B
"""
        result = parse_ranking_from_text(text)
        # Should only get the ones from FINAL RANKING section
        assert result == ["Response C", "Response A", "Response B"]

    def test_empty_text(self):
        """Test handling of empty text."""
        result = parse_ranking_from_text("")
        assert result == []

    def test_no_responses_mentioned(self):
        """Test handling of text with no Response patterns."""
        text = "This is just some random text without any rankings."
        result = parse_ranking_from_text(text)
        assert result == []

    def test_bullet_format_fallback(self):
        """Test parsing bullet format (non-numbered)."""
        text = """
FINAL RANKING:
- Response B
- Response A
- Response C
"""
        # The numbered pattern won't match, but fallback will find them
        result = parse_ranking_from_text(text)
        assert "Response B" in result
        assert "Response A" in result
        assert "Response C" in result

    def test_mixed_case_response(self):
        """Test that Response must have capital R."""
        text = """
FINAL RANKING:
1. response A
2. Response B
3. RESPONSE C
"""
        result = parse_ranking_from_text(text)
        # Only "Response B" matches the pattern
        assert "Response B" in result


class TestCalculateAggregateRankings:
    """Tests for calculate_aggregate_rankings function."""

    def test_basic_aggregation(self):
        """Test basic ranking aggregation."""
        from llm_council.council import calculate_aggregate_rankings

        stage2_results = [
            {"model": "model1", "ranking": "FINAL RANKING:\n1. Response A\n2. Response B"},
            {"model": "model2", "ranking": "FINAL RANKING:\n1. Response B\n2. Response A"},
        ]
        label_to_model = {
            "Response A": "openai/gpt-5.2",
            "Response B": "google/gemini-3-pro-preview",
        }

        result = calculate_aggregate_rankings(stage2_results, label_to_model)

        # Both should have average rank of 1.5 (one 1st, one 2nd)
        assert len(result) == 2
        for entry in result:
            assert entry["average_rank"] == 1.5
            assert entry["rankings_count"] == 2

    def test_clear_winner(self):
        """Test when one model clearly wins."""
        from llm_council.council import calculate_aggregate_rankings

        stage2_results = [
            {"model": "m1", "ranking": "FINAL RANKING:\n1. Response A\n2. Response B\n3. Response C"},
            {"model": "m2", "ranking": "FINAL RANKING:\n1. Response A\n2. Response C\n3. Response B"},
            {"model": "m3", "ranking": "FINAL RANKING:\n1. Response A\n2. Response B\n3. Response C"},
        ]
        label_to_model = {
            "Response A": "winner",
            "Response B": "second",
            "Response C": "third",
        }

        result = calculate_aggregate_rankings(stage2_results, label_to_model)

        # Result is sorted by average rank
        assert result[0]["model"] == "winner"
        assert result[0]["average_rank"] == 1.0  # Always first
