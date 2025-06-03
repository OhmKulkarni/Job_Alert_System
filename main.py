# main.py
import yaml
import json
from datetime import datetime
from tools.serper_job_search_tool import SerperJobSearchTool
from tools.email_sender_tool import EmailSenderTool
from tools.html_email_formatter import HTMLEmailFormatter
from tools.llm_sumarizer_tool import LLMSummarizerTool  # Added import
from utils.logger import logger

def main():
    logger.info("Starting Job Alert System")
    
    try:
        # 1. Load config
        logger.info("Loading configuration files...")
        with open('config/job_alert.yaml', 'r') as f:
            config = yaml.safe_load(f)
        logger.info("Configuration loaded successfully")

        # 1b. Load prompt templates
        with open('config/prompts.yaml', 'r') as f:
            prompts = yaml.safe_load(f)
        logger.info("Prompt templates loaded successfully")

        system_message = prompts['summarizer_system_message']
        prompt_intro = prompts['summarizer_prompt_intro']

        keywords = config.get('keywords', [])
        locations = config.get('locations', [])
        max_results = config.get('max_results', 10)
        recipient_name = config.get('recipient_name', 'Job Seeker')
        
        logger.info(f"Search parameters - Keywords: {keywords}, Locations: {locations}, Max results: {max_results}")

        # 2. Search for jobs
        logger.info("Initializing job search...")
        serper_tool = SerperJobSearchTool()
        job_results = serper_tool._run(keywords, locations, max_results)
        logger.info(f"Job search completed. Found {len(job_results)} job listings")

        # 3. Summarize with LLMSummarizerTool 
        logger.info("Using LLMSummarizerTool for job summarization...")
        llm_summarizer = LLMSummarizerTool()
        summary = llm_summarizer._run(job_results, system_message, prompt_intro)
        logger.info("LLM summarization completed")

        # 4. Format email with modern HTML template
        logger.info("Formatting email with HTML template...")
        html_formatter = HTMLEmailFormatter()
        
        # Try to parse LLM's JSON response, fallback to simple formatting
        try:
            parsed_summary = json.loads(summary)
            html_email = html_formatter.create_enhanced_email(
                recipient_name=recipient_name,
                job_data=parsed_summary,
                search_keywords=keywords,
                search_locations=locations
            )
        except (json.JSONDecodeError, KeyError):
            logger.warning("Could not parse LLM JSON response, using fallback formatting")
            html_email = html_formatter.create_simple_email(
                recipient_name=recipient_name,
                job_results=job_results,
                search_keywords=keywords,
                search_locations=locations
            )

        # 5. Send email
        logger.info("Preparing to send email digest...")
        email_tool = EmailSenderTool()
        
        # Enhanced subject line
        current_date = datetime.now().strftime("%B %d, %Y")
        subject = f"🚀 Your Job Alert Digest - {len(job_results)} New Opportunities | {current_date}"
        
        result = email_tool._run(subject, html_email)
        logger.info(f"Email sending result: {result}")
        print(result)
        
        logger.info("Job Alert System completed successfully")

    except FileNotFoundError as e:
        logger.error(f"Configuration file not found: {e}")
        raise
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML configuration: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in main process: {e}")
        raise

if __name__ == "__main__":
    main()