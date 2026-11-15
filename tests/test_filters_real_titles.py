"""Regression cases taken from live job boards (Nov 2026)."""
import pytest

from jobalert.filters import RuleFilter
from jobalert.models import Decision, Posting

CASES = [
    # (title, location, expected)
    ("Master's Machine Learning Internship 2027 (USA)", "San Francisco, CA, US; Palo Alto, CA, US", "shortlist"),
    ("Master's Data Science Internship 2027 (USA)", "San Francisco, CA, US; Seattle, WA, US", "shortlist"),
    ("PhD Machine Learning Internship 2027 (USA)", "San Francisco, CA, US", "reject"),
    ("2027 Summer Intern, MS/PhD, Machine Learning Engineer", "San Francisco, CA, USA", "shortlist"),
    ("2027 Summer Intern, MS/PhD, Perception, Machine Learning", "Mountain View, CA, USA", "shortlist"),
    ("2027 Summer Intern, PhD, Data Science", "Mountain View, CA, USA", "reject"),
    ("2027 Summer Intern, MBA, Strategic Finance", "San Francisco, California, United States", "reject"),
    ("2027 Summer Intern, MBA, Salesforce Product Owner", "San Francisco, California, United States", "reject"),
    ("Machine Learning Engineer Intern", "Hybrid - San Francisco, CA", "maybe"),  # season not stated
    ("Software Engineer, AI Platform - Intern", "Mountain View, California (HQ)", "maybe"),
    ("2027 Software Engineer Intern", "Atlanta, Georgia, United States; Costa Mesa, California, United States", "maybe"),
    ("2027 Finance Data Analyst Intern", "Costa Mesa, California, United States", "maybe"),  # mixed signals
    ("Sales Analytics Intern 2027 (USA)", "San Francisco, CA, US; Remote, US", "maybe"),
    ("2027 Brand Marketing Intern", "Costa Mesa, California, United States", "reject"),
    ("2027 Mechanical Engineer Intern", "Irvine, California, United States", "reject"),
    ("High School Internship, Software Engineering (Summer 2027)", "Seattle, San Francisco", "reject"),
    ("Undergrad Software Engineering Intern (Grad Year: Winter 2027)", "San Francisco, CA", "reject"),
    ("Technical Support Engineering Intern - Summer 2027", "San Mateo, CA United States", "reject"),
    ("Machine Learning Intern 2027 (Toronto)", "Toronto, ON, CA", "reject"),
    ("Data Science Intern, Algorithms (Summer 2027 - SF/NYC)", "San Francisco, CA", "shortlist"),
    ("Data Analyst, Intern", "New York, Seattle, South San Francisco HQ", "maybe"),
    ("Product Management Intern (Summer 2027)", "Mountain View, California; San Francisco, California", "maybe"),
    ("Senior Manager, Internal Comms", "Irvine, CA", "reject"),
    ("AI Engineer, Internal Tools", "San Francisco, CA", "reject"),
    ("Software Engineer Intern, Mobile (Winter 2027)", "San Francisco, CA", "reject"),
    ("AI Workflows Intern [Summer 2027]", "Foster City, CA", "shortlist"),
]


@pytest.mark.parametrize("title,location,expected", CASES)
def test_real_titles(config, title, location, expected):
    rules = RuleFilter(config.settings.filters, config.profile)
    p = Posting(uid="x", source="greenhouse", company_key="co", company="Co", title=title,
                locations=[part.strip() for part in location.split(";")], url="https://x")
    result = rules.evaluate(p)
    assert result.decision == Decision(expected), result.reasons
