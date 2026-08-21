# 🚀 Startup Builder — AI Skill Library

> **Turn a vague idea into a fully-built startup using AI-powered roles.**

This is a structured **skill library** for AI coding agents (like Dev/Dev). It contains **250+ expert role playbooks** covering every function of a startup — from customer discovery to deployment to growth.

## 🧠 What It Is

Think of this as **250 expert consultants in a folder**. Each `role/` folder contains `skills/` — YAML files with structured, actionable instructions for that role.

When you tell the AI your startup idea, it:
1. Matches your idea to a **startup archetype** (SaaS, AI, FinTech, etc.)
2. Loads the **right roles and skills** for each phase
3. Executes the full startup lifecycle — from ideation → planning → build → ship → growth → operations

## 📁 Structure

```
skills/
├── manifests/
│   └── startup-types.yaml      # Master registry: archetypes → roles → phases
├── roles/
│   ├── founder-ceo/
│   │   └── skills/
│   │       ├── investor-pitch-deck.yaml
│   │       ├── vision-setting.yaml
│   │       └── ...
│   ├── backend-engineer/
│   │   └── skills/
│   │       ├── api-design-rest.yaml
│   │       ├── database-design.yaml
│   │       └── ...
│   ├── ai-engineer/
│   ├── product-manager/
│   ├── ux-researcher/
│   ├── devops-engineer/
│   └── ... (250+ roles)
├── utilities/
│   ├── cognitive/               # First-principles, decision journal, etc.
│   ├── research/                # Competitive teardown, Reddit mining, etc.
│   ├── design/                  # Figma pipeline, 3D mockups, etc.
│   └── coding/                  # Code review, regex, conciseness, etc.
├── templates/
│   ├── role-readme-template.md
│   └── skill-template.yaml
├── STARTUP-BUILDER.md           # ← THE KEY FILE: Instructions for the AI
└── README.md                    # This file
```

## 🎯 How to Use It

### Step 1: Set Up
```bash
# Create your startup project folder
mkdir my-startup
cd my-startup

# Copy the entire skills/ folder into it
cp -r /path/to/this/skills .

# (Optional) Copy STARTUP-BUILDER.md to root
cp /path/to/STARTUP-BUILDER.md .
```

### Step 2: Start Dev
```bash
dev
# Or open Dev in this directory
```

### Step 3: Tell the AI Your Idea
Just say something like:
> "I have a startup idea. Read STARTUP-BUILDER.md and use the skills library to build it out."
>
> "My idea is: [describe your idea in one sentence]"

### Step 4: Let It Run
The AI will:
1. Analyze your idea and match it to an archetype
2. Load the relevant skills phase-by-phase
3. Do market research, customer discovery, planning
4. Build the MVP, deploy it, and set up growth channels
5. Hand off documentation for operations

## 🏗️ Startup Phases

| Phase | Focus | Key Roles |
|-------|-------|-----------|
| **0: Ideation** | Validate the idea, find customers, research market | founder-ceo, market-researcher, customer-discovery-specialist, competitive-analyst |
| **1: Planning** | Design product, architecture, roadmap | product-manager, ux-designer, technical-architect, data-architect |
| **2: Build** | Write code, set up infra, database | frontend-engineer, backend-engineer, devops-engineer, database-engineer, qa-engineer |
| **3: Ship** | Deploy, test, document, support | release-engineer, sre-engineer, technical-writer, support-engineer |
| **4: Growth** | Marketing, SEO, content, growth | seo-specialist, content-strategist, copywriter, social-media-manager, growth-hacker |
| **5: Operations** | Legal, compliance, HR, finance, fundraising | legal-counsel, compliance-officer, hr-manager, cfo, founder-ceo |

## 🔧 Supported Startup Archetypes

- **SaaS / Micro-SaaS** — Subscription software
- **AI / Agentic** — LLM/ML-powered products
- **E-Commerce / D2C** — Selling goods online
- **Marketplace** — Connecting buyers and sellers
- **FinTech** — Financial services
- **HealthTech** — Healthcare technology
- **EdTech** — Learning platforms
- **Web3 / Crypto** — Blockchain applications
- **Gaming** — Interactive entertainment
- **IoT / Hardware** — Physical devices
- **DevTools** — Developer tools
- **Media / Creator Economy** — Content platforms
- **AgriTech** — Agriculture technology
- **PropTech** — Real estate technology
- **CleanTech / Climate** — Sustainability

## 🤝 Contributing

See `templates/skill-template.yaml` for the skill schema and `templates/role-readme-template.md` for role structure.

## 📄 License

MIT — Use it, fork it, build startups with it.
