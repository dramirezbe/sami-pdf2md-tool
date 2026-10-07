#!/usr/bin/env python3
"""Generate a 5-page test PDF with text, formulas, tables and images per page."""
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage,
)
from reportlab.lib.styles import getSampleStyleSheet
from PIL import Image as PILImage, ImageDraw, ImageFont
import math
import os
import io

OUT = os.path.join(os.path.dirname(__file__), "test_document.pdf")
IMG_DIR = os.path.join(os.path.dirname(__file__), ".gen_images")
os.makedirs(IMG_DIR, exist_ok=True)

styles = getSampleStyleSheet()

PAGES = [
    {
        "title": "Chapter 1: Kinematics",
        "text": (
            "In classical mechanics, the position of a particle is described as a "
            "function of time. The displacement, velocity, and acceleration form the "
            "foundation of kinematics. Consider a projectile launched at angle theta."
        ),
        "formula": "v(t) = v₀ + at,   x(t) = x₀ + v₀t + ½at²",
        "table_header": ["Variable", "Symbol", "Unit", "Value"],
        "table_rows": [
            ["Initial velocity", "v₀", "m/s", "25.0"],
            ["Acceleration", "a", "m/s²", "−9.81"],
            ["Time", "t", "s", "3.0"],
            ["Displacement", "x", "m", "45.9"],
        ],
        "img_label": "Projectile trajectory",
        "img_color": (70, 130, 180),
    },
    {
        "title": "Chapter 2: Thermodynamics",
        "text": (
            "The laws of thermodynamics govern the transfer of energy in physical "
            "systems. Entropy is a measure of disorder, and the second law states "
            "that the total entropy of an isolated system never decreases."
        ),
        "formula": "ΔS = Q/T,   PV = nRT,   dU = δQ − δW",
        "table_header": ["Property", "Symbol", "Unit", "Example"],
        "table_rows": [
            ["Temperature", "T", "K", "300"],
            ["Pressure", "P", "Pa", "101325"],
            ["Volume", "V", "m³", "0.0224"],
            ["Entropy", "S", "J/K", "154.8"],
        ],
        "img_label": "PV diagram",
        "img_color": (220, 80, 60),
    },
    {
        "title": "Chapter 3: Electromagnetism",
        "text": (
            "Maxwell's equations unify electricity and magnetism into a single "
            "framework. The curl of the electric field relates to the time derivative "
            "of the magnetic field, producing electromagnetic waves."
        ),
        "formula": "∇×E = −∂B/∂t,   ∇·B = 0,   F = qE + qv×B",
        "table_header": ["Quantity", "Symbol", "SI Unit", "Typical Value"],
        "table_rows": [
            ["Electric field", "E", "V/m", "3.0 × 10⁶"],
            ["Magnetic field", "B", "T", "1.5"],
            ["Charge", "q", "C", "1.6 × 10⁻¹⁹"],
            ["Permittivity", "ε₀", "F/m", "8.85 × 10⁻¹²"],
        ],
        "img_label": "EM wave",
        "img_color": (60, 180, 75),
    },
    {
        "title": "Chapter 4: Quantum Mechanics",
        "text": (
            "At the atomic scale, particles exhibit wave-particle duality. The "
            "Schrödinger equation describes how the quantum state of a system "
            "evolves in time. Measurement collapses the wave function."
        ),
        "formula": "iℏ ∂ψ/∂t = Ĥψ,   ΔxΔp ≥ ℏ/2,   E = ℏω",
        "table_header": ["Constant", "Symbol", "Value", "Unit"],
        "table_rows": [
            ["Planck's constant", "ℏ", "1.055 × 10⁻³⁴", "J·s"],
            ["Electron mass", "mₑ", "9.109 × 10⁻³¹", "kg"],
            ["Bohr radius", "a₀", "5.292 × 10⁻¹¹", "m"],
            ["Fine structure", "α", "1/137.036", "—"],
        ],
        "img_label": "Wave function",
        "img_color": (148, 103, 189),
    },
    {
        "title": "Chapter 5: Statistical Mechanics",
        "text": (
            "Statistical mechanics bridges microscopic particle behavior and "
            "macroscopic thermodynamic properties. The partition function encodes "
            "all equilibrium information of a canonical ensemble."
        ),
        "formula": "Z = Σ exp(−Eᵢ/kT),   F = −kT ln Z,   ⟨E⟩ = −∂lnZ/∂β",
        "table_header": ["Ensemble", "Fixed", "Fluctuates", "Potential"],
        "table_rows": [
            ["Microcanonical", "E, V, N", "—", "S(E,V,N)"],
            ["Canonical", "T, V, N", "E", "F(T,V,N)"],
            ["Grand canonical", "T, V, μ", "E, N", "Φ(T,V,μ)"],
            ["Isothermal-isobaric", "T, P, N", "E, V", "G(T,P,N)"],
        ],
        "img_label": "Boltzmann distribution",
        "img_color": (255, 165, 0),
    },
]


