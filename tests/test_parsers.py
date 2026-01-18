"""Tests for Dossier parsers."""

import pytest
from dossier.models import DocumentationLevel
from dossier.parsers import BaseParser, MarkdownParser, ParserRegistry
from pathlib import Path


class TestMarkdownParser:
    """Tests for MarkdownParser."""

    @pytest.fixture
    def parser(self) -> MarkdownParser:
        """Create a markdown parser."""
        return MarkdownParser()

    def test_supported_extensions(self, parser: MarkdownParser) -> None:
        """Test supported file extensions."""
        assert ".md" in parser.supported_extensions
        assert ".markdown" in parser.supported_extensions

    def test_can_parse_markdown(self, parser: MarkdownParser) -> None:
        """Test can_parse for markdown files."""
        assert parser.can_parse(Path("README.md"))
        assert parser.can_parse(Path("docs/guide.markdown"))
        assert not parser.can_parse(Path("script.py"))

    def test_parse_simple_markdown(self, parser: MarkdownParser) -> None:
        """Test parsing simple markdown content."""
        content = """# Title

This is the introduction.

## Getting Started

Setup instructions here.
"""
        sections = parser.parse(content, source_file="test.md", project_id=1)
        
        assert len(sections) == 2
        assert sections[0].title == "Title"
        assert sections[1].title == "Getting Started"

    def test_parse_infers_section_type(self, parser: MarkdownParser) -> None:
        """Test that parser infers section types from titles."""
        content = """# Project Name

## Installation

Install with pip.

## API Reference

API documentation.

## Configuration

Config options.
"""
        sections = parser.parse(content, project_id=1)
        
        section_types = {s.title: s.section_type for s in sections}
        assert section_types["Installation"] == "setup"
        assert section_types["API Reference"] == "api"
        assert section_types["Configuration"] == "configuration"

    def test_parse_empty_content(self, parser: MarkdownParser) -> None:
        """Test parsing content with no headers."""
        content = "Just some plain text without headers."
        sections = parser.parse(content, project_id=1)
        
        assert len(sections) == 1
        assert sections[0].title == "Content"

    def test_header_level_mapping(self, parser: MarkdownParser) -> None:
        """Test that header levels map to documentation levels."""
        content = """# H1 Summary

## H2 Overview

### H3 Detailed

#### H4 Also Detailed

##### H5 Technical
"""
        sections = parser.parse(content, project_id=1)
        
        assert sections[0].level == DocumentationLevel.SUMMARY
        assert sections[1].level == DocumentationLevel.OVERVIEW
        assert sections[2].level == DocumentationLevel.DETAILED
        assert sections[3].level == DocumentationLevel.DETAILED
        assert sections[4].level == DocumentationLevel.TECHNICAL


class TestParserRegistry:
    """Tests for ParserRegistry."""

    def test_default_registry(self) -> None:
        """Test default registry includes markdown parser."""
        registry = ParserRegistry.default()
        parser = registry.get_parser(Path("README.md"))
        assert parser is not None
        assert isinstance(parser, MarkdownParser)

    def test_register_parser(self) -> None:
        """Test registering a custom parser."""
        registry = ParserRegistry()
        parser = MarkdownParser()
        registry.register(parser)
        
        assert registry.get_parser(Path("test.md")) is not None

    def test_no_parser_for_unknown_extension(self) -> None:
        """Test returns None for unknown file types."""
        registry = ParserRegistry.default()
        assert registry.get_parser(Path("script.py")) is None
