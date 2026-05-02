"""
form_filler.py — Playwright browser automation for filling job application forms.

Opens Chrome, navigates to each job, fills in application fields,
then PAUSES and leaves the tab open for the user to review and submit.
Claude never auto-submits — you are always in control.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional
from datetime import datetime

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

log = logging.getLogger("job_autopilot.form_filler")

# ── Field detection patterns ───────────────────────────────────────────────
# Maps field labels/placeholders to config keys
FIELD_PATTERNS = {
    # Name fields
    "first.name|firstname|first_name": "first_name",
    "last.name|lastname|last_name|surname": "last_name",
    "full.name|fullname|your.name|name": "full_name",
    
    # Contact
    r"e.?mail": "email",
    r"phone|mobile|cell|telephone": "phone",
    
    # Location
    r"city|location|address": "location",
    r"state|province": "state",
    r"zip|postal": "zip",
    r"country": "country",
    
    # Professional
    r"linkedin": "linkedin",
    r"github|git.hub": "github",
    r"portfolio|website|url": "portfolio",
    r"salary|compensation|expected": "salary_expectation",
    
    # Work authorization
    r"authorized|authorization|eligible.to.work|work.authorization": "work_auth",
    r"sponsor|visa|sponsorship": "sponsorship",
    r"start.date|available|availability": "start_date",
}


class FormFiller:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.personal = cfg["personal"]
        self.browser_cfg = cfg.get("browser", {})
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self._playwright = None
        self._tab_count = 0
        self._open_pages: list[Page] = []

        # Pre-compute fill values
        name_parts = self.personal["full_name"].split(" ", 1)
        self.fill_values = {
            "first_name": name_parts[0] if name_parts else "",
            "last_name": name_parts[1] if len(name_parts) > 1 else "",
            "full_name": self.personal["full_name"],
            "email": self.personal["email"],
            "phone": self.personal["phone"],
            "location": self.personal["location"],
            "state": self.personal["location"].split(", ")[-1] if "," in self.personal["location"] else "",
            "city": self.personal["location"].split(",")[0] if "," in self.personal["location"] else self.personal["location"],
            "zip": "",
            "country": "United States",
            "linkedin": self.personal.get("linkedin", ""),
            "github": self.personal.get("github", ""),
            "portfolio": self.personal.get("portfolio", ""),
            "salary_expectation": str(cfg["job_search"].get("salary_min", "80000")),
            "work_auth": self.personal.get("work_authorization", "Yes"),
            "sponsorship": "Yes" if cfg["job_search"].get("sponsorship_required") else "No",
            "start_date": "2 weeks",
        }

    async def _init_browser(self):
        """Launch or reuse Playwright Chrome browser."""
        if self.browser and self.browser.is_connected():
            return
        
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(
            headless=self.browser_cfg.get("headless", False),
            slow_mo=self.browser_cfg.get("slow_mo", 500),
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
            channel="chrome"  # Use system Chrome
        )
        self.context = await self.browser.new_context(
            viewport={"width": 1400, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36"
        )
        log.info("Browser launched")

    async def fill_application(self, job: dict) -> dict:
        """
        Navigate to the job URL, detect the application form, fill it in,
        and leave the tab open for user review.
        
        Returns: dict with status and tab_index
        """
        await self._init_browser()
        
        url = job.get("url", "")
        platform = job.get("platform", "")
        resume_path = job.get("resume_path", "")
        cover_letter_path = job.get("cover_letter_path", "")
        
        try:
            page = await self.context.new_page()
            self._open_pages.append(page)
            self._tab_count += 1
            tab_index = self._tab_count
            
            # Navigate
            log.info(f"Opening [{tab_index}] {job['company']} — {job['title']}")
            await page.goto(url, timeout=self.browser_cfg.get("page_load_timeout", 30) * 1000)
            await page.wait_for_load_state("networkidle", timeout=10000)
            
            # Pause before interacting
            pause = self.browser_cfg.get("tab_pause_seconds", 3)
            await asyncio.sleep(pause)
            
            # Platform-specific flow
            if platform == "LinkedIn":
                status = await self._fill_linkedin(page, job, resume_path)
            elif platform == "Indeed":
                status = await self._fill_indeed(page, job, resume_path)
            else:
                # Generic form filling
                status = await self._fill_generic(page, job, resume_path, cover_letter_path)
            
            # Add visual banner so user knows which tab is which
            await self._inject_review_banner(page, job, tab_index)
            
            return {"status": status, "tab_index": tab_index}
            
        except Exception as e:
            log.error(f"Form fill error for {job['company']}: {e}")
            return {"status": f"error: {str(e)[:100]}", "tab_index": self._tab_count}

    async def _fill_linkedin(self, page: Page, job: dict, resume_path: str) -> str:
        """Handle LinkedIn Easy Apply flow."""
        try:
            # Click Easy Apply button
            easy_apply_btn = page.locator("button.jobs-apply-button, button[aria-label*='Easy Apply']")
            if await easy_apply_btn.count() > 0:
                await easy_apply_btn.first.click()
                await asyncio.sleep(2)
            
            # Fill modal form fields
            await self._fill_form_fields(page, resume_path=resume_path)
            
            # Navigate through multi-step form (but NEVER click final Submit)
            for step in range(5):  # Max 5 steps
                next_btn = page.locator("button[aria-label='Continue to next step'], button[aria-label='Review your application']")
                if await next_btn.count() > 0:
                    await next_btn.first.click()
                    await asyncio.sleep(1.5)
                    await self._fill_form_fields(page, resume_path=resume_path)
                else:
                    break
            
            # Stop before the Submit button — leave for user
            log.info(f"LinkedIn: Form filled through last step. Awaiting user submit.")
            return "linkedin_ready_to_submit"
            
        except Exception as e:
            log.warning(f"LinkedIn form error: {e}")
            return f"linkedin_partial: {e}"

    async def _fill_indeed(self, page: Page, job: dict, resume_path: str) -> str:
        """Handle Indeed application flow."""
        try:
            # Click Apply button
            apply_btn = page.locator("button#indeedApplyButton, a[href*='apply'], button[data-testid='apply-button']")
            if await apply_btn.count() > 0:
                await apply_btn.first.click()
                await asyncio.sleep(2)
            
            await self._fill_form_fields(page, resume_path=resume_path)
            return "indeed_ready_to_submit"
            
        except Exception as e:
            log.warning(f"Indeed form error: {e}")
            return f"indeed_partial: {e}"

    async def _fill_generic(self, page: Page, job: dict, resume_path: str, cover_letter_path: str) -> str:
        """Generic form detection and filling for any job board."""
        try:
            # Look for Apply button variations
            apply_selectors = [
                "a[href*='apply']",
                "button:has-text('Apply')",
                "a:has-text('Apply Now')",
                "a:has-text('Apply for this job')",
                "button:has-text('Apply Now')",
            ]
            
            for selector in apply_selectors:
                btn = page.locator(selector)
                if await btn.count() > 0:
                    await btn.first.click()
                    await asyncio.sleep(2)
                    break
            
            await self._fill_form_fields(page, resume_path=resume_path, 
                                          cover_letter_path=cover_letter_path)
            return "generic_ready_to_submit"
            
        except Exception as e:
            log.warning(f"Generic form error: {e}")
            return f"generic_partial: {e}"

    async def _fill_form_fields(self, page: Page, resume_path: str = "", 
                                 cover_letter_path: str = ""):
        """
        Detect and fill all visible form fields on the current page.
        Handles text inputs, selects, file uploads, and textareas.
        """
        import re
        
        # ── Text inputs and textareas ────────────────────────
        fields = await page.query_selector_all("input[type='text'], input[type='email'], input[type='tel'], input:not([type]), textarea")
        
        for field in fields:
            try:
                if not await field.is_visible():
                    continue
                
                # Get identifying attributes
                label_text = await self._get_field_label(page, field)
                placeholder = await field.get_attribute("placeholder") or ""
                name_attr = await field.get_attribute("name") or ""
                id_attr = await field.get_attribute("id") or ""
                
                # Combined hint for matching
                hint = f"{label_text} {placeholder} {name_attr} {id_attr}".lower()
                
                fill_value = self._match_field(hint)
                if fill_value:
                    await field.click()
                    await field.fill(fill_value)
                    await asyncio.sleep(0.3)
                    log.debug(f"Filled field: '{hint[:40]}' → '{fill_value[:30]}'")
            except Exception:
                continue

        # ── Select dropdowns ─────────────────────────────────
        selects = await page.query_selector_all("select")
        for select in selects:
            try:
                if not await select.is_visible():
                    continue
                
                name_attr = await select.get_attribute("name") or ""
                id_attr = await select.get_attribute("id") or ""
                label_text = await self._get_field_label(page, select)
                hint = f"{label_text} {name_attr} {id_attr}".lower()
                
                # Work authorization dropdowns
                if re.search(r"authorized|work.auth|eligible|legal", hint):
                    await select.select_option(value="yes") if "yes" in str(await select.inner_html()).lower() else None
                elif re.search(r"sponsor|visa", hint):
                    await select.select_option(label="No") if "no" in str(await select.inner_html()).lower() else None
                elif re.search(r"experience|years", hint):
                    await select.select_option(index=2)  # Usually "2-5 years"
                    
            except Exception:
                continue

        # ── File upload: Resume ──────────────────────────────
        if resume_path and Path(resume_path).exists():
            resume_inputs = await page.query_selector_all(
                "input[type='file'][accept*='pdf'], input[type='file'][name*='resume'], "
                "input[type='file'][name*='cv'], input[type='file']"
            )
            for inp in resume_inputs[:1]:  # Upload to first file input only
                try:
                    await inp.set_input_files(resume_path)
                    log.debug(f"Uploaded resume: {Path(resume_path).name}")
                    await asyncio.sleep(1)
                except Exception:
                    pass

        # ── Textarea: Cover letter ───────────────────────────
        if cover_letter_path and Path(cover_letter_path).exists():
            cover_text = Path(cover_letter_path).read_text(encoding="utf-8")
            # Find cover letter textarea
            textareas = await page.query_selector_all("textarea")
            for ta in textareas:
                try:
                    name = (await ta.get_attribute("name") or "").lower()
                    placeholder = (await ta.get_attribute("placeholder") or "").lower()
                    label_text = (await self._get_field_label(page, ta)).lower()
                    hint = f"{name} {placeholder} {label_text}"
                    
                    if any(word in hint for word in ["cover", "letter", "message", "motivation", "why"]):
                        await ta.fill(cover_text[:2000])
                        break
                except Exception:
                    continue

    async def _get_field_label(self, page: Page, element) -> str:
        """Try to find the label text for a form element."""
        try:
            el_id = await element.get_attribute("id")
            if el_id:
                label = page.locator(f"label[for='{el_id}']")
                if await label.count() > 0:
                    return await label.inner_text()
            
            # Check aria-label
            aria = await element.get_attribute("aria-label") or ""
            if aria:
                return aria
            
            # Check parent text
            parent_text = await element.evaluate(
                """(el) => {
                    const parent = el.closest('div, fieldset, li');
                    if (!parent) return '';
                    const label = parent.querySelector('label, span, p');
                    return label ? label.innerText : '';
                }"""
            )
            return parent_text or ""
        except Exception:
            return ""

    def _match_field(self, hint: str) -> Optional[str]:
        """Match a form field hint to a fill value."""
        import re
        
        mapping = {
            r"first.?name|given.?name": self.fill_values["first_name"],
            r"last.?name|family.?name|surname": self.fill_values["last_name"],
            r"full.?name|your.?name|^name$|full name": self.fill_values["full_name"],
            r"e.?mail": self.fill_values["email"],
            r"phone|mobile|cell|tel": self.fill_values["phone"],
            r"city": self.fill_values["city"],
            r"state": self.fill_values["state"],
            r"zip|postal": self.fill_values["zip"],
            r"country": self.fill_values["country"],
            r"linkedin": self.fill_values["linkedin"],
            r"github": self.fill_values["github"],
            r"portfolio|website|personal.url": self.fill_values["portfolio"],
            r"salary|compensation": self.fill_values["salary_expectation"],
            r"start.?date|available|earliest": self.fill_values["start_date"],
        }
        
        for pattern, value in mapping.items():
            if re.search(pattern, hint) and value:
                return value
        return None

    async def _inject_review_banner(self, page: Page, job: dict, tab_index: int):
        """Inject a visible banner on the page reminding user to review before submitting."""
        banner_js = f"""
        const banner = document.createElement('div');
        banner.id = 'job-autopilot-banner';
        banner.style.cssText = `
            position: fixed; top: 0; left: 0; right: 0; z-index: 999999;
            background: linear-gradient(90deg, #1a365d, #2b6cb0);
            color: white; padding: 12px 20px;
            font-family: -apple-system, BlinkMacSystemFont, sans-serif;
            font-size: 14px; display: flex; align-items: center;
            justify-content: space-between; box-shadow: 0 2px 10px rgba(0,0,0,0.3);
        `;
        banner.innerHTML = `
            <span>🤖 <b>Job AutoPilot</b> — Tab #{tab_index}</span>
            <span style="font-size:16px"><b>{job['company']}</b> — {job['title']}</span>
            <span style="background:#f6e05e; color:#1a365d; padding:4px 12px; border-radius:4px; font-weight:bold">
                ⚠️ Review &amp; Submit Manually
            </span>
        `;
        document.body.prepend(banner);
        document.body.style.marginTop = '50px';
        """
        try:
            await page.evaluate(banner_js)
        except Exception:
            pass

    async def done(self):
        """Called after all jobs processed. Keep browser open, show message."""
        log.info(f"All {self._tab_count} tabs filled and open for review.")
        # Don't close browser — let user review and submit manually

    async def close(self):
        """Force close browser (not called in normal flow)."""
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()
