import re
from pathlib import Path
from fpdf import FPDF

# Page geometry
LEFT = 10
RIGHT = 10
PAGE_W = 210
CONTENT_W = PAGE_W - LEFT - RIGHT  # 190


class ResumePDF(FPDF):
    """Single-page ATS-friendly resume PDF."""

    FONT = "Helvetica"  # Built-in, works everywhere (visually identical to Arial)

    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=False)

        # Try macOS Arial first (nicer), fall back to built-in Helvetica
        font_dir = "/System/Library/Fonts/Supplemental"
        try:
            self.add_font("Arial", "", f"{font_dir}/Arial.ttf", uni=True)
            self.add_font("Arial", "B", f"{font_dir}/Arial Bold.ttf", uni=True)
            self.add_font("Arial", "I", f"{font_dir}/Arial Italic.ttf", uni=True)
            ResumePDF.FONT = "Arial"
        except (FileNotFoundError, OSError):
            ResumePDF.FONT = "Helvetica"  # Built-in, no TTF needed


class PDFGenerator:
    """Convert plain-text resume to a single-page PDF."""

    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, resume_text: str, filename: str) -> str:
        """Generate a PDF and return the file path."""
        pdf = ResumePDF()
        pdf.add_page()
        pdf.set_margins(LEFT, 7, RIGHT)
        pdf.set_y(7)

        lines = resume_text.strip().split("\n")
        i = 0

        while i < len(lines):
            line = lines[i].rstrip()

            # Always reset X to left margin before rendering
            pdf.set_x(LEFT)

            # Name (first line)
            if i == 0:
                pdf.set_font(ResumePDF.FONT, "B", 12)
                pdf.cell(CONTENT_W, 4.5, line, ln=True, align="C")
                i += 1
                continue

            # Contact info line (contains | and email/@)
            if i <= 2 and "|" in line and ("@" in line or "+" in line):
                pdf.set_font(ResumePDF.FONT, "", 7)
                pdf.cell(CONTENT_W, 3, line, ln=True, align="C")
                i += 1
                continue

            # Links line (linkedin, github)
            if i <= 3 and ("linkedin" in line.lower() or "github" in line.lower()):
                pdf.set_font(ResumePDF.FONT, "", 7)
                pdf.cell(CONTENT_W, 3, line, ln=True, align="C")
                i += 1
                continue

            # Section header (line followed by ===== or ===== before text)
            if line.startswith("===="):
                i += 1
                continue

            if i + 1 < len(lines) and lines[i + 1].startswith("===="):
                pdf.ln(1.5)
                y = pdf.get_y()
                pdf.line(LEFT, y, PAGE_W - RIGHT, y)
                pdf.ln(0.5)
                pdf.set_font(ResumePDF.FONT, "B", 8.5)
                pdf.set_x(LEFT)
                pdf.cell(CONTENT_W, 3.5, line.upper(), ln=True)
                i += 1
                if i < len(lines) and lines[i].startswith("===="):
                    i += 1
                continue

            # Company header (mostly uppercase + contains — dash)
            if self._is_company_header(line):
                pdf.ln(1)
                pdf.set_font(ResumePDF.FONT, "B", 7.5)
                pdf.set_x(LEFT)
                pdf.multi_cell(CONTENT_W, 3, line)
                i += 1
                continue

            # Role/title line (italic — contains | for date/location, not a bullet)
            if "|" in line and not line.startswith("-") and not self._is_project_header(line):
                pdf.set_font(ResumePDF.FONT, "I", 7)
                pdf.set_x(LEFT)
                pdf.multi_cell(CONTENT_W, 3, line)
                i += 1
                continue

            # Bullet points
            if line.startswith("- "):
                pdf.set_font(ResumePDF.FONT, "", 7)
                bullet_text = line[2:]
                pdf.set_x(LEFT)
                pdf.cell(3, 3, "•")
                pdf.multi_cell(CONTENT_W - 3, 3, bullet_text)
                i += 1
                continue

            # Skills line (bold label: value)
            if ":" in line and not line.startswith("-") and len(line) > 20:
                parts = line.split(":", 1)
                if len(parts) == 2 and len(parts[0]) < 45:
                    pdf.set_font(ResumePDF.FONT, "B", 7)
                    label = parts[0] + ":"
                    label_w = pdf.get_string_width(label) + 1
                    pdf.set_x(LEFT)
                    pdf.cell(label_w, 3, label)
                    pdf.set_font(ResumePDF.FONT, "", 7)
                    pdf.multi_cell(CONTENT_W - label_w, 3, parts[1].strip())
                    i += 1
                    continue

            # Project header (bold, contains | with tech stack)
            if self._is_project_header(line):
                pdf.set_font(ResumePDF.FONT, "B", 7)
                pdf.set_x(LEFT)
                pdf.multi_cell(CONTENT_W, 3, line)
                i += 1
                continue

            # Empty line → small gap
            if not line.strip():
                i += 1
                continue

            # Default
            pdf.set_font(ResumePDF.FONT, "", 7)
            pdf.set_x(LEFT)
            pdf.multi_cell(CONTENT_W, 3, line)
            i += 1

            # Safety — don't overflow
            if pdf.get_y() > 282:
                break

        # Save
        safe_name = re.sub(r"[^\w\-]", "_", filename)
        filepath = self.output_dir / f"Shrinija_Kummari_{safe_name}.pdf"
        pdf.output(str(filepath))
        return str(filepath)

    def _is_company_header(self, line: str) -> bool:
        """Company lines are mostly uppercase and contain — or –."""
        if "—" not in line and "–" not in line:
            # Also match ALL CAPS lines without dashes (e.g., "ELECTRONIC ARTS (EA GAMES)")
            alpha = [c for c in line if c.isalpha()]
            if alpha and sum(1 for c in alpha if c.isupper()) / len(alpha) > 0.6:
                return True
            return False
        name_part = line.split("—")[0].split("–")[0].strip()
        alpha = [c for c in name_part if c.isalpha()]
        return bool(alpha) and sum(1 for c in alpha if c.isupper()) / len(alpha) > 0.5

    def _is_project_header(self, line: str) -> bool:
        """Project headers contain | with tech stack keywords."""
        if "|" not in line:
            return False
        lower = line.lower()
        tech_words = ["python", "sql", "bigquery", "streamlit", "langchain", "cloud run",
                      "plotly", "chromadb", "claude", "llama", "docker", "nlp", "react"]
        return any(t in lower for t in tech_words)
