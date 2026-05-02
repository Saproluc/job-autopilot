"""
resume_builder.py — Claude-powered ATS resume tailoring.

Takes the user's base resume and a job description,
then generates a tailored, ATS-optimized resume saved as PDF.
"""

import os
import re
import logging
from pathlib import Path
from datetime import datetime

import anthropic
from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.pdfgen import canvas

log = logging.getLogger("job_autopilot.resume")

# ── Prompt for Claude ────────────────────────────────────────────────────────
RESUME_SYSTEM_PROMPT = """You are an expert resume writer and ATS optimization specialist with 15+ years of experience 
in technical recruiting. Your task is to tailor a candidate's resume for a specific job posting.

RULES:
1. Maximize ATS score by naturally weaving in exact keywords from the job description
2. Reorder bullet points to put the most relevant experience FIRST
3. Quantify achievements wherever possible (%, $, time saved, users served)
4. Keep it to ONE page if possible, TWO pages maximum
5. Use strong action verbs: Architected, Deployed, Automated, Reduced, Increased, Led
6. Match the seniority tone to the job level
7. Include ALL skills mentioned in the job description that the candidate has
8. Remove irrelevant experience to make room for relevant keywords
9. Output ONLY valid JSON — no markdown, no preamble

OUTPUT FORMAT (JSON):
{
  "ats_score_estimate": 85,
  "matched_keywords": ["AWS", "Python", "CI/CD"],
  "sections": {
    "header": {
      "name": "Full Name",
      "email": "email@example.com",
      "phone": "555-000-0000",
      "location": "City, ST",
      "linkedin": "linkedin.com/in/profile",
      "github": "github.com/username"
    },
    "summary": "2-3 sentence professional summary with keywords",
    "skills": {
      "Cloud & Infrastructure": ["AWS", "Azure", "Terraform"],
      "Languages & Tools": ["Python", "SQL", "Bash"],
      "CI/CD & DevOps": ["Jenkins", "GitHub Actions", "Docker"]
    },
    "experience": [
      {
        "title": "Job Title",
        "company": "Company Name",
        "dates": "Jan 2023 – Present",
        "location": "City, ST",
        "bullets": [
          "Action verb + task + quantified result",
          "..."
        ]
      }
    ],
    "education": [
      {
        "degree": "MS Information Technology",
        "school": "Clark University",
        "year": "2023",
        "gpa": "3.8",
        "relevant_courses": []
      }
    ],
    "certifications": ["AWS Solutions Architect Associate", "..."]
  }
}"""


