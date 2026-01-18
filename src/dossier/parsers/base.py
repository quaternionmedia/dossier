"""Base parser classes for documentation parsing."""

import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from dossier.models import DocumentationLevel, DocumentSection


class BaseParser(ABC):
    """Abstract base class for documentation parsers."""
    
    @property
    @abstractmethod
    def supported_extensions(self) -> list[str]:
        """Return list of supported file extensions."""
        pass
    
    @abstractmethod
    def parse(self, content: str, source_file: Optional[str] = None) -> list[DocumentSection]:
        """Parse content and return document sections."""
        pass
    
    def can_parse(self, file_path: Path) -> bool:
        """Check if this parser can handle the given file."""
        return file_path.suffix.lower() in self.supported_extensions


class MarkdownParser(BaseParser):
    """Parser for Markdown documentation files."""
    
    @property
    def supported_extensions(self) -> list[str]:
        return [".md", ".markdown"]
    
    def parse(
        self,
        content: str,
        source_file: Optional[str] = None,
        project_id: int = 0,
    ) -> list[DocumentSection]:
        """Parse markdown content into document sections."""
        sections: list[DocumentSection] = []
        
        # Split by headers (# or ##)
        header_pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
        
        matches = list(header_pattern.finditer(content))
        
        if not matches:
            # No headers, treat entire content as one section
            sections.append(
                DocumentSection(
                    project_id=project_id,
                    title="Content",
                    content=content.strip(),
                    level=DocumentationLevel.DETAILED,
                    source_file=source_file,
                    order=0,
                )
            )
            return sections
        
        for i, match in enumerate(matches):
            header_level = len(match.group(1))
            title = match.group(2).strip()
            
            # Get content between this header and the next
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            section_content = content[start:end].strip()
            
            # Determine documentation level based on header depth
            doc_level = self._header_to_doc_level(header_level)
            
            # Determine section type from title
            section_type = self._infer_section_type(title)
            
            sections.append(
                DocumentSection(
                    project_id=project_id,
                    title=title,
                    content=section_content,
                    level=doc_level,
                    section_type=section_type,
                    source_file=source_file,
                    order=i,
                )
            )
        
        return sections
    
    def _header_to_doc_level(self, header_level: int) -> DocumentationLevel:
        """Map markdown header level to documentation level."""
        if header_level == 1:
            return DocumentationLevel.SUMMARY
        elif header_level == 2:
            return DocumentationLevel.OVERVIEW
        elif header_level <= 4:
            return DocumentationLevel.DETAILED
        else:
            return DocumentationLevel.TECHNICAL
    
    def _infer_section_type(self, title: str) -> str:
        """Infer section type from title."""
        title_lower = title.lower()
        
        type_keywords = {
            "setup": ["setup", "installation", "install", "getting started"],
            "api": ["api", "endpoint", "route"],
            "usage": ["usage", "how to", "example", "tutorial"],
            "configuration": ["config", "configuration", "settings"],
            "development": ["development", "contributing", "developer"],
            "readme": ["readme", "about", "overview", "introduction"],
        }
        
        for section_type, keywords in type_keywords.items():
            if any(kw in title_lower for kw in keywords):
                return section_type
        
        return "general"


class ParserRegistry:
    """Registry for documentation parsers."""
    
    def __init__(self) -> None:
        self._parsers: list[BaseParser] = []
    
    def register(self, parser: BaseParser) -> None:
        """Register a parser."""
        self._parsers.append(parser)
    
    def get_parser(self, file_path: Path) -> Optional[BaseParser]:
        """Get appropriate parser for a file."""
        for parser in self._parsers:
            if parser.can_parse(file_path):
                return parser
        return None
    
    @classmethod
    def default(cls) -> "ParserRegistry":
        """Create registry with default parsers."""
        registry = cls()
        registry.register(MarkdownParser())
        return registry
