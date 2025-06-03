# tools/llm_sumarizer_tool.py  
from crewai.tools import BaseTool
from typing import List, Dict
import requests
import json
from utils.logger import logger

class LLMSummarizerTool(BaseTool):
    name: str = "LLM Summarizer Tool"
    description: str = "Summarizes job listings into structured JSON format using Mistral API."

    def _run(self, job_listings: List[Dict], system_message: str = "", prompt_intro: str = "") -> str:
        logger.info(f"Starting job listings summarization for {len(job_listings)} jobs")

        # Default messages if not provided
        if not system_message:
            system_message = "You are a professional job market analyst. Your task is to analyze job listings and create structured summaries."
        
        if not prompt_intro:
            prompt_intro = "Please analyze the following job listings and provide a comprehensive summary."

        # Create enhanced prompt
        enhanced_prompt = f"""
        {system_message}
        
        IMPORTANT: Format your response as JSON with the following structure:
        {{
            "summary": "Brief overview of job market for these searches",
            "jobs": [
                {{
                    "title": "Job Title",
                    "company": "Company Name (if available)",
                    "location": "Location",
                    "description": "Brief 1-2 sentence description",
                    "url": "Application URL",
                    "salary": "Salary range (if mentioned)",
                    "employment_type": "Full-time/Part-time/Contract/Remote (if mentioned)",
                    "relevance_score": relevance_score_from_original_data
                }}
            ]
        }}
        
        {prompt_intro}
        
        {json.dumps(job_listings, indent=2)}
        """
        
        logger.info("Sending request to Mistral API...")
        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": "mistral:7b", "prompt": enhanced_prompt},
                stream=True
            )
            logger.info("Mistral API request initiated")

            summary = ""
            logger.info("Processing Mistral response stream...")
            for line in response.iter_lines():
                if line:
                    data = json.loads(line)
                    summary += data.get("response", "")
            
            logger.info("Summary generation completed")
            return summary
            
        except requests.RequestException as e:
            logger.error(f"Error communicating with Mistral API: {e}")
            raise
        except Exception as e:
            logger.error(f"Error in LLM summarization: {e}")
            raise