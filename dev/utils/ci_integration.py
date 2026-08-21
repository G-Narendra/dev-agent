"""
GitHub Actions and GitLab CI integration.

Generate workflow files for running Dev in CI/CD pipelines.
"""
from __future__ import annotations
import os
from dataclasses import dataclass


@dataclass
class GitHubAction:
    """A GitHub Actions workflow for Dev."""
    
    @staticmethod
    def generate_review_workflow() -> str:
        """Generate a GitHub Actions workflow for code review."""
        return '''name: Dev Code Review
on:
  pull_request:
    types: [opened, synchronize]

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - name: Install Dev
        run: pip install dev-agent
      
      - name: Review PR
        env:
          NVIDIA_NIM_API_KEY: ${{ secrets.NVIDIA_NIM_API_KEY }}
        run: |
          dev setup --key "$NVIDIA_NIM_API_KEY"
          git diff origin/${{ github.base_ref }} --name-only | \\
            dev headless "Review these changed files for security issues, bugs, and code quality. Output a structured report." --json > review.json
      
      - name: Post Review
        if: always()
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const review = fs.readFileSync('review.json', 'utf8');
            const data = JSON.parse(review);
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: `## Dev Code Review\\n\\n${data.response || 'Review completed'}`
            });
'''
    
    @staticmethod
    def generate_fix_workflow() -> str:
        """Generate a workflow that auto-fixes issues."""
        return '''name: Dev Auto-Fix
on:
  issue_comment:
    types: [created]
  issues:
    types: [labeled]

jobs:
  fix:
    if: contains(github.event.label.name, 'dev-fix') || startsWith(github.event.comment.body, '/dev-fix')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - name: Install Dev
        run: pip install dev-agent
      
      - name: Fix Issue
        env:
          NVIDIA_NIM_API_KEY: ${{ secrets.NVIDIA_NIM_API_KEY }}
        run: |
          dev setup --key "$NVIDIA_NIM_API_KEY"
          dev run "Fix the issue described in: ${{ github.event.issue.title }} - ${{ github.event.issue.body }}" --project .
      
      - name: Create PR
        uses: peter-evans/create-pull-request@v6
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
          commit-message: 'fix: auto-fix from issue #${{ github.event.issue.number }}'
          title: 'Fix: ${{ github.event.issue.title }}'
          body: 'Auto-generated fix for issue #${{ github.event.issue.number }}'
'''
    
    @staticmethod
    def generate_test_workflow() -> str:
        """Generate a workflow that runs tests and fixes failures."""
        return '''name: Dev Test & Fix
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test-and-fix:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - name: Install Dev
        run: pip install dev-agent
      
      - name: Run Tests
        id: tests
        run: |
          python -m pytest --tb=short 2>&1 | tee test-output.txt || true
          echo "exit_code=$?" >> $GITHUB_OUTPUT
      
      - name: Fix Failures
        if: steps.tests.outputs.exit_code != '0'
        env:
          NVIDIA_NIM_API_KEY: ${{ secrets.NVIDIA_NIM_API_KEY }}
        run: |
          dev setup --key "$NVIDIA_NIM_API_KEY"
          dev run "Fix the failing tests. Here is the test output:\\n$(cat test-output.txt)" --project .
      
      - name: Re-run Tests
        run: python -m pytest --tb=short
'''


@dataclass
class GitLabCI:
    """GitLab CI configuration for Dev."""
    
    @staticmethod
    def generate_config() -> str:
        """Generate .gitlab-ci.yml for Dev."""
        return '''stages:
  - review
  - test
  - fix

variables:
  PIP_CACHE_DIR: "$CI_PROJECT_DIR/.cache/pip"

dev-review:
  stage: review
  image: python:3.12
  rules:
    - if: $CI_MERGE_REQUEST_ID
  script:
    - pip install dev-agent
    - dev setup --key "$NVIDIA_NIM_API_KEY"
    - git diff origin/$CI_MERGE_REQUEST_TARGET_BRANCH_NAME --name-only | dev headless "Review these changed files for issues" --json > review.json
    - cat review.json
  artifacts:
    paths:
      - review.json

dev-test-fix:
  stage: fix
  image: python:3.12
  rules:
    - if: $CI_COMMIT_BRANCH == "main"
  script:
    - pip install dev-agent
    - dev setup --key "$NVIDIA_NIM_API_KEY"
    - python -m pytest || dev run "Fix failing tests" --project .
    - python -m pytest
  cache:
    paths:
      - .cache/pip/
'''
