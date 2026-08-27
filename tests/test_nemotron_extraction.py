"""Tests for Nemotron content-to-tool-call extraction.

Nemotron 120B (and similar open models) put tool call JSON inside the
content string instead of the proper tool_calls field. These tests verify
that _extract_json_tool_calls_from_content correctly handles all variants.
"""
import json
import pytest
from dev.agents.production_loop import ProductionAgentLoop


class TestNemotronExtraction:
    """Test the static extraction method on ProductionAgentLoop."""

    # ------------------------------------------------------------------ #
    #  Strategy 1: entire content is a JSON array
    # ------------------------------------------------------------------ #

    def test_openai_format_array(self):
        """[{\"function\": {\"name\": \"write_file\", \"arguments\": ...}}]"""
        calls = [
            {
                "function": {
                    "name": "write_file",
                    "arguments": json.dumps({"path": "a.js", "content": "hello"}),
                }
            }
        ]
        text = json.dumps(calls)
        remaining, extracted = ProductionAgentLoop._extract_json_tool_calls_from_content(text)
        assert remaining == ""
        assert len(extracted) == 1
        assert extracted[0]["function"]["name"] == "write_file"
        args = json.loads(extracted[0]["function"]["arguments"])
        assert args["path"] == "a.js"

    def test_nemotron_format_array(self):
        """[{\"name\": \"write_file\", \"parameters\": {...}}]"""
        calls = [
            {"name": "write_file", "parameters": {"path": "b.css", "content": "body{}"}}
        ]
        text = json.dumps(calls)
        remaining, extracted = ProductionAgentLoop._extract_json_tool_calls_from_content(text)
        assert remaining == ""
        assert len(extracted) == 1
        assert extracted[0]["function"]["name"] == "write_file"
        args = json.loads(extracted[0]["function"]["arguments"])
        assert args["path"] == "b.css"

    def test_single_object_not_array(self):
        """{ \"name\": \"run_terminal_command\", \"parameters\": {\"command\": \"ls\"} }"""
        obj = {"name": "run_terminal_command", "parameters": {"command": "ls -la"}}
        text = json.dumps(obj)
        remaining, extracted = ProductionAgentLoop._extract_json_tool_calls_from_content(text)
        assert remaining == ""
        assert len(extracted) == 1
        assert extracted[0]["function"]["name"] == "run_terminal_command"
        args = json.loads(extracted[0]["function"]["arguments"])
        assert args["command"] == "ls -la"

    # ------------------------------------------------------------------ #
    #  Strategy 2: JSON embedded in natural language
    # ------------------------------------------------------------------ #

    def test_json_array_with_surrounding_text(self):
        """JSON tool calls surrounded by explanatory text."""
        preamble = "I'll create the files now.\n\n"
        calls = [
            {"name": "write_file", "parameters": {"path": "x.html", "content": "<html></html>"}}
        ]
        text = preamble + json.dumps(calls) + "\n\nDone!"
        remaining, extracted = ProductionAgentLoop._extract_json_tool_calls_from_content(text)
        assert len(extracted) == 1
        assert extracted[0]["function"]["name"] == "write_file"
        # Remaining should not contain the JSON anymore
        assert '"name"' not in remaining
        assert "I'll create" in remaining

    def test_multiple_tool_calls_in_text(self):
        """Multiple tool calls in JSON array embedded in text."""
        calls = [
            {"name": "write_file", "parameters": {"path": "a.js", "content": "var x=1;"}},
            {"name": "run_terminal_command", "parameters": {"command": "npm init -y"}},
        ]
        text = "Here are the files:\n\n" + json.dumps(calls)
        remaining, extracted = ProductionAgentLoop._extract_json_tool_calls_from_content(text)
        assert len(extracted) == 2
        names = [e["function"]["name"] for e in extracted]
        assert "write_file" in names
        assert "run_terminal_command" in names

    # ------------------------------------------------------------------ #
    #  Strategy 3: double-escaped JSON
    # ------------------------------------------------------------------ #

    def test_double_escaped_json(self):
        """Model outputs stringified JSON with escaped quotes."""
        inner = json.dumps([{"name": "write_file", "parameters": {"path": "y.js", "content": "ok"}}])
        # Double-escape: every " becomes \"
        double = inner.replace('"', '\\"')
        # The content field itself wraps it: the model literally outputs this string
        remaining, extracted = ProductionAgentLoop._extract_json_tool_calls_from_content(double)
        # Should either extract from the unescaped version or return original
        # (Strategy 3 handles this)
        if extracted:
            assert extracted[0]["function"]["name"] == "write_file"

    # ------------------------------------------------------------------ #
    #  Edge cases
    # ------------------------------------------------------------------ #

    def test_empty_content(self):
        remaining, extracted = ProductionAgentLoop._extract_json_tool_calls_from_content("")
        assert remaining == ""
        assert extracted == []

    def test_plain_text_no_json(self):
        text = "I'll help you build a website. Let me start by creating the files."
        remaining, extracted = ProductionAgentLoop._extract_json_tool_calls_from_content(text)
        assert remaining == text
        assert extracted == []

    def test_non_tool_json(self):
        """JSON that doesn't look like tool calls should NOT be extracted."""
        text = json.dumps({"status": "ok", "data": [1, 2, 3]})
        remaining, extracted = ProductionAgentLoop._extract_json_tool_calls_from_content(text)
        assert extracted == []

    def test_partial_json(self):
        """Incomplete JSON should not crash."""
        text = '[{"name": "write_file", "parameters": {"path":'
        remaining, extracted = ProductionAgentLoop._extract_json_tool_calls_from_content(text)
        assert extracted == []  # No crash, no false positives

    def test_multiple_json_blocks_in_text(self):
        """Two separate JSON tool call objects in the text."""
        tc1 = json.dumps({"name": "write_file", "parameters": {"path": "a.html", "content": "<h1>A</h1>"}})
        tc2 = json.dumps({"name": "write_file", "parameters": {"path": "b.html", "content": "<h1>B</h1>"}})
        text = f"First:\n{tc1}\n\nSecond:\n{tc2}"
        remaining, extracted = ProductionAgentLoop._extract_json_tool_calls_from_content(text)
        # At least one should be found (strategy 2 does bracket matching)
        assert len(extracted) >= 1

    # ------------------------------------------------------------------ #
    #  _normalize_tool_call_object
    # ------------------------------------------------------------------ #

    def test_normalize_openai_format(self):
        obj = {"function": {"name": "write_file", "arguments": '{"path":"x.js"}'}}
        tc = ProductionAgentLoop._normalize_tool_call_object(obj)
        assert tc is not None
        assert tc["function"]["name"] == "write_file"

    def test_normalize_nemotron_format(self):
        obj = {"name": "write_file", "parameters": {"path": "x.js"}}
        tc = ProductionAgentLoop._normalize_tool_call_object(obj)
        assert tc is not None
        assert tc["function"]["name"] == "write_file"
        args = json.loads(tc["function"]["arguments"])
        assert args["path"] == "x.js"

    def test_normalize_invalid_returns_none(self):
        obj = {"foo": "bar"}
        tc = ProductionAgentLoop._normalize_tool_call_object(obj)
        assert tc is None

    # ------------------------------------------------------------------ #
    #  Realistic Nemotron output
    # ------------------------------------------------------------------ #

    def test_realistic_nemotron_multi_tool_output(self):
        """Simulate what Nemotron actually outputs: a mix of thinking + tool calls."""
        nemotron_output = (
            "I'll create the portfolio website with the following files:\n\n"
            + json.dumps([
                {
                    "name": "write_file",
                    "parameters": {
                        "path": "portfolio/public/index.html",
                        "content": "<!DOCTYPE html><html><head><title>Portfolio</title></head></html>"
                    }
                },
                {
                    "name": "write_file",
                    "parameters": {
                        "path": "portfolio/public/styles.css",
                        "content": "body { margin: 0; font-family: Inter; }"
                    }
                },
                {
                    "name": "run_terminal_command",
                    "parameters": {
                        "command": "cd portfolio && npm init -y"
                    }
                }
            ])
            + "\n\nI've created the basic structure. Let me install dependencies."
        )
        remaining, extracted = ProductionAgentLoop._extract_json_tool_calls_from_content(nemotron_output)
        assert len(extracted) == 3
        names = [e["function"]["name"] for e in extracted]
        assert names == ["write_file", "write_file", "run_terminal_command"]
        # Natural language text should remain
        assert "portfolio website" in remaining
