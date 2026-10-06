"""Publish output/draft_board.html to GitHub Pages on the gh-pages branch."""
import subprocess

from common import OUT, ROOT

BRANCH = "gh-pages"
URL = "https://mccomark21.github.io/fantasy-basketball-rankings/"


def git(repo, *args, data=b""):
    return subprocess.run(["git", *args], cwd=repo, input=data, check=True, capture_output=True).stdout.decode().strip()


def write_blob(repo, data):
    return git(repo, "hash-object", "-w", "--stdin", "--no-filters", data=data)


def publish(repo, board):
    """Push the board to gh-pages in origin as index.html. The working tree and the current branch do not change.

    The branch holds one commit, so each run replaces the last one and the old boards do not stay in the repo.
    """
    if not board.exists():
        raise FileNotFoundError(f"{board} does not exist. Run scripts/draft_board.py first.")
    tree = git(repo, "mktree", data=(f"100644 blob {write_blob(repo, b'')}\t.nojekyll\n"
                                     f"100644 blob {write_blob(repo, board.read_bytes())}\tindex.html\n").encode())
    commit = git(repo, "commit-tree", tree, "-m", "Publish the draft board")
    git(repo, "push", "--force", "origin", f"{commit}:refs/heads/{BRANCH}")


def main():
    publish(ROOT, OUT / "draft_board.html")
    print(f"Published the draft board to {URL}. GitHub can take a few minutes to show the new board.")


if __name__ == "__main__":
    main()
