import os
import logging

log = logging.getLogger("amethyst.docreader")

class DocumentReader:
    """Handles extracting text from various file formats for RAG injection."""
    
    @staticmethod
    def read_file(filepath: str, max_chars: int = 15000) -> str:
        """
        Reads a file and returns its text content. 
        Limits length to max_chars to prevent overflowing the context window.
        """
        if not os.path.exists(filepath):
            return ""
            
        ext = os.path.splitext(filepath)[1].lower()
        
        try:
            if ext == ".pdf":
                return DocumentReader._read_pdf(filepath, max_chars)
            elif ext in [".txt", ".md", ".py", ".json", ".js", ".html", ".css", ".csv", ".log", ".ini"]:
                return DocumentReader._read_text(filepath, max_chars)
            else:
                log.warning(f"Unsupported file type: {ext}")
                return f"[Unsupported file type: {ext}]"
        except Exception as e:
            log.error(f"Error reading document {filepath}: {e}")
            return f"[Error reading file: {e}]"

    @staticmethod
    def _read_pdf(filepath: str, max_chars: int) -> str:
        try:
            import fitz  # PyMuPDF
            text = ""
            with fitz.open(filepath) as doc:
                for page in doc:
                    text += page.get_text()
                    if len(text) > max_chars:
                        break
            
            if len(text) > max_chars:
                text = text[:max_chars] + "...[Document Truncated]"
            return text.strip()
        except ImportError:
            log.error("PyMuPDF (fitz) is not installed. Cannot read PDF.")
            return "[Error: PyMuPDF not installed. Run: pip install pymupdf]"

    @staticmethod
    def _read_text(filepath: str, max_chars: int) -> str:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read(max_chars + 100)
            if len(content) > max_chars:
                return content[:max_chars] + "...[Document Truncated]"
            return content.strip()
