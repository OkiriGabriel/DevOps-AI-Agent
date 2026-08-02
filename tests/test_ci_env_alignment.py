"""
Guards that CI's dummy environment variables use the names the code reads.

The CI workflow writes throwaway `.env` files inline. When a key there drifts
from the name a collector actually reads, the smoke jobs keep passing while
validating nothing. These tests pin both directions: every variable CI sets
must be a name the application knows, and every org credential key must be
documented in `.env.example`.
"""

import re
from pathlib import Path

from services.org_config import ORG_CREDENTIAL_KEYS

REPO_ROOT = Path(__file__).resolve().parent.parent
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
ENV_EXAMPLE = REPO_ROOT / ".env.example"

# Test-harness flag CI sets on purpose; not an application credential.
CI_ONLY_KEYS = {"TESTING"}

HEREDOC_START_RE = re.compile(r"cat\s*>\s*\.env\s*<<\s*'?EOF'?\s*$")
HEREDOC_END_RE = re.compile(r"^\s*EOF\s*$")
ASSIGNMENT_RE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)=")
# os.environ['KEY'] = ... assignments only (the (?!=) lookahead excludes `==`
# comparisons); a plain read like os.environ['GITHUB_WORKSPACE'] must not match.
OS_ENVIRON_RE = re.compile(r"""os\.environ\[['"]([A-Z][A-Z0-9_]*)['"]\]\s*=(?!=)""")


def _heredoc_env_keys(workflow_text):
    """Keys assigned inside every `cat > .env << EOF ... EOF` block."""
    keys = set()
    blocks = 0
    in_block = False
    for line in workflow_text.splitlines():
        if not in_block:
            if HEREDOC_START_RE.search(line):
                in_block = True
                blocks += 1
            continue
        if HEREDOC_END_RE.match(line):
            in_block = False
            continue
        match = ASSIGNMENT_RE.match(line)
        if match:
            keys.add(match.group(1))
    return keys, blocks


def _env_example_declared_keys(env_example_text):
    """Keys declared as `KEY=` on an uncommented line of .env.example."""
    keys = set()
    for line in env_example_text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        match = ASSIGNMENT_RE.match(line)
        if match:
            keys.add(match.group(1))
    return keys


def test_ci_dummy_env_uses_known_variable_names():
    workflow_text = CI_WORKFLOW.read_text(encoding="utf-8")
    heredoc_keys, block_count = _heredoc_env_keys(workflow_text)
    environ_keys = set(OS_ENVIRON_RE.findall(workflow_text))

    # Guard the parser itself: an empty scrape would pass vacuously.
    assert block_count, "no `cat > .env << EOF` block found in ci.yml"
    assert heredoc_keys, "no KEY= lines found in ci.yml's dummy .env blocks"
    assert environ_keys, "no os.environ[...] assignments found in ci.yml"

    known_keys = (
        set(ORG_CREDENTIAL_KEYS)
        | _env_example_declared_keys(ENV_EXAMPLE.read_text(encoding="utf-8"))
        | CI_ONLY_KEYS
    )
    unknown = sorted((heredoc_keys | environ_keys) - known_keys)
    assert unknown == [], (
        "ci.yml assigns environment variables that are not an ORG_CREDENTIAL_KEYS "
        "entry, are not declared in .env.example, and are not a CI-only key "
        f"({sorted(CI_ONLY_KEYS)}): " + str(unknown)
    )


def test_org_credential_keys_are_documented():
    env_example_text = ENV_EXAMPLE.read_text(encoding="utf-8")
    undocumented = sorted(
        key
        for key in ORG_CREDENTIAL_KEYS
        if not re.search(rf"\b{re.escape(key)}\b", env_example_text)
    )
    assert (
        undocumented == []
    ), ".env.example does not mention these ORG_CREDENTIAL_KEYS: " + str(undocumented)
