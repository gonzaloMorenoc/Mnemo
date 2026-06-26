import pytest
from pydantic import ValidationError

from src.multitenant_models import GitHubConfigRequest


def test_valid_repo_full_name():
    m = GitHubConfigRequest(org_id="o", installation_id="1", repo_full_name="owner/repo-1.x")
    assert m.repo_full_name == "owner/repo-1.x"


@pytest.mark.parametrize("bad", ["owner", "owner/repo/extra", "owner/../repo", "o r/repo", "owner/re po"])
def test_invalid_repo_full_name_rejected(bad):
    with pytest.raises(ValidationError):
        GitHubConfigRequest(org_id="o", installation_id="1", repo_full_name=bad)
