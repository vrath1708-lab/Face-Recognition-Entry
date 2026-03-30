# -*- coding: utf-8 -*-
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

output_path = r"g:\Premium face recognition entry\ARCHITECTURE.pdf"
doc = SimpleDocTemplate(output_path, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
styles = getSampleStyleSheet()

styles.add(ParagraphStyle(name='TitleCustomX', parent=styles['Title'], fontSize=20, leading=24, spaceAfter=12))
styles.add(ParagraphStyle(name='H2X', parent=styles['Heading2'], fontSize=13, leading=16, spaceAfter=8, textColor=colors.HexColor('#1f2937')))
styles.add(ParagraphStyle(name='BodyX', parent=styles['BodyText'], fontSize=10.5, leading=14))
styles.add(ParagraphStyle(name='BulletX', parent=styles['BodyText'], fontSize=10.5, leading=14, leftIndent=14, bulletIndent=4))

story = []

story.append(Paragraph("Face Recognition Entry System - Architecture", styles['TitleCustomX']))
story.append(Paragraph("Version: Current implementation (FastAPI + SQLite + OpenCV + SMTP notifications)", styles['BodyX']))
story.append(Spacer(1, 10))

story.append(Paragraph("1) System Overview", styles['H2X']))
story.append(Paragraph("The application implements a VIP access workflow: users submit face-based applications, admins review and decide approval status, and gate verification allows entry only for approved users whose face matches in real-time.", styles['BodyX']))
story.append(Spacer(1, 6))

for line in [
    "Client layer: Home, User Portal, Admin Portal, Gate Live page",
    "Backend layer: FastAPI HTTP APIs + WebSocket stream endpoint",
    "Recognition layer: OpenCV face detection + selectable recognition backend (legacy/ml/hybrid/lbph)",
    "Data layer: SQLite members table + audit event log",
    "Notification layer: SMTP email on admin decision (approved/rejected)",
]:
    story.append(Paragraph(line, styles['BulletX'], bulletText='-'))

story.append(Spacer(1, 10))
story.append(Paragraph("2) Core Workflow", styles['H2X']))
workflow_data = [
    ["Step", "Actor", "Action", "System Effect"],
    ["1", "User", "Register with name + email + face capture", "Creates pending application in members DB"],
    ["2", "Admin", "Review pending records in Admin Dashboard", "Can update name/email/status/note"],
    ["3", "Admin", "Approve or reject application", "Status persisted + audit event logged"],
    ["4", "Backend", "Send SMTP decision email", "Immediate email attempt to registered email"],
    ["5", "Gate", "Stream frames to /ws/gate-live", "ALLOW only for approved + matched face"],
]

workflow_table = Table(workflow_data, colWidths=[40, 70, 180, 200])
workflow_table.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#e5e7eb')),
    ('TEXTCOLOR', (0,0), (-1,0), colors.black),
    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
    ('GRID', (0,0), (-1,-1), 0.4, colors.HexColor('#9ca3af')),
    ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
    ('FONTSIZE', (0,0), (-1,-1), 9),
    ('LEFTPADDING', (0,0), (-1,-1), 6),
    ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ('TOPPADDING', (0,0), (-1,-1), 5),
    ('BOTTOMPADDING', (0,0), (-1,-1), 5),
]))
story.append(workflow_table)

story.append(PageBreak())
story.append(Paragraph("3) Backend/API Architecture", styles['H2X']))

api_sections = [
    ("Authentication", ["POST /api/auth/login", "GET /api/auth/me", "POST /api/auth/logout"]),
    ("Registration", ["POST /api/register (name, email, image)"]),
    ("Admin Management", ["GET /api/admin/users", "GET /api/admin/users/{member_id}", "POST /api/admin/users/update", "DELETE /api/admin/users/{member_id}"]),
    ("Review Decisions", ["POST /api/applications/decision"]),
    ("Gate Access", ["POST /api/gate/verify", "WS /ws/gate-live"]),
    ("Audit", ["GET /api/events", "GET /api/health"]),
]

for title, endpoints in api_sections:
    story.append(Paragraph(f"{title}", styles['BodyX']))
    for ep in endpoints:
        story.append(Paragraph(ep, styles['BulletX'], bulletText='-'))
    story.append(Spacer(1, 4))

story.append(Spacer(1, 8))
story.append(Paragraph("4) Recognition Layer", styles['H2X']))
for line in [
    "Face detection: OpenCV Haar Cascade (largest detected face selected)",
    "Backend switch via EMBEDDING_BACKEND: legacy, ml, hybrid, lbph",
    "legacy: grayscale flatten embedding + cosine similarity",
    "ml: LBP + HOG embedding + cosine similarity",
    "hybrid: concatenated legacy + ml embedding",
    "lbph: LBPH recognizer path using approved stored face images",
    "Decision rule: match confidence threshold + approved application status",
]:
    story.append(Paragraph(line, styles['BulletX'], bulletText='-'))

story.append(Spacer(1, 8))
story.append(Paragraph("5) Data Model", styles['H2X']))
for line in [
    "Primary table: members",
    "Key fields: member_id, name, email, embedding, face_image, application_status",
    "Review metadata: review_note, reviewed_by, reviewed_at, created_at",
    "Audit log: events.log for registration, decisions, gate attempts, and email notification attempts",
]:
    story.append(Paragraph(line, styles['BulletX'], bulletText='-'))

story.append(Spacer(1, 8))
story.append(Paragraph("6) Email Notification Architecture", styles['H2X']))
for line in [
    "Trigger: admin decision changed to approved/rejected",
    "Transport: SMTP (generic SMTP_* variables, with backward-compatible RESEND_* fallback)",
    "Behavior: decision update is not blocked if email fails",
    "Observability: email success/failure stored in audit events",
]:
    story.append(Paragraph(line, styles['BulletX'], bulletText='-'))

story.append(Spacer(1, 8))
story.append(Paragraph("7) Security and Reliability Notes", styles['H2X']))
for line in [
    "Role-based token auth for admin-protected endpoints",
    "Public registration endpoint limited to face application submission",
    "Gate decision always enforces approved-status check",
    "UI and APIs remain backward-compatible for legacy admin actions",
]:
    story.append(Paragraph(line, styles['BulletX'], bulletText='-'))

story.append(Spacer(1, 10))
story.append(Paragraph("Generated automatically for evaluation handoff.", styles['BodyX']))

doc.build(story)
print(output_path)
