"""
job_searcher.py — Finds matching jobs across multiple platforms.

Searches LinkedIn, Indeed, Glassdoor, and Dice based on user config.
Returns a list of job dicts with title, company, description, URL, etc.
"""

import asyncio
import logging
from typing import Optional
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

log = logging.getLogger("job_autopilot.searcher")


class JobSearcher:
    def __init__(self, cfg: dict, platform_filter: Optional[str] = None):
        self.cfg = cfg
        self.platform_filter = platform_filter
        self.prefs = cfg["job_search"]
        self.platforms = cfg["platforms"]

    async def search_all(self, max_results: int = 100) -> list[dict]:
        """Search all enabled platforms and return merged, deduplicated job list."""
        all_jobs = []
        per_platform = max(max_results // 4, 10)

        tasks = []

        if self._platform_enabled("linkedin"):
            tasks.append(self._search_linkedin(per_platform))
        if self._platform_enabled("indeed"):
            tasks.append(self._search_indeed(per_platform))
        if self._platform_enabled("glassdoor"):
            tasks.append(self._search_glassdoor(per_platform))
        if self._platform_enabled("dice"):
            tasks.append(self._search_dice(per_platform))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                log.error(f"Platform search error: {result}")
                continue
            all_jobs.extend(result)

        # Deduplicate by URL
        seen_urls = set()
        unique_jobs = []
        for job in all_jobs:
            url = job.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_jobs.append(job)

        # Filter by user preferences
        filtered = self._apply_filters(unique_jobs)
        log.info(f"Found {len(all_jobs)} raw jobs → {len(filtered)} after filtering")
        return filtered[:max_results]

    def _platform_enabled(self, name: str) -> bool:
        if self.platform_filter:
            return self.platform_filter.lower() == name.lower()
        p = self.platforms.get(name)
        if isinstance(p, dict):
            return p.get("enabled", True)
        return bool(p)

    def _apply_filters(self, jobs: list[dict]) -> list[dict]:
        """Apply keyword and exclusion filters."""
        exclude = [kw.lower() for kw in self.prefs.get("exclude_keywords", [])]
        filtered = []
        for job in jobs:
            text = f"{job.get('title','')} {job.get('description','')}".lower()
            if any(ex in text for ex in exclude):
                log.debug(f"Excluded: {job.get('title')} at {job.get('company')}")
                continue
            filtered.append(job)
        return filtered

    # ─────────────────────────────────────────────────────────
    # LinkedIn
    # ─────────────────────────────────────────────────────────
    async def _search_linkedin(self, limit: int) -> list[dict]:
        log.info("Searching LinkedIn...")
        jobs = []
        try:
            for title in self.prefs["titles"][:3]:  # Top 3 titles
                for location in self.prefs["locations"][:2]:
                    batch = await self._linkedin_query(title, location, limit // 6)
                    jobs.extend(batch)
                    await asyncio.sleep(1.5)  # Be polite
        except Exception as e:
            log.error(f"LinkedIn search error: {e}")
        return jobs

    async def _linkedin_query(self, title: str, location: str, limit: int) -> list[dict]:
        """Scrape LinkedIn public job search (no login required for basic results)."""
        jobs = []
        try:
            query = title.replace(" ", "%20")
            loc = location.replace(", ", "%2C%20").replace(" ", "%20")
            url = (
                f"https://www.linkedin.com/jobs/search?"
                f"keywords={query}&location={loc}&f_JT=F&f_E=2%2C3&start=0"
            )
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/124.0.0.0 Safari/537.36"
            }
            
            async with httpx.AsyncClient(headers=headers, timeout=15) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return jobs
                
                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.select("div.base-card")[:limit]
                
                for card in cards:
                    try:
                        job_title = card.select_one("h3.base-search-card__title")
                        company = card.select_one("h4.base-search-card__subtitle")
                        job_location = card.select_one("span.job-search-card__location")
                        link = card.select_one("a.base-card__full-link")
                        
                        if not (job_title and company and link):
                            continue
                        
                        jobs.append({
                            "title": job_title.get_text(strip=True),
                            "company": company.get_text(strip=True),
                            "location": job_location.get_text(strip=True) if job_location else location,
                            "url": link["href"].split("?")[0],
                            "platform": "LinkedIn",
                            "description": "",  # Fetched separately
                            "date_found": datetime.now().isoformat(),
                        })
                    except Exception:
                        continue
        except Exception as e:
            log.warning(f"LinkedIn query failed ({title}): {e}")
        return jobs

    # ─────────────────────────────────────────────────────────
    # Indeed
    # ─────────────────────────────────────────────────────────
    async def _search_indeed(self, limit: int) -> list[dict]:
        log.info("Searching Indeed...")
        jobs = []
        try:
            for title in self.prefs["titles"][:3]:
                for location in self.prefs["locations"][:2]:
                    batch = await self._indeed_query(title, location, limit // 6)
                    jobs.extend(batch)
                    await asyncio.sleep(1.5)
        except Exception as e:
            log.error(f"Indeed search error: {e}")
        return jobs

    async def _indeed_query(self, title: str, location: str, limit: int) -> list[dict]:
        jobs = []
        try:
            query = title.replace(" ", "+")
            loc = location.replace(", ", "%2C+").replace(" ", "+")
            url = f"https://www.indeed.com/jobs?q={query}&l={loc}&limit={limit}&sort=date"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9"
            }
            
            async with httpx.AsyncClient(headers=headers, timeout=15, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return jobs
                
                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.select("div.job_seen_beacon")[:limit]
                
                for card in cards:
                    try:
                        job_title_el = card.select_one("h2.jobTitle span")
                        company_el = card.select_one("span[data-testid='company-name']")
                        location_el = card.select_one("div[data-testid='text-location']")
                        link_el = card.select_one("a[id^='job_']")
                        
                        if not (job_title_el and link_el):
                            continue
                        
                        job_id = link_el.get("id", "").replace("job_", "")
                        job_url = f"https://www.indeed.com/viewjob?jk={job_id}"
                        
                        jobs.append({
                            "title": job_title_el.get_text(strip=True),
                            "company": company_el.get_text(strip=True) if company_el else "Unknown",
                            "location": location_el.get_text(strip=True) if location_el else location,
                            "url": job_url,
                            "platform": "Indeed",
                            "description": "",
                            "date_found": datetime.now().isoformat(),
                        })
                    except Exception:
                        continue
        except Exception as e:
            log.warning(f"Indeed query failed ({title}): {e}")
        return jobs

    # ─────────────────────────────────────────────────────────
    # Glassdoor
    # ─────────────────────────────────────────────────────────
    async def _search_glassdoor(self, limit: int) -> list[dict]:
        log.info("Searching Glassdoor...")
        jobs = []
        try:
            for title in self.prefs["titles"][:2]:
                for location in self.prefs["locations"][:2]:
                    batch = await self._glassdoor_query(title, location, limit // 4)
                    jobs.extend(batch)
                    await asyncio.sleep(2)
        except Exception as e:
            log.error(f"Glassdoor search error: {e}")
        return jobs

    async def _glassdoor_query(self, title: str, location: str, limit: int) -> list[dict]:
        # Glassdoor API endpoint (public)
        jobs = []
        try:
            params = {
                "keyword": title,
                "locT": "C",
                "locId": "1147401" if "remote" in location.lower() else "1147401",
                "jobType": "fulltime",
                "fromAge": 7,
                "maxResults": limit,
            }
            url = "https://www.glassdoor.com/Job/jobs.htm"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0",
            }
            async with httpx.AsyncClient(headers=headers, timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, params=params)
                if resp.status_code != 200:
                    return jobs
                
                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.select("li[data-test='jobListing']")[:limit]
                
                for card in cards:
                    try:
                        title_el = card.select_one("a[data-test='job-title']")
                        company_el = card.select_one("div.EmployerProfile_employerInfo__GaPbq")
                        location_el = card.select_one("div[data-test='emp-location']")
                        
                        if not title_el:
                            continue
                        
                        href = title_el.get("href", "")
                        full_url = f"https://www.glassdoor.com{href}" if href.startswith("/") else href
                        
                        jobs.append({
                            "title": title_el.get_text(strip=True),
                            "company": company_el.get_text(strip=True) if company_el else "Unknown",
                            "location": location_el.get_text(strip=True) if location_el else location,
                            "url": full_url,
                            "platform": "Glassdoor",
                            "description": "",
                            "date_found": datetime.now().isoformat(),
                        })
                    except Exception:
                        continue
        except Exception as e:
            log.warning(f"Glassdoor query failed ({title}): {e}")
        return jobs

    # ─────────────────────────────────────────────────────────
    # Dice — great for tech + OPT/H1B sponsorship roles
    # ─────────────────────────────────────────────────────────
    async def _search_dice(self, limit: int) -> list[dict]:
        log.info("Searching Dice...")
        jobs = []
        try:
            for title in self.prefs["titles"][:3]:
                batch = await self._dice_query(title, limit // 3)
                jobs.extend(batch)
                await asyncio.sleep(1.5)
        except Exception as e:
            log.error(f"Dice search error: {e}")
        return jobs

    async def _dice_query(self, title: str, limit: int) -> list[dict]:
        jobs = []
        try:
            # Dice public API
            api_url = "https://job-search-api.svc.dhigroupinc.com/v1/dice/jobs/search"
            params = {
                "q": title,
                "countryCode2": "US",
                "radius": "30",
                "radiusUnit": "mi",
                "page": 1,
                "pageSize": min(limit, 20),
                "language": "en",
                "eid": "27"
            }
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0",
                "x-api-key": "1YAt0R9wBg4WfsF9VB2778F5CHLAPMVW3WAZcKd8",
            }
            async with httpx.AsyncClient(headers=headers, timeout=15) as client:
                resp = await client.get(api_url, params=params)
                if resp.status_code != 200:
                    return jobs
                
                data = resp.json()
                for item in data.get("data", [])[:limit]:
                    jobs.append({
                        "title": item.get("title", ""),
                        "company": item.get("hiringOrganization", {}).get("name", "Unknown"),
                        "location": item.get("jobLocation", [{}])[0].get("displayName", "Remote"),
                        "url": f"https://www.dice.com/job-detail/{item.get('id','')}",
                        "platform": "Dice",
                        "description": item.get("descriptionFragment", ""),
                        "date_found": datetime.now().isoformat(),
                    })
        except Exception as e:
            log.warning(f"Dice query failed ({title}): {e}")
        return jobs

    async def fetch_job_description(self, job_url: str, platform: str) -> str:
        """Fetch full job description from job URL."""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"
            }
            async with httpx.AsyncClient(headers=headers, timeout=20, follow_redirects=True) as client:
                resp = await client.get(job_url)
                if resp.status_code != 200:
                    return ""
                
                soup = BeautifulSoup(resp.text, "html.parser")
                
                # Remove noise
                for tag in soup.select("script, style, nav, footer, header"):
                    tag.decompose()
                
                # Platform-specific selectors
                selectors = {
                    "LinkedIn": "div.description__text",
                    "Indeed": "div#jobDescriptionText",
                    "Glassdoor": "div.jobDescriptionContent",
                    "Dice": "div.job-description",
                }
                
                sel = selectors.get(platform)
                if sel:
                    el = soup.select_one(sel)
                    if el:
                        return el.get_text(separator="\n", strip=True)[:3000]
                
                # Fallback: get largest text block
                paragraphs = soup.find_all("p")
                text = "\n".join(p.get_text(strip=True) for p in paragraphs)
                return text[:3000]
        except Exception as e:
            log.warning(f"Could not fetch description for {job_url}: {e}")
            return ""
