# tools/job_relevance_scorer.py
from typing import List, Dict


class JobRelevanceScorer:
    """Scores job relevance based on keyword matching"""
    
    def __init__(self, keywords: List[str]):
        self.keywords = [kw.lower().strip() for kw in keywords]
        self.keyword_weights = {
            'title': 3.0,      # Title matches are most important
            'company': 1.5,    # Company matches are moderately important
            'snippet': 1.0,    # Description matches are baseline
            'location': 0.5    # Location matches are least weighted
        }
    
    def _calculate_field_score(self, field_text: str, field_weight: float) -> float:
        """Calculate relevance score for a specific field"""
        if not field_text:
            return 0.0
        
        field_text_lower = field_text.lower()
        score = 0.0
        
        for keyword in self.keywords:
            # Exact keyword match
            if keyword in field_text_lower:
                score += field_weight * 2.0  # Bonus for exact match
            
            # Partial keyword match (for multi-word keywords)
            keyword_words = keyword.split()
            if len(keyword_words) > 1:
                matches = sum(1 for word in keyword_words if word in field_text_lower)
                partial_score = (matches / len(keyword_words)) * field_weight
                score += partial_score
        
        return score
    
    def calculate_relevance_score(self, job: Dict) -> float:
        """Calculate overall relevance score for a job"""
        total_score = 0.0
        
        # Score different fields
        fields_to_score = [
            ('title', self.keyword_weights['title']),
            ('company', self.keyword_weights['company']),
            ('snippet', self.keyword_weights['snippet']),
            ('location', self.keyword_weights['location'])
        ]
        
        for field_name, weight in fields_to_score:
            field_value = job.get(field_name, '')
            field_score = self._calculate_field_score(field_value, weight)
            total_score += field_score
        
        # Normalize score (optional - you can adjust this)
        max_possible_score = sum(weight * 2.0 * len(self.keywords) for _, weight in fields_to_score)
        normalized_score = (total_score / max_possible_score) * 100 if max_possible_score > 0 else 0
        
        return round(normalized_score, 2)