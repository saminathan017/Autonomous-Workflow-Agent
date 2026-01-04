#!/usr/bin/env python3
"""
Security Verification Script
Checks for any sensitive data that might be accidentally committed to git.
"""
import subprocess
import sys
from pathlib import Path

# ANSI color codes
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_header(text):
    """Print a formatted header."""
    print(f"\n{BLUE}{'='*70}{RESET}")
    print(f"{BLUE}{text:^70}{RESET}")
    print(f"{BLUE}{'='*70}{RESET}\n")

def print_success(text):
    """Print success message."""
    print(f"{GREEN}✓ {text}{RESET}")

def print_error(text):
    """Print error message."""
    print(f"{RED}✗ {text}{RESET}")

def print_warning(text):
    """Print warning message."""
    print(f"{YELLOW}⚠ {text}{RESET}")

def check_git_repo():
    """Check if we're in a git repository."""
    try:
        subprocess.run(
            ['git', 'rev-parse', '--git-dir'],
            check=True,
            capture_output=True,
            text=True
        )
        return True
    except subprocess.CalledProcessError:
        return False

def check_sensitive_files():
    """Check if sensitive files exist and are properly ignored."""
    sensitive_files = [
        'autonomous_workflow_agent/.env',
        'autonomous_workflow_agent/credentials.json',
        'autonomous_workflow_agent/token.json',
        'autonomous_workflow_agent/data/state.db',
    ]
    
    print_header("Checking Sensitive Files")
    
    all_ignored = True
    for file_path in sensitive_files:
        full_path = Path(file_path)
        
        # Check if file exists
        if not full_path.exists():
            print_warning(f"{file_path} - Does not exist (OK)")
            continue
        
        # Check if it's ignored by git
        result = subprocess.run(
            ['git', 'check-ignore', '-q', file_path],
            capture_output=True
        )
        
        if result.returncode == 0:
            print_success(f"{file_path} - Properly ignored")
        else:
            print_error(f"{file_path} - NOT IGNORED! This is a security risk!")
            all_ignored = False
    
    return all_ignored

def check_venv_ignored():
    """Check if virtual environment is ignored."""
    print_header("Checking Virtual Environment")
    
    venv_path = 'autonomous_workflow_agent/venv'
    
    if not Path(venv_path).exists():
        print_warning(f"{venv_path} - Does not exist")
        return True
    
    result = subprocess.run(
        ['git', 'check-ignore', '-q', venv_path],
        capture_output=True
    )
    
    if result.returncode == 0:
        print_success(f"{venv_path} - Properly ignored")
        return True
    else:
        print_error(f"{venv_path} - NOT IGNORED! This will bloat your repository!")
        return False

def check_for_hardcoded_secrets():
    """Check for potential hardcoded secrets in tracked files."""
    print_header("Scanning for Hardcoded Secrets")
    
    # Patterns that might indicate secrets
    patterns = [
        r'sk-[a-zA-Z0-9]{20,}',  # OpenAI API keys
        r'AIza[a-zA-Z0-9_-]{35}',  # Google API keys
        r'ya29\.[a-zA-Z0-9_-]+',  # Google OAuth tokens
        r'AKIA[0-9A-Z]{16}',  # AWS access keys
        r'ghp_[a-zA-Z0-9]{36}',  # GitHub personal access tokens
    ]
    
    all_clean = True
    
    for pattern in patterns:
        result = subprocess.run(
            ['git', 'grep', '-i', '-E', pattern, '--', '*.py', '*.sh', '*.command'],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print_error(f"Found potential secret matching pattern: {pattern}")
            print(result.stdout)
            all_clean = False
    
    if all_clean:
        print_success("No hardcoded secrets found in tracked files")
    
    return all_clean

def check_staged_files():
    """Check what files are staged/tracked."""
    print_header("Files Ready to Commit")
    
    result = subprocess.run(
        ['git', 'status', '--short'],
        capture_output=True,
        text=True
    )
    
    if result.stdout.strip():
        print(result.stdout)
    else:
        print("No files staged or untracked")

def main():
    """Run all security checks."""
    print_header("🔒 Security Verification for GitHub 🔒")
    
    # Check if we're in a git repo
    if not check_git_repo():
        print_error("Not in a git repository! Initialize with 'git init'")
        return 1
    
    # Run all checks
    checks_passed = [
        check_sensitive_files(),
        check_venv_ignored(),
        check_for_hardcoded_secrets(),
    ]
    
    # Show staged files
    check_staged_files()
    
    # Final summary
    print_header("Summary")
    
    if all(checks_passed):
        print_success("All security checks passed! ✓")
        print_success("Your repository is safe to push to GitHub!")
        return 0
    else:
        print_error("Some security checks failed!")
        print_error("DO NOT push to GitHub until all issues are resolved!")
        return 1

if __name__ == '__main__':
    sys.exit(main())
