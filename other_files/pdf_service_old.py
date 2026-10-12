from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)


class PDFService:
    def __init__(self, output_dir="output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def create_invention_pdf(
        self,
        session_id,
        invention,
    ):
        output_file = self.output_dir / f"{session_id}_invention_analysis.pdf"

        styles = getSampleStyleSheet()

        doc = SimpleDocTemplate(
            str(output_file),
            pagesize=A4,
            rightMargin=40,
            leftMargin=40,
            topMargin=40,
            bottomMargin=40,
        )

        story = []

        story.append(Paragraph("Invention Analysis", styles["Title"]))

        story.append(Spacer(1, 12))

        story.append(Paragraph(f"<b>Session ID:</b> {session_id}", styles["Normal"]))

        story.append(Spacer(1, 15))

        # Summary
        story.append(Paragraph("Invention Summary", styles["Heading2"]))

        story.append(Paragraph(invention.invention_summary, styles["BodyText"]))

        # Structural features
        story.append(Spacer(1, 15))

        story.append(Paragraph("Structural Features", styles["Heading2"]))

        structural_items = []

        for feature in invention.structural_features:
            text = (
                f"<b>{feature.feature_id}:</b> {feature.feature}<br/>{feature.details}"
            )

            structural_items.append(ListItem(Paragraph(text, styles["BodyText"])))

        story.append(ListFlowable(structural_items, bulletType="bullet"))

        # Procedural features
        story.append(Spacer(1, 15))

        story.append(Paragraph("Procedural / Process Features", styles["Heading2"]))

        process_items = []

        for feature in invention.procedural_features:
            text = f"<b>{feature.feature_id}:</b> {feature.step}<br/>{feature.details}"

            process_items.append(ListItem(Paragraph(text, styles["BodyText"])))

        story.append(ListFlowable(process_items, bulletType="bullet"))

        # Functional features
        story.append(Spacer(1, 15))

        story.append(Paragraph("Functional Features", styles["Heading2"]))

        function_items = []

        for feature in invention.functional_features:
            text = (
                f"<b>{feature.feature_id}:</b> {feature.function}<br/>{feature.details}"
            )

            function_items.append(ListItem(Paragraph(text, styles["BodyText"])))

        story.append(ListFlowable(function_items, bulletType="bullet"))

        doc.build(story)

        return str(output_file)
