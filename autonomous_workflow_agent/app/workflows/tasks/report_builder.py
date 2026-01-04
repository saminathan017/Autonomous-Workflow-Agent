"""
AI-powered report builder task.
"""
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from autonomous_workflow_agent.app.ai.openai_client import get_openai_client
from autonomous_workflow_agent.app.workflows.models import EmailData, ReportData
from autonomous_workflow_agent.app.config import get_reports_dir
from autonomous_workflow_agent.app.utils.logging import get_logger

logger = get_logger(__name__)


class ReportBuilder:
    """Builds AI-powered reports from email data."""
    
    def __init__(self):
        """Initialize the report builder."""
        self.openai_client = get_openai_client()
    
    def _generate_summary(self, emails: List[EmailData]) -> str:
        """
        Generate an overall summary of emails.
        
        Args:
            emails: List of EmailData objects
            
        Returns:
            Summary text
        """
        if not emails:
            return "No emails to summarize."
        
        # Prepare email summaries
        email_summaries = []
        for email in emails[:10]:  # Limit to first 10 to avoid token limits
            email_summaries.append(
                f"From: {email.sender}\n"
                f"Subject: {email.subject}\n"
                f"Snippet: {email.snippet}\n"
            )
        
        combined_text = "\n---\n".join(email_summaries)
        
        prompt = (
            f"Summarize the following {len(emails)} emails in 2-3 paragraphs. "
            f"Focus on common themes, important senders, and key topics:\n\n{combined_text}"
        )
        
        summary = self.openai_client.summarize_text(prompt, max_length=150)
        return summary
    
    def _extract_insights(self, emails: List[EmailData]) -> List[str]:
        """
        Extract key insights from emails.
        
        Args:
            emails: List of EmailData objects
            
        Returns:
            List of insight strings
        """
        if not emails:
            return ["No emails to analyze."]
        
        # Prepare data for analysis
        subjects = [email.subject for email in emails[:20]]
        senders = [email.sender for email in emails[:20]]
        
        data_text = (
            f"Email subjects:\n" + "\n".join(f"- {s}" for s in subjects) + "\n\n"
            f"Senders:\n" + "\n".join(f"- {s}" for s in set(senders))
        )
        
        insights_text = self.openai_client.extract_insights(data_text)
        
        # Parse insights into list
        insights = []
        for line in insights_text.split('\n'):
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith('-') or line.startswith('•')):
                # Remove numbering/bullets
                clean_line = line.lstrip('0123456789.-•) ').strip()
                if clean_line:
                    insights.append(clean_line)
        
        return insights[:5]  # Return top 5 insights
    
    def _format_markdown_report(self, report_data: ReportData) -> str:
        """
        Format report data as Markdown.
        
        Args:
            report_data: ReportData object
            
        Returns:
            Markdown formatted report
        """
        md = f"# {report_data.title}\n\n"
        md += f"**Generated:** {report_data.generated_at.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        md += f"**Emails Processed:** {report_data.email_count}\n\n"
        md += "---\n\n"
        
        # Urgency Breakdown Section
        md += "## Urgency Breakdown\n\n"
        stats = report_data.urgency_stats
        if stats:
            md += f"- **Important:** {stats.get('Important', 0)}\n"
            md += f"- **Needed Review:** {stats.get('Needed Review', 0)}\n"
            md += f"- **Take Your Time:** {stats.get('Take Your Time', 0)}\n\n"
        
        if report_data.priority_emails:
            md += "### 🚨 Priority Action Items\n\n"
            for subject in report_data.priority_emails:
                md += f"- {subject}\n"
            md += "\n"
            
        md += "---\n\n"
        md += "## Summary\n\n"
        md += f"{report_data.summary}\n\n"
        md += "---\n\n"
        md += "## Key Insights\n\n"
        
        for i, insight in enumerate(report_data.insights, 1):
            md += f"{i}. {insight}\n"
        
        md += "\n---\n\n"
        md += "*This report was generated automatically by the Autonomous Workflow Agent.*\n"
        
        return md
    
    def build_report(self, emails: List[EmailData], title: str = "Email Analysis Report") -> ReportData:
        """
        Build a complete report from emails.
        
        Args:
            emails: List of EmailData objects
            title: Report title
            
        Returns:
            ReportData object
        """
        logger.info(f"Building report for {len(emails)} emails")
        
        # Reset OpenAI call counter for this report
        self.openai_client.reset_call_count()
        
        # Calculate urgency stats
        urgency_stats = {
            "Important": 0,
            "Needed Review": 0,
            "Take Your Time": 0
        }
        priority_emails = []
        
        for email in emails:
            if email.sentiment:
                score = email.sentiment.urgency_score
                if score >= 0.7:
                    urgency_stats["Important"] += 1
                    priority_emails.append(f"**{email.sender}**: {email.subject}")
                elif score >= 0.4:
                    urgency_stats["Needed Review"] += 1
                else:
                    urgency_stats["Take Your Time"] += 1
        
        # Generate summary
        summary = self._generate_summary(emails)
        
        # Extract insights
        insights = self._extract_insights(emails)
        
        # Create report data
        report_data = ReportData(
            title=title,
            summary=summary,
            insights=insights,
            urgency_stats=urgency_stats,
            priority_emails=priority_emails,
            email_count=len(emails),
            generated_at=datetime.now()
        )
        
        logger.info("Report generation complete")
        return report_data
    
    def save_report(self, report_data: ReportData, filename: Optional[str] = None) -> Path:
        """
        Save report to disk.
        
        Args:
            report_data: ReportData object
            filename: Optional filename (defaults to timestamped name)
            
        Returns:
            Path to saved report
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"report_{timestamp}.md"
        
        reports_dir = get_reports_dir()
        report_path = reports_dir / filename
        
        # Format as Markdown
        markdown = self._format_markdown_report(report_data)
        
        # Save to file
        report_path.write_text(markdown, encoding='utf-8')
        logger.info(f"Report saved to {report_path}")
        
        return report_path


def get_report_builder() -> ReportBuilder:
    """Get a report builder instance."""
    return ReportBuilder()
