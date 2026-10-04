"""Remote-write CLIs (gh, glab, hub) are denied; reads stay ask (ADR-0018)."""

import base64

import pytest

from chatur.verdict import Decision
from conftest import check, hit_ids, shell_event


def _enc(command: str) -> str:
    return base64.b64encode(command.encode("utf-16-le")).decode()


DENIED = [
    # gh
    "gh pr create --title x --body y",
    "gh pr merge 12 --squash --delete-branch",
    "gh pr close 12",
    "gh pr review 12 --approve",
    "gh pr comment 12 --body hi",
    "gh -R owner/repo pr merge 12",
    "gh pr --repo owner/repo merge 12",
    "gh issue create --title bug",
    "gh issue comment 5 --body x",
    "gh issue delete 5 --yes",
    "gh release create v1.0.0 dist/*",
    "gh release upload v1.0.0 app.zip",
    "gh repo delete owner/repo --yes",
    "gh repo edit --visibility public",
    "gh repo sync",
    "gh repo deploy-key add key.pub",
    "gh secret set API_KEY --body xyz",
    "gh variable delete FOO",
    "gh workflow run deploy.yml",
    "gh run rerun 123",
    "gh run cancel 123",
    "gh label create bug",
    "gh gist create notes.txt",
    "gh cache delete --all",
    "gh api -X DELETE repos/o/r",
    "gh api --method PUT repos/o/r/pulls/1/merge",
    "gh api --method=PATCH repos/o/r",
    "gh api -XPOST repos/o/r/issues",
    "gh api repos/o/r/issues -f title=x",
    "gh api graphql -F query=@q.graphql",
    "gh api repos/o/r/contents/x --input body.json",
    # glab
    "glab mr create --fill",
    "glab mr merge 7",
    "glab mr approve 7",
    "glab issue note 3 -m hi",
    "glab release create v1",
    "glab repo delete group/proj",
    "glab variable set TOKEN x",
    "glab ci run",
    "glab api --method POST projects/1/issues",
    # hub
    "hub pull-request -m x",
    "hub merge https://github.com/o/r/pull/1",
    "hub release create v1",
    "hub push origin main",
    "hub api -X DELETE repos/o/r",
    # bypass attempts
    "GH.EXE pr merge 12",
    "/usr/local/bin/gh pr merge 12",
    "sudo gh pr merge 12",
    "GH_TOKEN=x gh pr merge 12",
    'sh -c "gh pr merge 12"',
    'cmd /c "gh release create v1"',
    "pwsh -c 'gh repo delete o/r --yes'",
    f"pwsh -EncodedCommand {_enc('gh pr merge 12')}",
    "git status && gh pr merge 12",
    "echo $(gh pr merge 12)",
    "g`h pr mer`ge 12",
    "python -c \"import os; os.system('gh pr merge 12')\"",
    'python -c \'import subprocess; subprocess.run(["gh","pr","merge","12"])\'',
]


@pytest.mark.parametrize("command", DENIED)
def test_remote_write_denied(command):
    verdict = check(shell_event(command))
    assert verdict.decision is Decision.DENY, f"{command!r} -> {verdict.decision}: {verdict.reason}"
    assert "git.remote-cli" in hit_ids(verdict) or "git.no-commit-push" in hit_ids(verdict)


ASK = [
    "gh pr view 12",
    "gh pr list --search merge",
    "gh pr diff 12",
    "gh pr checks 12",
    "gh issue list --label bug",
    "gh run view 123 --log",
    "gh api repos/o/r/pulls",
    "gh api --method GET repos/o/r",
    "gh release list",
    "gh repo view",
    "glab mr list",
    "glab ci status",
    'echo "gh pr merge 12"',
    "grep -r 'gh release create' docs/",
]


@pytest.mark.parametrize("command", ASK)
def test_reads_and_text_not_denied(command):
    verdict = check(shell_event(command))
    assert verdict.decision is Decision.ASK, f"{command!r} -> {verdict.decision}: {verdict.reason}"
    assert "git.remote-cli" not in hit_ids(verdict)
