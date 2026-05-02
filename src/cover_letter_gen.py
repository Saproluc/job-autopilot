"""
cover_letter_gen.py — Claude-powered cover letter generation.

Creates a tailored, professional cover letter for each job application.
"""

import re
import logging
from pathlib import Path
from datetime import datetime

import anthropic

log = logging.getLogger("job_autopilot.cover_letter")

COVER_LETTER_SYSTEM = """You are an expert career coach who writes compelling, personalized cover letters 
that get callbacks. You write letters that:
- Sound genuinely human, not robotic or AI-generated
- Open with a hook specific to the company, not "I am writing to apply for..."
- Connect the candidate's specific experience to the role's exact needs
- Show cultural fit and enthusiasm without being sycophantic
- Are concise: 3 short paragraphs max, under 300 words
- End with a confident, specific call to action

Output ONLY the cover letter text. No subject line, no filename, no commentary."""


class CoverLetterGenerator:
    def __init__(self, cfg: dict, api_key: str):
        self.cfg = cfg
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = cfg["ai"]["model"]
        self.personal = cfg["personal"]
        self.bio = cfg["ai"].get("personal_bio", "")
        self.tone = cfg["ai"].get("cover_letter_tone", "professional")
        self.output_dir = Path(cfg["output"]["cover_letters_dir"])
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def generate(self, job_description: str, company: str, title: str) -> str:
        """
        Generate a tailored cover letter and save it.
        Returns the path to the saved text file.
        """
        letter_text = await self._call_claude(job_description, company, title)
        
        # Save to file
        safe_company = re.sub(r"[^\w\-]", "_", company)[:30]
        safe_title = re.sub(r"[^\w\-]", "_", title)[:30]
        date_str = datetime.now().strftime("%Y%m%d")
        filename = f"{safe_company}_{safe_title}_{date_str}.txt"
        output_path = self.output_dir / filename
        
        full_letter = self._format_letter(letter_text, company, title)
        output_path.write_text(full_letter, encoding="utf-8")
        
        log.info(f"Cover letter saved: {filename}")
        return str(output_path)

    async def _call_claude(self, job_description: str, company: str, title: str) -> str:
        """Ask Claude to write the cover letter."""
        today = datetime.now().strftime("%B %d, %Y")
        
        user_message = f"""Write a cover letter for this application.

CANDIDATE BACKGROUND:
{self.bio}

Name: {self.personal['full_name']}
Email: {self.personal['email']}
Phone: {self.personal['phone']}
Location: {self.personal['location']}

TARGET ROLE:
Company: {company}
Position: {title}
Date: {today}

JOB DESCRIPTION:
{job_description[:2000]}

Tone: {self.tone}
Instructions: Make it sound authentic and specific to THIS company and role. 
Avoid clichés like "I am a team player" or "I am passionate about...".
Write 3 tight paragraphs. Under 280 words total."""

        message = self.client.messages.create(
            model=self.model,
            max_tokens=700,
            system=COVER_LETTER_SYSTEM,
            messages=[{"role": "user", "content": user_message}]
        )
        
        return message.content[0].text.strip()

    def _format_letter(self, body: str, company: str, title: str) -> str:
        """Add header/footer formatting to the cover letter body."""
        today = datetime.now().strftime("%B %d, %Y")
        p = self.personal
        
        header = f"""{p['full_name']}
{p['email']}  |  {p['phone']}
{p['location']}
{p.get('linkedin', '')}

{today}

Hiring Manager
{company}

Re: {title}

"""
        footer = f"""

Sincerely,

{p['full_name']}
"""
        return header + body + footer