def make_image(label: str, bg_color: tuple, index: int) -> str:
    """Generate a simple diagram image and return its path."""
    w, h = 360, 200
    img = PILImage.new("RGB", (w, h), bg_color)
    draw = ImageDraw.Draw(img)

    # Draw a simple plot-like shape
    draw.rectangle([20, 20, w - 20, h - 20], outline="white", width=2)
    # Axes
    draw.line([40, h - 40, w - 40, h - 40], fill="white", width=2)
    draw.line([40, 30, 40, h - 40], fill="white", width=2)

    # Draw a curve
    points = []
    for x in range(50, w - 40, 3):
        t = (x - 50) / (w - 90)
        if index == 0:
            y = h - 50 - int(80 * math.sin(t * math.pi))
        elif index == 1:
            y = h - 50 - int(60 * (1 - t) * 0.8) if t < 0.5 else h - 50 - int(60 * t * 0.6)
        elif index == 2:
            y = h - 50 - int(60 * math.sin(t * 4 * math.pi) * math.exp(-t))
        elif index == 3:
            y = h - 50 - int(70 * abs(math.sin(t * 3 * math.pi)) * math.exp(-t * 2))
        else:
            y = h - 50 - int(70 * math.exp(-(t - 0.4) ** 2 / 0.05))
        points.append((x, max(30, min(h - 30, y))))

    for i in range(len(points) - 1):
        draw.line([points[i], points[i + 1]], fill="yellow", width=2)

    # Label
    draw.text((w // 2 - 50, 5), label, fill="white")

    path = os.path.join(IMG_DIR, f"fig_{index + 1}.png")
    img.save(path)
    return path


def build_pdf():
    doc = SimpleDocTemplate(OUT, pagesize=letter,
                            topMargin=0.6 * inch, bottomMargin=0.6 * inch)
    story = []

    for i, page in enumerate(PAGES):
        if i > 0:
            story.append(Spacer(1, 0.1 * inch))

        # Title
        story.append(Paragraph(f"<b>{page['title']}</b>", styles["Title"]))
        story.append(Spacer(1, 0.15 * inch))

        # Body text
        story.append(Paragraph(page["text"], styles["BodyText"]))
        story.append(Spacer(1, 0.15 * inch))

        # Formula
        story.append(Paragraph(
            f"<i>Key equations:</i>&nbsp;&nbsp; <b>{page['formula']}</b>",
            styles["BodyText"],
        ))
        story.append(Spacer(1, 0.15 * inch))

        # Table
        data = [page["table_header"]] + page["table_rows"]
        t = Table(data, colWidths=[1.8 * inch, 1.2 * inch, 1.2 * inch, 1.5 * inch])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#336699")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f0f0f0"), colors.white]),
            ("ALIGN", (2, 1), (-1, -1), "CENTER"),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.15 * inch))

        # Image
        img_path = make_image(page["img_label"], page["img_color"], i)
        story.append(Paragraph(
            f"<i>Figure {i + 1}: {page['img_label']}</i>", styles["BodyText"]
        ))
        story.append(Spacer(1, 0.05 * inch))
        story.append(RLImage(img_path, width=3.5 * inch, height=1.9 * inch))

        if i < len(PAGES) - 1:
            from reportlab.platypus import PageBreak
            story.append(PageBreak())

    doc.build(story)
    print(f"Created: {OUT}")

    # Cleanup temp images
    import shutil
    shutil.rmtree(IMG_DIR, ignore_errors=True)


if __name__ == "__main__":
    build_pdf()
