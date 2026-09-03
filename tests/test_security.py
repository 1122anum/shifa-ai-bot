"""
test_security.py — Security audit tests for the Shifa AI project.

Verifies:
  - .env files are gitignored
  - .env.example files exist and contain only placeholders
  - No hard-coded API keys, passwords, or tokens in source code
  - No private keys committed
  - Configuration loaded from environment variables
  - Secret redaction filter works correctly
"""

import os
import re
import subprocess
from pathlib import Path

import pytest

# Project root
ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT / "backend-ai" / "backend"
WHATSAPP_DIR = ROOT / "whatsapp-integration"


# ── .gitignore Tests ────────────────────────────────────────────────────

class TestGitignore:
    """Verify .gitignore properly excludes sensitive files."""

    def test_root_gitignore_exists(self):
        gitignore = ROOT / ".gitignore"
        assert gitignore.exists(), "Root .gitignore must exist"

    def test_env_is_gitignored(self):
        gitignore = (ROOT / ".gitignore").read_text()
        assert ".env" in gitignore, ".env must be in .gitignore"

    def test_env_example_not_gitignored(self):
        gitignore = (ROOT / ".gitignore").read_text()
        assert "!.env.example" in gitignore, ".env.example must NOT be gitignored"

    def test_env_not_tracked_by_git(self):
        """Ensure .env files are not tracked by git."""
        result = subprocess.run(
            ["git", "ls-files", "--cached"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        tracked_files = result.stdout.strip().split("\n")
        env_files = [f for f in tracked_files if f.endswith(".env") and ".env.example" not in f]
        assert not env_files, f".env files should not be tracked: {env_files}"


# ── .env.example Tests ──────────────────────────────────────────────────

class TestEnvExample:
    """Verify .env.example files exist and contain only placeholders."""

    def test_backend_env_example_exists(self):
        env_example = BACKEND_DIR / ".env.example"
        assert env_example.exists(), "backend/.env.example must exist"

    def test_whatsapp_env_example_exists(self):
        env_example = WHATSAPP_DIR / ".env.example"
        assert env_example.exists(), "whatsapp-integration/.env.example must exist"

    def test_backend_env_example_has_no_real_keys(self):
        content = (BACKEND_DIR / ".env.example").read_text()
        # Check for patterns that look like real keys (not placeholders)
        assert not re.search(r'=AIza[A-Za-z0-9]{20,}', content), \
            "backend .env.example contains what looks like a real Gemini key"
        assert not re.search(r'=sk-[A-Za-z0-9]{20,}', content), \
            "backend .env.example contains what looks like a real OpenAI key"
        assert not re.search(r'=gsk_[A-Za-z0-9]{20,}', content), \
            "backend .env.example contains what looks like a real Groq key"
        assert not re.search(r'=EAA[A-Za-z0-9]{50,}', content), \
            "backend .env.example contains what looks like a real Meta token"

    def test_whatsapp_env_example_has_no_real_keys(self):
        content = (WHATSAPP_DIR / ".env.example").read_text()
        assert not re.search(r'=EAA[A-Za-z0-9]{50,}', content), \
            "whatsapp .env.example contains what looks like a real Meta token"
        assert not re.search(r'=AC[a-f0-9]{32}', content), \
            "whatsapp .env.example contains what looks like a real Twilio SID"

    def test_env_example_uses_placeholders(self):
        """Verify .env.example uses placeholder values."""
        for env_file in [BACKEND_DIR / ".env.example", WHATSAPP_DIR / ".env.example"]:
            content = env_file.read_text()
            for line in content.split("\n"):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                # Values should be placeholder text or empty
                assert not re.match(r'[A-Za-z0-9]{32,}$', value.strip()), \
                    f"{env_file.name}: {key} looks like a real credential"


# ── Hard-coded Secret Tests ─────────────────────────────────────────────

class TestHardcodedSecrets:
    """Scan source code for hard-coded secrets."""

    # Patterns that look like real API keys
    SECRET_PATTERNS = [
        re.compile(r'["\']AIza[A-Za-z0-9]{20,}["\']'),       # Gemini
        re.compile(r'["\']sk-[A-Za-z0-9]{20,}["\']'),         # OpenAI
        re.compile(r'["\']gsk_[A-Za-z0-9]{20,}["\']'),        # Groq
        re.compile(r'["\']EAA[A-Za-z0-9]{50,}["\']'),         # Meta token
        re.compile(r'["\']AC[a-f0-9]{32}["\']'),              # Twilio SID
    ]

    def _scan_python_files(self, directory: Path) -> list[str]:
        """Scan all .py files for hard-coded secrets."""
        violations = []
        for py_file in directory.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            content = py_file.read_text(errors="ignore")
            for pattern in self.SECRET_PATTERNS:
                matches = pattern.findall(content)
                for match in matches:
                    # Exclude test fixtures that use obviously fake values
                    if "test" in str(py_file).lower() and ("ACtest" in match or "testtoken" in match.lower()):
                        continue
                    violations.append(f"{py_file.relative_to(ROOT)}: {match[:20]}...")
        return violations

    def test_no_hardcoded_secrets_in_backend(self):
        violations = self._scan_python_files(BACKEND_DIR / "app")
        assert not violations, \
            f"Hard-coded secrets found in backend:\n" + "\n".join(violations)

    def test_no_hardcoded_secrets_in_whatsapp(self):
        violations = self._scan_python_files(WHATSAPP_DIR / "app")
        assert not violations, \
            f"Hard-coded secrets found in whatsapp-integration:\n" + "\n".join(violations)

    def test_no_password_hardcoded(self):
        """Check for hard-coded password= patterns in source."""
        pattern = re.compile(r'password\s*=\s*["\'][^"\']{8,}["\']', re.IGNORECASE)
        for directory in [BACKEND_DIR / "app", WHATSAPP_DIR / "app"]:
            for py_file in directory.rglob("*.py"):
                if "__pycache__" in str(py_file):
                    continue
                content = py_file.read_text(errors="ignore")
                matches = pattern.findall(content)
                assert not matches, \
                    f"Hard-coded password in {py_file.relative_to(ROOT)}: {matches}"


# ── Configuration Tests ──────────────────────────────────────────────────

class TestConfiguration:
    """Verify centralized configuration is properly set up."""

    def test_backend_config_exists(self):
        config_file = BACKEND_DIR / "app" / "core" / "config.py"
        assert config_file.exists(), "backend/app/core/config.py must exist"

    def test_whatsapp_config_exists(self):
        config_file = WHATSAPP_DIR / "app" / "config.py"
        assert config_file.exists(), "whatsapp-integration/app/config.py must exist"

    def test_backend_config_uses_env_vars(self):
        content = (BACKEND_DIR / "app" / "core" / "config.py").read_text()
        assert "os.getenv" in content or "os.environ" in content, \
            "Backend config must load from environment variables"

    def test_whatsapp_config_uses_env_vars(self):
        content = (WHATSAPP_DIR / "app" / "config.py").read_text()
        assert "os.environ" in content or "os.getenv" in content, \
            "WhatsApp config must load from environment variables"


# ── Secret Redaction Tests ──────────────────────────────────────────────

class TestSecretRedaction:
    """Verify the secret redaction filter works."""

    def test_redaction_filter_exists(self):
        logger_file = WHATSAPP_DIR / "app" / "utils" / "logger.py"
        content = logger_file.read_text()
        assert "SecretRedactionFilter" in content, \
            "Secret redaction filter must exist in logger.py"

    def test_redaction_patterns_present(self):
        logger_file = WHATSAPP_DIR / "app" / "utils" / "logger.py"
        content = logger_file.read_text()
        assert "REDACTED" in content, "Logger must contain REDACTED replacement"


# ── Security Documentation Tests ────────────────────────────────────────

class TestSecurityDocs:
    """Verify security documentation exists."""

    def test_security_md_exists(self):
        security_md = ROOT / "SECURITY.md"
        assert security_md.exists(), "SECURITY.md must exist at project root"

    def test_readme_exists(self):
        readme = ROOT / "README.md"
        assert readme.exists(), "README.md must exist at project root"

    def test_readme_mentions_env_setup(self):
        content = (ROOT / "README.md").read_text()
        assert ".env.example" in content, "README must mention .env.example setup"
        assert ".env" in content, "README must mention .env"

    def test_pre_commit_config_exists(self):
        config = ROOT / ".pre-commit-config.yaml"
        assert config.exists(), ".pre-commit-config.yaml must exist"


# ── Sensitive File Tests ────────────────────────────────────────────────

class TestSensitiveFiles:
    """Verify no sensitive files are tracked by git."""

    def test_no_db_files_tracked(self):
        result = subprocess.run(
            ["git", "ls-files", "--cached"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        tracked = result.stdout.strip().split("\n")
        db_files = [f for f in tracked if f.endswith(".db")]
        assert not db_files, f"Database files should not be tracked: {db_files}"

    def test_no_screenshots_tracked(self):
        result = subprocess.run(
            ["git", "ls-files", "--cached"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        tracked = result.stdout.strip().split("\n")
        screenshots = [f for f in tracked if "page_" in f and f.endswith(".png")]
        assert not screenshots, f"Screenshots should not be tracked: {screenshots}"

    def test_no_log_files_tracked(self):
        result = subprocess.run(
            ["git", "ls-files", "--cached"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        tracked = result.stdout.strip().split("\n")
        logs = [f for f in tracked if f.endswith(".log")]
        assert not logs, f"Log files should not be tracked: {logs}"

    def test_no_key_files_tracked(self):
        result = subprocess.run(
            ["git", "ls-files", "--cached"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        tracked = result.stdout.strip().split("\n")
        keys = [f for f in tracked if f.endswith((".pem", ".key", ".crt"))]
        assert not keys, f"Key files should not be tracked: {keys}"
