"""Tests for spectrik.resolve — variable interpolation on parsed dicts."""

import pytest

from spectrik.resolve import Resolver


class TestResolveRef:
    """Test _resolve_ref: dotted reference resolution against context."""

    def test_bare_reference(self):
        r = Resolver({"name": "myapp"})
        assert r._resolve_ref("name") == "myapp"

    def test_dotted_reference_dict(self):
        r = Resolver({"env": {"HOME": "/home/user"}})
        assert r._resolve_ref("env.HOME") == "/home/user"

    def test_dotted_reference_getattr(self):
        class Config:
            region = "us-east-1"

        r = Resolver({"config": Config()})
        assert r._resolve_ref("config.region") == "us-east-1"

    def test_deeply_nested(self):
        r = Resolver({"a": {"b": {"c": "deep"}}})
        assert r._resolve_ref("a.b.c") == "deep"

    def test_undefined_raises(self):
        r = Resolver({"name": "myapp"})
        with pytest.raises(ValueError, match="missing"):
            r._resolve_ref("missing")

    def test_undefined_nested_raises(self):
        r = Resolver({"env": {"HOME": "/home"}})
        with pytest.raises(ValueError, match="MISSING"):
            r._resolve_ref("env.MISSING")

    def test_callable_value(self):
        r = Resolver({"cwd": lambda: "/tmp/work"})
        assert r._resolve_ref("cwd") == "/tmp/work"

    def test_callable_not_invoked_on_intermediate(self):
        """Callables at intermediate positions are not invoked during traversal."""
        r = Resolver({"get_value": lambda: "result"})
        with pytest.raises(ValueError, match="get_value.attr"):
            r._resolve_ref("get_value.attr")


class TestResolveValue:
    """Test _resolve_value: interpolation within string values."""

    def test_no_interpolation(self):
        r = Resolver({"name": "app"})
        assert r._resolve_value("plain string") == "plain string"

    def test_single_full_interpolation_preserves_type_int(self):
        r = Resolver({"count": 42})
        assert r._resolve_value("${count}") == 42

    def test_single_full_interpolation_preserves_type_bool(self):
        r = Resolver({"flag": True})
        assert r._resolve_value("${flag}") is True

    def test_single_full_interpolation_preserves_type_list(self):
        r = Resolver({"items": [1, 2, 3]})
        assert r._resolve_value("${items}") == [1, 2, 3]

    def test_embedded_interpolation_stringifies(self):
        r = Resolver({"name": "app"})
        assert r._resolve_value("hello-${name}") == "hello-app"

    def test_multiple_interpolations(self):
        r = Resolver({"host": "localhost", "port": 8080})
        assert r._resolve_value("${host}:${port}") == "localhost:8080"

    def test_dotted_in_string(self):
        r = Resolver({"env": {"HOME": "/home/user"}})
        assert r._resolve_value("${env.HOME}/.config") == "/home/user/.config"

    def test_undefined_raises(self):
        r = Resolver({})
        with pytest.raises(ValueError, match="missing"):
            r._resolve_value("${missing}")

    def test_callable_in_string(self):
        r = Resolver({"cwd": lambda: "/tmp"})
        assert r._resolve_value("${cwd}/data") == "/tmp/data"

    def test_escaped_dollar_not_interpolated(self):
        """$${...} should produce literal ${...}."""
        r = Resolver({"name": "app"})
        assert r._resolve_value("$${name}") == "${name}"

    def test_double_brace_passthrough(self):
        """${{ ... }} (e.g., GitHub Actions) is not ${...} syntax — left alone."""
        r = Resolver({"github": {"token": "secret"}})
        assert r._resolve_value("${{ github.token }}") == "${{ github.token }}"

    def test_mixed_interpolation_and_double_brace(self):
        """Real-world: spectrik vars alongside GitHub Actions expressions."""
        r = Resolver({"name": "myapp"})
        result = r._resolve_value("${name} uses ${{ github.token }}")
        assert result == "myapp uses ${{ github.token }}"

    def test_escaped_double_brace_produces_github_actions_syntax(self):
        """$${{ }} from HCL parsing produces ${{ }} after resolver (GitHub Actions)."""
        r = Resolver({"github": {"repository": "HACKED"}})
        # python-hcl2 parses $${{ expr }} as the literal string "$${{ expr }}"
        result = r._resolve_value("$${{ github.repository }}")
        assert result == "${{ github.repository }}"

    def test_hostile_context_cannot_inject_via_double_brace(self):
        """Even with matching context keys, ${{ }} patterns are never resolved."""
        r = Resolver(
            {
                "github": {"repository": "HACKED"},
                "secrets": {"TOKEN": "HACKED"},
            }
        )
        data = {
            "token": "${{ secrets.TOKEN }}",
            "repo": "$${{ github.repository }}",
            "name": "${github.repository}",
        }
        result = r.resolve(data)
        assert result["token"] == "${{ secrets.TOKEN }}"
        assert result["repo"] == "${{ github.repository }}"
        assert result["name"] == "HACKED"


class TestResolve:
    """Test resolve: recursive dict/list walking."""

    def test_simple_dict(self):
        r = Resolver({"name": "app"})
        data = {"title": "${name}"}
        assert r.resolve(data) == {"title": "app"}

    def test_nested_dict(self):
        r = Resolver({"host": "localhost"})
        data = {"server": {"address": "${host}"}}
        assert r.resolve(data) == {"server": {"address": "localhost"}}

    def test_list_values(self):
        r = Resolver({"x": "a", "y": "b"})
        data = {"items": ["${x}", "${y}"]}
        assert r.resolve(data) == {"items": ["a", "b"]}

    def test_list_of_dicts(self):
        r = Resolver({"name": "app"})
        data = {"entries": [{"label": "${name}"}]}
        assert r.resolve(data) == {"entries": [{"label": "app"}]}

    def test_non_string_values_untouched(self):
        r = Resolver({"name": "app"})
        data = {"count": 5, "flag": True, "ratio": 3.14, "empty": None}
        assert r.resolve(data) == {"count": 5, "flag": True, "ratio": 3.14, "empty": None}

    def test_original_dict_not_mutated(self):
        r = Resolver({"name": "app"})
        data = {"title": "${name}"}
        r.resolve(data)
        assert data == {"title": "${name}"}

    def test_empty_dict(self):
        r = Resolver({"name": "app"})
        assert r.resolve({}) == {}

    def test_empty_context(self):
        r = Resolver()
        data = {"title": "no interpolation"}
        assert r.resolve(data) == {"title": "no interpolation"}
