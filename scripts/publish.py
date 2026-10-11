"""Publish output/draft_board.html to GitHub Pages on the gh-pages branch, with the pages of the other playoff windows."""
import subprocess

from common import OUT, ROOT

BRANCH = "gh-pages"
URL = "https://mccomark21.github.io/fantasy-basketball-rankings/"


def git(repo, *args, data=b""):
    return subprocess.run(["git", *args], cwd=repo, input=data, check=True, capture_output=True).stdout.decode().strip()


def write_blob(repo, data):
    return git(repo, "hash-object", "-w", "--stdin", "--no-filters", data=data)


def publish(repo, board, others=()):
    """Push the board to gh-pages in origin as index.html. The working tree and the current branch do not change.

    others: more pages (the other playoff windows). Each one goes to gh-pages with its own file name.
    The branch holds one commit, so each run replaces the last one and the old boards do not stay in the repo.
    """
    if not board.exists():
        raise FileNotFoundError(f"{board} does not exist. Run scripts/draft_board.py first.")
    files = {".nojekyll": b"", "index.html": board.read_bytes(), **{o.name: o.read_bytes() for o in others}}
    # mktree needs the entries in name order
    tree = git(repo, "mktree", data="".join(f"100644 blob {write_blob(repo, data)}\t{name}\n"
                                            for name, data in sorted(files.items())).encode())
    commit = git(repo, "commit-tree", tree, "-m", "Publish the draft board")
    git(repo, "push", "--force", "origin", f"{commit}:refs/heads/{BRANCH}")


def main():
    publish(ROOT, OUT / "draft_board.html", sorted(OUT.glob("draft_board_*.html")))
    print(f"Published the draft board to {URL}. GitHub can take a few minutes to show the new board.")


if __name__ == "__main__":
    main()
