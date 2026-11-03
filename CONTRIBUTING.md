# 🤝 Contributing to Dream Destiny

Thank you for your interest in contributing to **Dream Destiny**! We are thrilled to welcome developers, designers, writers, and travel enthusiasts to our open-source community.

Whether you are fixing a typo, resolving a bug, optimizing microservice performance, or adding a new travel capability, your contributions help make travel planning accessible and stress-free for thousands of travelers.

---

## 📑 Table of Contents

- [Code of Conduct](#-code-of-conduct)
- [How Can I Contribute?](#-how-can-i-contribute)
  - [Reporting Bugs](#reporting-bugs)
  - [Suggesting Features & Enhancements](#suggesting-features--enhancements)
  - [Contributing Code or Documentation](#contributing-code-or-documentation)
- [Development Setup](#-development-setup)
  - [Prerequisites](#prerequisites)
  - [Forking and Cloning](#forking-and-cloning)
  - [Configuring Environment Variables](#configuring-environment-variables)
  - [Running Microservices Locally](#running-microservices-locally)
  - [Running the Showcase Frontend](#running-the-showcase-frontend)
- [Development Guidelines](#-development-guidelines)
  - [Branch Naming Convention](#branch-naming-convention)
  - [Commit Message Guidelines](#commit-message-guidelines)
  - [Code Quality & Style](#code-quality--style)
  - [Testing Standards](#testing-standards)
- [Pull Request (PR) Process](#-pull-request-pr-process)
  - [PR Checklist](#pr-checklist)
  - [Review & Merge Workflow](#review--merge-workflow)
- [Security Disclosures](#-security-disclosures)
- [License & Attribution](#-license--attribution)

---

## 📜 Code of Conduct

We are committed to providing a welcoming, inclusive, and harassment-free environment for everyone.

- **Be respectful and empathetic:** Disagreements are natural in software development, but always critique ideas, not people.
- **Collaborate constructively:** Provide actionable feedback on pull requests and issues.
- **Respect privacy and security:** Never post private credentials, tokens, or personal identifiable information (PII) in public issues or pull requests.

---

## 💡 How Can I Contribute?

### Reporting Bugs

Before creating a new bug report, please check [existing GitHub Issues](https://github.com/jashwanth-cse/DreamDestiny/issues) to ensure the issue hasn't already been reported.

When opening a bug report, include:
1. **Clear, descriptive title.**
2. **Steps to reproduce the behavior.**
3. **Expected vs. actual behavior.**
4. **Relevant log snippets** (remember to scrub any API keys or secrets!).
5. **Environment details** (OS, Docker version, Python version, Node.js version).

### Suggesting Features & Enhancements

We welcome creative ideas for new transport connectors, AI planning strategies, UI themes, and optimizations!
- Open a **Feature Request** on GitHub Issues.
- Clearly describe the problem your feature solves and who benefits.
- Provide mockups, API references, or architecture sketches where applicable.

### Contributing Code or Documentation

Good first contributions include:
- Improving setup and deployment documentation.
- Adding unit or integration tests for edge cases.
- Enhancing error handling or retry logic in transit connectors.
- Improving PDF itinerary rendering or WhatsApp message templates.

---

## 💻 Development Setup

### Prerequisites

Ensure you have the following installed on your development machine:
- **Git** (2.30+)
- **Docker** & **Docker Compose** (v2+)
- **Python 3.11+**
- **Node.js 22+**
- **pnpm 10+** (`npm install -g pnpm`)

### Forking and Cloning

1. Fork the repository on GitHub:
   Click the **Fork** button on [https://github.com/jashwanth-cse/DreamDestiny](https://github.com/jashwanth-cse/DreamDestiny).

2. Clone your fork locally:
   ```bash
   git clone https://github.com/<your-username>/DreamDestiny.git
   cd DreamDestiny
   ```

3. Add the upstream remote to stay synchronized:
   ```bash
   git remote add upstream https://github.com/jashwanth-cse/DreamDestiny.git
   git fetch upstream
   ```

### Configuring Environment Variables

Create your local `.env` configuration file from the template:
```bash
cp .env.example .env
```

Review `.env` and supply credentials for external providers you intend to test:
- `WHATSAPP_*`: Meta WhatsApp Cloud API credentials (mocked in test mode if omitted).
- `BEDROCK_API_KEY`: AWS Amazon Bedrock API key for the AI Planner.
- `GOOGLE_MAPS_API_KEY`: Google Places / Maps Platform key for tourism discovery.
- `SERPAPI_API_KEY`: Optional key for live Google Flights & Hotels search.

> **CRITICAL:** Never commit your `.env` file or any private keys (`.pem`, `.key`, `serviceKey*.json`) to version control. They are strictly ignored by `.gitignore`.

### Running Microservices Locally

#### Option A: Run the Entire Stack with Docker Compose (Recommended)

To build and start all microservices, Redis cache, and monitoring in the background:
```bash
docker compose up --build -d
```

Verify service status and health checks:
```bash
docker compose ps
```

View live aggregated logs across all microservices:
```bash
docker compose logs -f
```

To stop all services:
```bash
docker compose down
```

#### Option B: Run a Specific Microservice for Local Debugging

You can also run individual Python microservices natively using a virtual environment:

```bash
# Example: Running the WhatsApp Bot Service
cd whatsapp-bot-service
python -m venv .venv

# On Linux/macOS:
source .venv/bin/activate
# On Windows PowerShell:
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8007 --reload
```

### Running the Showcase Frontend

The showcase landing page is built with **Next.js 16**, **TypeScript**, and **Tailwind CSS**:

```bash
cd dream-destiny-showcase
pnpm install
pnpm dev
```

Visit [http://localhost:3000](http://localhost:3000) in your browser.

To verify a production static export:
```bash
pnpm build
pnpm serve
```

---

## 🛠️ Development Guidelines

### Branch Naming Convention

Create feature branches originating from `main`:
```bash
git checkout -b <type>/<short-description>
```

Recommended prefix conventions:
- `feat/` — New feature or major capability (e.g., `feat/flight-layover-filter`)
- `fix/` — Bug fix (e.g., `fix/pdf-page-overflow`)
- `docs/` — Documentation updates (e.g., `docs/deployment-guide`)
- `refactor/` — Code refactoring without behavior change (e.g., `refactor/redis-session-store`)
- `test/` — Adding or updating test cases (e.g., `test/nlp-multislot-parsing`)
- `chore/` — Build system, dependencies, or CI updates (e.g., `chore/bump-pydantic`)

### Commit Message Guidelines

We follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```text
<type>(<scope>): <short imperative summary>

[optional body explaining motivation and context]

[optional footer with issue reference, e.g., Closes #42]
```

**Examples:**
- `feat(planner): support multi-city roadtrip waypoint sequencing`
- `fix(pdf): strictly map attraction photos 1-to-1 without stock fallbacks`
- `docs(readme): add step-by-step AWS free tier provisioning instructions`
- `test(whatsapp-bot): add unit tests for cancellation and reset intents`

### Code Quality & Style

- **Python:**
  - Follow [PEP 8](https://peps.python.org/pep-0008/) style standards.
  - Use explicit type annotations for function signatures.
  - Use Pydantic models for data validation and schema definitions.
  - Run `ruff` or `flake8` to detect linting errors.
- **TypeScript / Frontend:**
  - Strict TypeScript mode (`noImplicitAny`).
  - Follow the TripForge color palette tokens defined in Tailwind (`brand-navy`, `botanic-green`, `soft-sage`, `stone-canvas`, `deep-ink`).
  - Ensure all pages are responsive and pass accessibility standards (WCAG AA).
- **Architecture Integrity:**
  - Preserve loose coupling between microservices.
  - Do not create circular dependencies across services.
  - Always implement graceful fallbacks when external APIs time out.

### Testing Standards

Always run the test suite before submitting changes:

```bash
# Run tests for whatsapp-bot-service
cd whatsapp-bot-service
pytest tests/ -v

# Run tests from project root with PYTHONPATH configured:
# On Windows PowerShell:
$env:PYTHONPATH="whatsapp-bot-service"; python -m pytest whatsapp-bot-service/tests/ -v

# On Linux/macOS:
PYTHONPATH="whatsapp-bot-service" pytest whatsapp-bot-service/tests/ -v
```

If you add a new endpoint or feature, **include corresponding unit tests** validating both the happy path and error/fallback paths.

---

## 🚀 Pull Request (PR) Process

1. **Keep Pull Requests Focused:** Aim for single-responsibility PRs. Small, targeted PRs are reviewed and merged much faster.
2. **Sync with Upstream Main:** Before creating your PR, rebase or merge from upstream to avoid merge conflicts:
   ```bash
   git checkout main
   git pull upstream main
   git checkout <your-branch>
   git rebase main
   ```
3. **Push to Your Fork:**
   ```bash
   git push origin <your-branch>
   ```
4. **Open a Pull Request:**
   - Go to your repository on GitHub and click **Compare & pull request**.
   - Fill in the PR description template clearly explaining:
     - What problem this PR solves.
     - How the changes were tested.
     - Screenshots or sample outputs if visual changes were made.
     - Links to relevant issues (e.g., `Closes #12`).

### PR Checklist

Before requesting a review, confirm:
- [ ] Code follows project style guidelines.
- [ ] All existing automated tests pass (`pytest`).
- [ ] New tests have been added covering the changed code.
- [ ] Documentation has been updated (README, API docs, comments).
- [ ] No private keys, `.env` files, or sensitive tokens are included in the diff.
- [ ] Commits follow Conventional Commits formatting.

### Review & Merge Workflow

1. Maintainers will review your PR, run CI checks, and leave constructive feedback.
2. If changes are requested, push additional commits to the same branch; GitHub will update the PR automatically.
3. Once approved, a maintainer will merge your PR (typically via squash-and-merge).
4. 🎉 Celebrate your contribution to Dream Destiny!

---

## 🔒 Security Disclosures

If you discover a potential security vulnerability within Dream Destiny:
- **Please DO NOT report security vulnerabilities through public GitHub issues.**
- Instead, send a private advisory to the project maintainers via GitHub Security Advisories or contact `jashwanth-cse` directly.
- We will investigate and address the vulnerability promptly.

---

## ⚖️ License & Attribution

By contributing to Dream Destiny, you agree that your contributions will be licensed under the [MIT License](LICENSE).

Thank you for helping build the future of travel intelligence! 🌟
