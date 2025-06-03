# tools/job_deduplication.py
from typing import Dict, Set
import hashlib
import re
from difflib import SequenceMatcher
from utils.logger import logger

class JobDeduplicator:
    """Handles job deduplication using multiple strategies"""

    def __init__(self):  # Fixed: was missing underscore
        self.seen_jobs: Set[str] = set()
        self.similarity_threshold = 0.8  # 80% similarity threshold

    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison"""
        if not text:
            return ""
        # Remove extra whitespace, convert to lowercase, remove special chars
        return re.sub(r'[^\w\s]', '', text.lower().strip())

    def _create_job_hash(self, job: Dict) -> str:
        """Create a hash from key job attributes"""
        # Combine normalized title, company, and location for hashing
        title = self._normalize_text(job.get('title', ''))
        company = self._normalize_text(job.get('company', ''))
        location = self._normalize_text(job.get('location', ''))

        # Create composite string for hashing
        composite = f"{title}|{company}|{location}"
        return hashlib.md5(composite.encode()).hexdigest()

    def _calculate_similarity(self, job1: Dict, job2_hash: str, job2_title: str) -> float:
        """Calculate similarity between jobs"""
        job1_title = self._normalize_text(job1.get('title', ''))
        job2_title_norm = self._normalize_text(job2_title)

        # Use sequence matcher for title similarity
        title_similarity = SequenceMatcher(None, job1_title, job2_title_norm).ratio()
        return title_similarity

    def is_duplicate(self, job: Dict) -> bool:
        """Check if job is a duplicate"""
        job_hash = self._create_job_hash(job)

        # Exact match check
        if job_hash in self.seen_jobs:
            logger.info(f"Exact duplicate found: {job.get('title', 'Unknown')}")
            return True

        # Similarity check (for fuzzy duplicates)
        job_title = job.get('title', '')
        for existing_hash in self.seen_jobs:
            # For similarity check, we'd need to store more info
            # For now, we'll rely on exact hash matching
            pass

        # Add to seen jobs if not duplicate
        self.seen_jobs.add(job_hash)
        return False