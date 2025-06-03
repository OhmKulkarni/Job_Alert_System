# tools/html_email_formatter.py
from typing import List, Dict
from datetime import datetime


class HTMLEmailFormatter:
    """Creates modern, responsive HTML email templates for job alerts."""

    def create_enhanced_email(self, recipient_name: str, job_data: dict, search_keywords: List[str], search_locations: List[str]) -> str:
        """Create enhanced HTML email from structured job data"""
        current_date = datetime.now().strftime("%B %d, %Y")
        
        jobs_html = ""
        for job in job_data.get('jobs', []):
            # *** NEW: Add relevance score badge ***
            relevance_score = job.get('relevance_score', 0)
            score_color = self._get_score_color(relevance_score)
            score_badge = f'<span style="background: {score_color}; color: white; padding: 4px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; margin-left: 8px;">Score: {relevance_score}%</span>'
            
            jobs_html += f"""
            <div style="background: white; border-radius: 12px; padding: 24px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); border-left: 4px solid #4F46E5;">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
                    <h3 style="margin: 0; color: #1F2937; font-size: 18px; font-weight: 600; line-height: 1.4;">
                        {job.get('title', 'Job Title Not Available')}
                        {score_badge}
                    </h3>
                    {f'<span style="background: #EEF2FF; color: #4F46E5; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 500;">{job.get("employment_type", "")}</span>' if job.get('employment_type') else ''}
                </div>
                
                {f'<p style="margin: 0 0 8px 0; color: #6B7280; font-size: 14px;"><strong>Company:</strong> {job.get("company", "Not specified")}</p>' if job.get('company') else ''}
                <p style="margin: 0 0 8px 0; color: #6B7280; font-size: 14px;"><strong>Location:</strong> {job.get('location', 'Not specified')}</p>
                {f'<p style="margin: 0 0 16px 0; color: #6B7280; font-size: 14px;"><strong>Salary:</strong> {job.get("salary", "")}</p>' if job.get('salary') else ''}
                
                <p style="margin: 0 0 16px 0; color: #374151; font-size: 14px; line-height: 1.6;">
                    {job.get('description', 'No description available')}
                </p>
                
                <a href="{job.get('url', '#')}" style="display: inline-block; background: #4F46E5; color: white; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: 500; font-size: 14px; transition: background-color 0.2s;">
                    Apply Now →
                </a>
            </div>
            """

        return self._get_email_template(
            recipient_name=recipient_name,
            current_date=current_date,
            job_count=len(job_data.get('jobs', [])),
            summary=job_data.get('summary', 'New job opportunities found for your search criteria.'),
            jobs_html=jobs_html,
            search_keywords=search_keywords,
            search_locations=search_locations
        )

    def create_simple_email(self, recipient_name: str, job_results: List[Dict], search_keywords: List[str], search_locations: List[str]) -> str:
        """Create simple HTML email from raw job results (fallback)"""
        current_date = datetime.now().strftime("%B %d, %Y")
        
        jobs_html = ""
        for job in job_results:
            employment_info = []
            if job.get('employment_type'):
                employment_info.append(job['employment_type'])
            if job.get('salary'):
                employment_info.append(job['salary'])
            
            employment_badge = f'<span style="background: #EEF2FF; color: #4F46E5; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 500;">{" | ".join(employment_info)}</span>' if employment_info else ''
            
            # *** NEW: Add relevance score badge ***
            relevance_score = job.get('relevance_score', 0)
            score_color = self._get_score_color(relevance_score)
            score_badge = f'<span style="background: {score_color}; color: white; padding: 4px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; margin-left: 8px;">Score: {relevance_score}%</span>'
            
            jobs_html += f"""
            <div style="background: white; border-radius: 12px; padding: 24px; margin-bottom: 20px; box-shadow: 0 2px8px rgba(0,0,0,0.1); border-left: 4px solid #4F46E5;">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
                    <h3 style="margin: 0; color: #1F2937; font-size: 18px; font-weight: 600; line-height: 1.4;">
                        {job.get('title', 'Job Title Not Available')}
                        {score_badge}
                    </h3>
                    {employment_badge}
                </div>
                
                {f'<p style="margin: 0 0 8px 0; color: #6B7280; font-size: 14px;"><strong>Company:</strong> {job.get("company", "Not specified")}</p>' if job.get('company') else ''}
                <p style="margin: 0 0 16px 0; color: #6B7280; font-size: 14px;"><strong>Location:</strong> {job.get('location', 'Not specified')}</p>
                
                <p style="margin: 0 0 16px 0; color: #374151; font-size: 14px; line-height: 1.6;">
                    {job.get('snippet', 'No description available')}
                </p>
                
                <a href="{job.get('url', '#')}" style="display: inline-block; background: #4F46E5; color: white; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: 500; font-size: 14px;">
                    Apply Now →
                </a>
            </div>
            """

        return self._get_email_template(
            recipient_name=recipient_name,
            current_date=current_date,
            job_count=len(job_results),
            summary="We found new job opportunities matching your search criteria.",
            jobs_html=jobs_html,
            search_keywords=search_keywords,
            search_locations=search_locations
        )

    def _get_score_color(self, score: float) -> str:
        """Get color based on relevance score"""
        if score >= 75:
            return "#059669"  # Green for high relevance
        elif score >= 50:
            return "#D97706"  # Orange for medium relevance
        elif score >= 25:
            return "#DC2626"  # Red for low relevance
        else:
            return "#6B7280"  # Gray for very low relevance

    def _get_email_template(self, recipient_name: str, current_date: str, job_count: int, summary: str, jobs_html: str, search_keywords: List[str], search_locations: List[str]) -> str:
        """Base HTML email template with modern design"""
        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Job Alert Digest</title>
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #F9FAFB; line-height: 1.6;">
            <div style="max-width: 600px; margin: 0 auto; background-color: #F9FAFB;">
                
                <!-- Header -->
                <div style="background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%); padding: 32px 24px; text-align: center;">
                    <h1 style="margin: 0; color: white; font-size: 28px; font-weight: 700; text-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        🚀 Your Job Alert Digest
                    </h1>
                    <p style="margin: 8px 0 0 0; color: rgba(255,255,255,0.9); font-size: 16px;">
                        {current_date}
                    </p>
                </div>

                <!-- Main Content -->
                <div style="padding: 32px 24px;">
                    
                    <!-- Greeting -->
                    <div style="background: white; border-radius: 12px; padding: 24px; margin-bottom: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                        <h2 style="margin: 0 0 12px 0; color: #1F2937; font-size: 20px;">
                            Hello {recipient_name}! 👋
                        </h2>
                        <p style="margin: 0; color: #6B7280; font-size: 16px;">
                            {summary}
                        </p>
                    </div>

                    <!-- Stats -->
                    <div style="display: flex; gap: 16px; margin-bottom: 32px;">
                        <div style="flex: 1; background: white; border-radius: 12px; padding: 20px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                            <div style="font-size: 24px; font-weight: 700; color: #4F46E5; margin-bottom: 4px;">
                                {job_count}
                            </div>
                            <div style="font-size: 14px; color: #6B7280;">
                                New Jobs
                            </div>
                        </div>
                        <div style="flex: 1; background: white; border-radius: 12px; padding: 20px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                            <div style="font-size: 24px; font-weight: 700; color: #059669; margin-bottom: 4px;">
                                {len(search_keywords)}
                            </div>
                            <div style="font-size: 14px; color: #6B7280;">
                                Keywords
                            </div>
                        </div>
                    </div>

                    <!-- Search Info -->
                    <div style="background: #EEF2FF; border-radius: 12px; padding: 20px; margin-bottom: 32px; border: 1px solid #E0E7FF;">
                        <h3 style="margin: 0 0 12px 0; color: #4338CA; font-size: 16px;">
                            🔍 Your Search Criteria
                        </h3>
                        <p style="margin: 0 0 8px 0; color: #6B7280; font-size: 14px;">
                            <strong>Keywords:</strong> {', '.join(search_keywords)}
                        </p>
                        <p style="margin: 0; color: #6B7280; font-size: 14px;">
                            <strong>Locations:</strong> {', '.join(search_locations)}
                        </p>
                    </div>

                    <!-- Job Listings -->
                    <h2 style="margin: 0 0 24px 0; color: #1F2937; font-size: 22px;">
                        💼 Latest Opportunities (Sorted by Relevance)
                    </h2>
                    
                    {jobs_html}

                </div>

                <!-- Footer -->
                <div style="background: #374151; padding: 24px; text-align: center; border-radius: 0 0 12px 12px;">
                    <p style="margin: 0 0 8px 0; color: #D1D5DB; font-size: 14px;">
                        Job Alert System • Powered by AI • Jobs ranked by relevance
                    </p>
                    <p style="margin: 0; color: #9CA3AF; font-size: 12px;">
                        Keep pursuing your career goals! 🌟
                    </p>
                </div>

            </div>
        </body>
        </html>
        """