"""Tests for web search functionality."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from backend.search import search_web, format_search_results, SEARCH_TOOL
from backend.council import execute_tool
from backend.openrouter import query_model_with_tools


class TestSearchTool:
    """Tests for the SEARCH_TOOL definition."""

    def test_search_tool_structure(self):
        """SEARCH_TOOL has correct OpenAI function calling format."""
        assert SEARCH_TOOL["type"] == "function"
        assert SEARCH_TOOL["function"]["name"] == "search_web"
        assert "parameters" in SEARCH_TOOL["function"]
        assert "query" in SEARCH_TOOL["function"]["parameters"]["properties"]

    def test_search_tool_required_params(self):
        """SEARCH_TOOL requires the query parameter."""
        assert "query" in SEARCH_TOOL["function"]["parameters"]["required"]


class TestSearchWeb:
    """Tests for the search_web() function."""

    @pytest.mark.asyncio
    async def test_search_web_no_api_key(self):
        """Returns error when TAVILY_API_KEY is not set."""
        with patch("backend.search.TAVILY_API_KEY", None):
            result = await search_web("test query")
            assert "error" in result
            assert "TAVILY_API_KEY not configured" in result["error"]
            assert result["results"] == []

    @pytest.mark.asyncio
    async def test_search_web_success(self):
        """Returns formatted results on successful API call."""
        mock_response = {
            "answer": "Test answer",
            "results": [
                {"title": "Result 1", "url": "https://example.com/1", "content": "Content 1"},
                {"title": "Result 2", "url": "https://example.com/2", "content": "Content 2"},
            ]
        }

        with patch("backend.search.TAVILY_API_KEY", "test-key"):
            with patch("httpx.AsyncClient") as mock_client:
                mock_response_obj = MagicMock()
                mock_response_obj.json.return_value = mock_response
                mock_response_obj.raise_for_status = MagicMock()

                mock_client_instance = AsyncMock()
                mock_client_instance.post = AsyncMock(return_value=mock_response_obj)
                mock_client.return_value.__aenter__.return_value = mock_client_instance

                result = await search_web("test query")

                assert "error" not in result
                assert result["answer"] == "Test answer"
                assert len(result["results"]) == 2
                assert result["results"][0]["title"] == "Result 1"

    @pytest.mark.asyncio
    async def test_search_web_api_error(self):
        """Returns error on API failure."""
        with patch("backend.search.TAVILY_API_KEY", "test-key"):
            with patch("httpx.AsyncClient") as mock_client:
                mock_client_instance = AsyncMock()
                mock_client_instance.post = AsyncMock(side_effect=Exception("API Error"))
                mock_client.return_value.__aenter__.return_value = mock_client_instance

                result = await search_web("test query")

                assert "error" in result
                assert "API Error" in result["error"]
                assert result["results"] == []


class TestFormatSearchResults:
    """Tests for the format_search_results() function."""

    def test_format_with_answer_and_results(self):
        """Formats results with both answer and search results."""
        response = {
            "answer": "Quick answer here",
            "results": [
                {"title": "Title 1", "url": "https://example.com", "content": "Content here"}
            ]
        }
        formatted = format_search_results(response)

        assert "Quick Answer: Quick answer here" in formatted
        assert "Search Results:" in formatted
        assert "1. Title 1" in formatted
        assert "URL: https://example.com" in formatted
        assert "Content here" in formatted

    def test_format_with_error(self):
        """Formats error response correctly."""
        response = {"error": "Something went wrong", "results": []}
        formatted = format_search_results(response)

        assert "Search error: Something went wrong" in formatted

    def test_format_empty_results(self):
        """Handles empty results list."""
        response = {"results": []}
        formatted = format_search_results(response)

        assert "Search Results:" in formatted

    def test_format_multiple_results(self):
        """Formats multiple results with correct numbering."""
        response = {
            "results": [
                {"title": "First", "url": "https://1.com", "content": "Content 1"},
                {"title": "Second", "url": "https://2.com", "content": "Content 2"},
                {"title": "Third", "url": "https://3.com", "content": "Content 3"},
            ]
        }
        formatted = format_search_results(response)

        assert "1. First" in formatted
        assert "2. Second" in formatted
        assert "3. Third" in formatted


class TestExecuteTool:
    """Tests for the execute_tool() function in council.py."""

    @pytest.mark.asyncio
    async def test_execute_search_web_tool(self):
        """Executes search_web tool and returns formatted results."""
        mock_search_result = {
            "answer": "Test",
            "results": [{"title": "T", "url": "U", "content": "C"}]
        }

        with patch("backend.council.orchestrator.search_web", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = mock_search_result

            result = await execute_tool("search_web", {"query": "test"})

            mock_search.assert_called_once_with("test")
            assert "Search Results:" in result

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        """Returns error for unknown tool names."""
        result = await execute_tool("unknown_tool", {"arg": "value"})
        assert "Unknown tool" in result


class TestQueryModelWithTools:
    """Tests for the query_model_with_tools() function."""

    @pytest.mark.asyncio
    async def test_no_tool_calls(self):
        """Returns content directly when model doesn't request tools."""
        mock_api_response = {
            "choices": [{
                "message": {
                    "content": "Direct answer without tools"
                }
            }]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_api_response
            mock_response.raise_for_status = MagicMock()

            mock_client_instance = AsyncMock()
            mock_client_instance.post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            result = await query_model_with_tools(
                model="test/model",
                messages=[{"role": "user", "content": "question"}],
                tools=[SEARCH_TOOL],
                tool_executor=AsyncMock()
            )

            assert result["content"] == "Direct answer without tools"
            assert result["tool_calls_made"] == []

    @pytest.mark.asyncio
    async def test_with_tool_call(self):
        """Executes tool and returns final response."""
        # First response: model requests tool
        tool_call_response = {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "id": "call_123",
                        "function": {
                            "name": "search_web",
                            "arguments": '{"query": "current weather"}'
                        }
                    }]
                }
            }]
        }

        # Second response: model provides final answer
        final_response = {
            "choices": [{
                "message": {
                    "content": "Based on the search, the weather is sunny."
                }
            }]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_resp_1 = MagicMock()
            mock_resp_1.json.return_value = tool_call_response
            mock_resp_1.raise_for_status = MagicMock()

            mock_resp_2 = MagicMock()
            mock_resp_2.json.return_value = final_response
            mock_resp_2.raise_for_status = MagicMock()

            mock_client_instance = AsyncMock()
            mock_client_instance.post = AsyncMock(side_effect=[mock_resp_1, mock_resp_2])
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            mock_executor = AsyncMock(return_value="Search results here")

            result = await query_model_with_tools(
                model="test/model",
                messages=[{"role": "user", "content": "what's the weather?"}],
                tools=[SEARCH_TOOL],
                tool_executor=mock_executor
            )

            assert result["content"] == "Based on the search, the weather is sunny."
            assert len(result["tool_calls_made"]) == 1
            assert result["tool_calls_made"][0]["tool"] == "search_web"
            mock_executor.assert_called_once_with("search_web", {"query": "current weather"})

    @pytest.mark.asyncio
    async def test_max_tool_calls_reached(self):
        """Returns message when max tool calls is exceeded."""
        # Response that always requests another tool call
        tool_call_response = {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "id": "call_123",
                        "function": {
                            "name": "search_web",
                            "arguments": '{"query": "search"}'
                        }
                    }]
                }
            }]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = tool_call_response
            mock_response.raise_for_status = MagicMock()

            mock_client_instance = AsyncMock()
            mock_client_instance.post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            result = await query_model_with_tools(
                model="test/model",
                messages=[{"role": "user", "content": "question"}],
                tools=[SEARCH_TOOL],
                tool_executor=AsyncMock(return_value="result"),
                max_tool_calls=3
            )

            assert "Max tool calls reached" in result["content"]
            assert len(result["tool_calls_made"]) == 3

    @pytest.mark.asyncio
    async def test_tool_execution_error(self):
        """Handles tool execution errors gracefully."""
        tool_call_response = {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "id": "call_123",
                        "function": {
                            "name": "search_web",
                            "arguments": '{"query": "test"}'
                        }
                    }]
                }
            }]
        }

        final_response = {
            "choices": [{
                "message": {
                    "content": "I couldn't search but here's my answer."
                }
            }]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_resp_1 = MagicMock()
            mock_resp_1.json.return_value = tool_call_response
            mock_resp_1.raise_for_status = MagicMock()

            mock_resp_2 = MagicMock()
            mock_resp_2.json.return_value = final_response
            mock_resp_2.raise_for_status = MagicMock()

            mock_client_instance = AsyncMock()
            mock_client_instance.post = AsyncMock(side_effect=[mock_resp_1, mock_resp_2])
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            # Tool executor that raises an error
            mock_executor = AsyncMock(side_effect=Exception("Tool failed"))

            result = await query_model_with_tools(
                model="test/model",
                messages=[{"role": "user", "content": "question"}],
                tools=[SEARCH_TOOL],
                tool_executor=mock_executor
            )

            # Should still complete with the tool error captured
            assert result["content"] == "I couldn't search but here's my answer."
            assert "Error executing tool" in result["tool_calls_made"][0]["result_preview"]


class TestStage1ToolIntegration:
    """Tests for tool calling integration in Stage 1."""

    @pytest.mark.asyncio
    async def test_stage1_returns_tool_calls_made(self):
        """Stage 1 includes tool_calls_made in results when tools are used."""
        from backend.council import stage1_collect_responses

        mock_response = {
            "content": "Here's what I found after searching...",
            "tool_calls_made": [{"tool": "search_web", "args": {"query": "test"}, "result_preview": "..."}]
        }

        with patch("backend.council.orchestrator.query_model_with_tools", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = mock_response
            with patch("backend.council.orchestrator.COUNCIL_MODELS", ["test/model"]):
                results = await stage1_collect_responses("What is the current price of BTC?")

                assert len(results) == 1
                assert "tool_calls_made" in results[0]
                assert results[0]["tool_calls_made"][0]["tool"] == "search_web"

    @pytest.mark.asyncio
    async def test_stage1_no_tool_calls(self):
        """Stage 1 omits tool_calls_made when no tools are used."""
        from backend.council import stage1_collect_responses

        mock_response = {
            "content": "I know this without searching.",
            "tool_calls_made": []
        }

        with patch("backend.council.orchestrator.query_model_with_tools", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = mock_response
            with patch("backend.council.orchestrator.COUNCIL_MODELS", ["test/model"]):
                results = await stage1_collect_responses("What is 2+2?")

                assert len(results) == 1
                assert "tool_calls_made" not in results[0]
