import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from publish import BRANCH, publish  # noqa: E402


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path):
    """A clone with one commit on main and a bare 'origin'."""
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    git(tmp_path, "init", "--bare", "-b", "main", str(origin))
    git(tmp_path, "clone", str(origin), str(work))
    git(work, "config", "user.name", "Test")
    git(work, "config", "user.email", "test@example.com")
    (work / "README.md").write_text("main\n")
    git(work, "add", "README.md")
    git(work, "commit", "-m", "init")
    git(work, "push", "origin", "main")
    return work


def remote_pages(repo):
    """Files on gh-pages in origin, as {name: text}."""
    git(repo, "fetch", "origin", BRANCH)
    names = git(repo, "ls-tree", "--name-only", "FETCH_HEAD").split()
    return {n: git(repo, "show", f"FETCH_HEAD:{n}") for n in names}


def board(repo, text):
    path = repo / "output" / "draft_board.html"
    path.parent.mkdir(exist_ok=True)
    path.write_text(text)
    return path


def test_board_is_index_on_remote_gh_pages(repo):
    publish(repo, board(repo, "<p>board</p>"))
    assert remote_pages(repo) == {".nojekyll": "", "index.html": "<p>board</p>"}


def test_second_publish_replaces_the_first(repo):
    publish(repo, board(repo, "<p>old</p>"))
    publish(repo, board(repo, "<p>new</p>"))
    assert remote_pages(repo)["index.html"] == "<p>new</p>"
    assert git(repo, "rev-list", "--count", "FETCH_HEAD").strip() == "1"


def test_main_branch_and_working_tree_do_not_change(repo):
    head = git(repo, "rev-parse", "HEAD")
    publish(repo, board(repo, "<p>board</p>"))
    assert git(repo, "rev-parse", "HEAD") == head
    assert git(repo, "branch", "--show-current").strip() == "main"
    assert git(repo, "status", "--porcelain") == "?? output/\n"  # only the board, which is untracked
    assert git(repo, "branch", "--list", BRANCH) == ""


def test_missing_board_stops_with_an_error(repo):
    with pytest.raises(FileNotFoundError, match="draft_board.py"):
        publish(repo, repo / "output" / "draft_board.html")
