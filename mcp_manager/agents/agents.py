from crewai import Agent
from ..tools.directory_scanner import get_repo_files
from ..tools.issue_retriever import get_issue

## Repository Structure Analyzer
repo_structure_auditor = Agent(
    role = "Repository Structure Auditor",
    goal = "Analyze the folder and file structure of a GitHub repository and produce a Markdown-based file tree with clickable links.",
    backstory = (
        "You are skilled at visualizing repository structures. You help developers by generating clean, readable "
        "Markdown summaries of files and folders, especially for documentation purposes."
        ),
        tools = [get_repo_files],
        verbose = True
    )

## GitHub Issue Analyst
issue_analyst = Agent(
    role = "GitHub Issue Analyst",
    goal = "Fetch and summarize open GitHub issues, and suggest which issue should be prioritized.",
    backstory = (
        "You are an experienced open-source contributor who can identify, retrieve, and analyze GitHub issues. "
        "You know how to summarize them effectively and highlight the ones that need urgent attention."
    ),
    tools = [get_issue],
    verbose = True
)