# tools/serper_job_search_tool.py
from crewai.tools import BaseTool
import http.client
import json
import os
from typing import List, Dict
from datetime import datetime
from dotenv import load_dotenv
from utils.logger import logger
from .job_deduplication import JobDeduplicator
from .job_relevance_scorer import JobRelevanceScorer

load_dotenv()


class SerperJobSearchTool(BaseTool):
    name: str = "Serper Job Search Tool"
    description: str = "Searches for job listings using Serper.dev based on keywords and locations."

    def _run(self, keywords: List[str], locations: List[str], max_results: int = 10) -> List[Dict]:
        logger.info(f"Starting job search with SerperJobSearchTool")
        
        api_key = os.getenv('SERPER_API_KEY')
        if not api_key:
            logger.error("SERPER_API_KEY not found in environment variables")
            raise ValueError("SERPER_API_KEY not found in environment variables.")
        
        logger.info("SERPER_API_KEY found, establishing connection...")
        conn = http.client.HTTPSConnection("google.serper.dev")
        job_results = []
        
        # Initialize deduplication and relevance scoring
        deduplicator = JobDeduplicator()
        relevance_scorer = JobRelevanceScorer(keywords)
        
        total_searches = len(keywords) * len(locations)
        search_count = 0
        
        for keyword in keywords:
            for location in locations:
                search_count += 1
                query = f"{keyword} jobs in {location}"
                logger.info(f"Search {search_count}/{total_searches}: '{query}'")
                
                payload = json.dumps({
                    "q": query,
                    "num": max_results,
                    "autocorrect": True
                })
                headers = {
                    'X-API-KEY': api_key,
                    'Content-Type': 'application/json'
                }
                
                try:
                    conn.request("POST", "/search", payload, headers)
                    res = conn.getresponse()
                    data = res.read()
                    response_json = json.loads(data.decode("utf-8"))
                    
                    organic_results = response_json.get("organic", [])
                    logger.info(f"Received {len(organic_results)} results for query: '{query}'")
                    
                    for result in organic_results:
                        # Enhanced job data extraction
                        job = {
                            "title": result.get("title", "No title available"),
                            "url": result.get("link", "#"),
                            "snippet": result.get("snippet", "No description available"),
                            "source": result.get("source", "Google Search"),
                            "location": location,
                            "keyword": keyword,
                            "date_found": datetime.now().isoformat(),
                            # Try to extract additional info from snippet
                            "company": self._extract_company_name(result.get("title", "")),
                            "employment_type": self._extract_employment_type(result.get("snippet", "")),
                            "salary": self._extract_salary_info(result.get("snippet", ""))
                        }
                        
                        # *** NEW: Check for duplicates ***
                        if deduplicator.is_duplicate(job):
                            logger.info(f"Skipping duplicate job: {job.get('title', 'Unknown')}")
                            continue
                        
                        # *** NEW: Calculate relevance score ***
                        relevance_score = relevance_scorer.calculate_relevance_score(job)
                        job['relevance_score'] = relevance_score
                        
                        logger.info(f"Job '{job.get('title', 'Unknown')}' - Relevance Score: {relevance_score}")
                        
                        job_results.append(job)
                        
                    if len(job_results) >= max_results:
                        logger.info(f"Reached maximum results limit ({max_results}), stopping search")
                        break
                        
                except Exception as e:
                    logger.error(f"Error during search for '{query}': {e}")
                    continue
                    
            if len(job_results) >= max_results:
                break
        
        # *** NEW: Sort by relevance score (highest first) ***
        job_results.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        
        final_results = job_results[:max_results]
        logger.info(f"Job search completed. Returning {len(final_results)} unique, scored results")
        
        # Log relevance score distribution
        if final_results:
            scores = [job.get('relevance_score', 0) for job in final_results]
            logger.info(f"Relevance scores - Min: {min(scores)}, Max: {max(scores)}, Avg: {sum(scores)/len(scores):.2f}")
        
        return final_results

    def _extract_company_name(self, title: str) -> str:
        """Extract company name from job title if possible"""
        # Simple extraction - look for patterns like "at Company Name"
        if " at " in title.lower():
            parts = title.lower().split(" at ")
            if len(parts) > 1:
                return parts[-1].strip().title()
        return ""

    def _extract_employment_type(self, snippet: str) -> str:
        """Extract employment type from job snippet"""
        snippet_lower = snippet.lower()
        if "remote" in snippet_lower:
            return "Remote"
        elif "full-time" in snippet_lower or "full time" in snippet_lower:
            return "Full-time"
        elif "part-time" in snippet_lower or "part time" in snippet_lower:
            return "Part-time"
        elif "contract" in snippet_lower:
            return "Contract"
        elif "freelance" in snippet_lower:
            return "Freelance"
        return ""

    def _extract_salary_info(self, snippet: str) -> str:
        """Extract salary information from job snippet"""
        import re
        # Look for salary patterns like $50,000, $50K, $50-60K, etc.
        salary_patterns = [
            r'\$[\d,]+k?(?:\s*-\s*\$?[\d,]+k?)?',
            r'[\d,]+k?\s*-\s*[\d,]+k?\s*(?:per year|annually|/year)',
        ]
        
        for pattern in salary_patterns:
            match = re.search(pattern, snippet, re.IGNORECASE)
            if match:
                return match.group(0)
        return ""