class ResumeBuilder:
    def __init__(self, cfg: dict, api_key: str):
        self.cfg = cfg
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = cfg["ai"]["model"]
        self.personal = cfg["personal"]
        self.bio = cfg["ai"].get("personal_bio", "")
        self.output_dir = Path(cfg["output"]["resumes_dir"])
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def create_tailored_resume(
        self,
        job_description: str,
        company: str,
        title: str,
        base_resume_path: str
    ) -> str:
        """
        Generate a tailored, ATS-optimized resume for the given job.
        Returns the path to the saved PDF.
        """
        # Extract text from base resume
        base_text = self._extract_resume_text(base_resume_path)
        
        # Call Claude to tailor
        resume_data = await self._call_claude(
            base_resume_text=base_text,
            job_description=job_description,
            company=company,
            title=title
        )
        
        # Generate output filename
        safe_company = re.sub(r"[^\w\-]", "_", company)[:30]
        safe_title = re.sub(r"[^\w\-]", "_", title)[:30]
        date_str = datetime.now().strftime("%Y%m%d")
        filename = f"{safe_company}_{safe_title}_{date_str}.pdf"
        output_path = self.output_dir / filename
        
        # Render PDF
        self._render_pdf(resume_data, str(output_path))
        
        ats_score = resume_data.get("ats_score_estimate", "?")
        keywords = resume_data.get("matched_keywords", [])
        log.info(f"Resume saved: {filename} | ATS score: {ats_score} | Keywords: {len(keywords)}")
        
        return str(output_path)

    def _extract_resume_text(self, pdf_path: str) -> str:
        """Extract text from user's base resume PDF."""
        try:
            reader = PdfReader(pdf_path)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            return text[:4000]  # Trim to fit context
        except Exception as e:
            log.warning(f"Could not read base resume: {e}")
            # Fall back to bio from config
            return f"Candidate profile:\n{self.bio}"

    async def _call_claude(
        self,
        base_resume_text: str,
        job_description: str,
        company: str,
        title: str
    ) -> dict:
        """Ask Claude to tailor the resume and return structured JSON."""
        import json
        
        user_message = f"""Please tailor this resume for the following job posting.

CANDIDATE'S BASE RESUME:
{base_resume_text}

ADDITIONAL CONTEXT:
{self.bio}

TARGET JOB:
Company: {company}
Title: {title}

JOB DESCRIPTION:
{job_description[:2500]}

Personal details to always include:
- Name: {self.personal['full_name']}
- Email: {self.personal['email']}
- Phone: {self.personal['phone']}
- Location: {self.personal['location']}
- LinkedIn: {self.personal.get('linkedin', '')}
- GitHub: {self.personal.get('github', '')}

Output ONLY valid JSON following the schema in the system prompt. No markdown backticks."""

        message = self.client.messages.create(
            model=self.model,
            max_tokens=2500,
            system=RESUME_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}]
        )
        
        response_text = message.content[0].text.strip()
        
        # Clean up any accidental markdown fences
        response_text = re.sub(r"```json\s*", "", response_text)
        response_text = re.sub(r"```\s*", "", response_text)
        
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            log.warning("Claude returned non-JSON, using fallback resume structure")
            return self._fallback_resume_data(company, title)

    def _fallback_resume_data(self, company: str, title: str) -> dict:
        """Fallback if Claude response can't be parsed."""
        return {
            "ats_score_estimate": 70,
            "matched_keywords": [],
            "sections": {
                "header": {
                    "name": self.personal["full_name"],
                    "email": self.personal["email"],
                    "phone": self.personal["phone"],
                    "location": self.personal["location"],
                    "linkedin": self.personal.get("linkedin", ""),
                    "github": self.personal.get("github", "")
                },
                "summary": f"Experienced IT professional seeking {title} role at {company}.",
                "skills": {},
                "experience": [],
                "education": [],
                "certifications": []
            }
        }

    def _render_pdf(self, data: dict, output_path: str):
        """Render the structured resume data as a clean, modern PDF."""
        sections = data.get("sections", {})
        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            rightMargin=0.6 * inch,
            leftMargin=0.6 * inch,
            topMargin=0.6 * inch,
            bottomMargin=0.6 * inch
        )

        # ── Colors ────────────────────────────────────────────
        PRIMARY = HexColor("#1a365d")    # Dark navy
        ACCENT = HexColor("#2b6cb0")     # Blue
        MUTED = HexColor("#718096")      # Gray
        RULE_COLOR = HexColor("#e2e8f0") # Light gray

        # ── Styles ────────────────────────────────────────────
        styles = getSampleStyleSheet()
        name_style = ParagraphStyle("name", fontSize=22, fontName="Helvetica-Bold",
                                     textColor=PRIMARY, spaceAfter=2)
        contact_style = ParagraphStyle("contact", fontSize=9, fontName="Helvetica",
                                        textColor=MUTED, spaceAfter=4)
        section_style = ParagraphStyle("section", fontSize=11, fontName="Helvetica-Bold",
                                        textColor=ACCENT, spaceBefore=8, spaceAfter=3)
        body_style = ParagraphStyle("body", fontSize=9.5, fontName="Helvetica",
                                     leading=14, spaceAfter=2)
        bullet_style = ParagraphStyle("bullet", fontSize=9.5, fontName="Helvetica",
                                       leading=13, leftIndent=12, spaceAfter=1,
                                       bulletIndent=0)
        job_title_style = ParagraphStyle("job_title", fontSize=10, fontName="Helvetica-Bold",
                                          textColor=PRIMARY, spaceAfter=1)
        job_meta_style = ParagraphStyle("job_meta", fontSize=9, fontName="Helvetica",
                                         textColor=MUTED, spaceAfter=2)

        story = []

        # ── Header ───────────────────────────────────────────
        header = sections.get("header", {})
        story.append(Paragraph(header.get("name", self.personal["full_name"]), name_style))
        
        contact_parts = []
        if header.get("email"):
            contact_parts.append(header["email"])
        if header.get("phone"):
            contact_parts.append(header["phone"])
        if header.get("location"):
            contact_parts.append(header["location"])
        if header.get("linkedin"):
            contact_parts.append(header["linkedin"])
        if header.get("github"):
            contact_parts.append(header["github"])
        
        story.append(Paragraph(" • ".join(contact_parts), contact_style))
        story.append(HRFlowable(width="100%", thickness=1.5, color=ACCENT, spaceAfter=6))

        # ── Summary ──────────────────────────────────────────
        summary = sections.get("summary", "")
        if summary:
            story.append(Paragraph("PROFESSIONAL SUMMARY", section_style))
            story.append(HRFlowable(width="100%", thickness=0.5, color=RULE_COLOR, spaceAfter=4))
            story.append(Paragraph(summary, body_style))
            story.append(Spacer(1, 4))

        # ── Skills ───────────────────────────────────────────
        skills = sections.get("skills", {})
        if skills:
            story.append(Paragraph("TECHNICAL SKILLS", section_style))
            story.append(HRFlowable(width="100%", thickness=0.5, color=RULE_COLOR, spaceAfter=4))
            
            if isinstance(skills, dict):
                for category, skill_list in skills.items():
                    if skill_list:
                        skills_text = f"<b>{category}:</b> {', '.join(skill_list)}"
                        story.append(Paragraph(skills_text, body_style))
            elif isinstance(skills, list):
                story.append(Paragraph(", ".join(skills), body_style))
            
            story.append(Spacer(1, 4))

        # ── Experience ───────────────────────────────────────
        experience = sections.get("experience", [])
        if experience:
            story.append(Paragraph("PROFESSIONAL EXPERIENCE", section_style))
            story.append(HRFlowable(width="100%", thickness=0.5, color=RULE_COLOR, spaceAfter=4))
            
            for exp in experience:
                company_loc = exp.get("company", "")
                if exp.get("location"):
                    company_loc += f" — {exp['location']}"
                
                title_dates = f"<b>{exp.get('title', '')}</b>"
                story.append(Paragraph(title_dates, job_title_style))
                
                meta = f"{company_loc}  |  {exp.get('dates', '')}"
                story.append(Paragraph(meta, job_meta_style))
                
                for bullet in exp.get("bullets", []):
                    story.append(Paragraph(f"• {bullet}", bullet_style))
                
                story.append(Spacer(1, 4))

        # ── Education ────────────────────────────────────────
        education = sections.get("education", [])
        if education:
            story.append(Paragraph("EDUCATION", section_style))
            story.append(HRFlowable(width="100%", thickness=0.5, color=RULE_COLOR, spaceAfter=4))
            
            for edu in education:
                degree_text = f"<b>{edu.get('degree', '')}</b> — {edu.get('school', '')}  |  {edu.get('year', '')}"
                if edu.get("gpa"):
                    degree_text += f"  |  GPA: {edu['gpa']}"
                story.append(Paragraph(degree_text, body_style))
                
                if edu.get("relevant_courses"):
                    courses = ", ".join(edu["relevant_courses"])
                    story.append(Paragraph(f"Relevant Courses: {courses}", 
                                           ParagraphStyle("courses", fontSize=8.5, fontName="Helvetica",
                                                           textColor=MUTED, spaceAfter=2)))
            story.append(Spacer(1, 4))

        # ── Certifications ───────────────────────────────────
        certs = sections.get("certifications", [])
        if certs:
            story.append(Paragraph("CERTIFICATIONS", section_style))
            story.append(HRFlowable(width="100%", thickness=0.5, color=RULE_COLOR, spaceAfter=4))
            story.append(Paragraph(" • ".join(certs), body_style))

        doc.build(story)
