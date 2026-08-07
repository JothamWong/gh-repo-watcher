from urllib.error import HTTPError
from typing import Any
from dataclasses import asdict
from pathlib import Path
from dataclasses import dataclass
import json
import os
from urllib.request import Request, urlopen
from urllib.parse import quote
from html import escape

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPOS_JSON_PATH = PROJECT_ROOT / "config" / "repositories.json"
STATE_JSON_PATH = PROJECT_ROOT / "state" / "last-seen.json"


# --- GitHub stuff ---
@dataclass(frozen=True, slots=True)
class StalkedGitHubRepo:
    friendly_name: str
    repository: str
    branch: str
    enabled: bool

    @classmethod
    def from_dict(cls, data: Any):
        return StalkedGitHubRepo(
            friendly_name=data["name"],
            repository=data["repository"],
            branch=data["branch"],
            enabled=data["enabled"],
        )


@dataclass
class GitHubRepoState:
    last_seen_commit: str
    last_checked_at: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any):
        return GitHubRepoState(
            last_seen_commit=data["last_seen_commit"],
            last_checked_at=data["last_checked_at"],
        )


def get_latest_github_commit(
    repository: str,
    branch: str,
) -> GitHubRepoState | None:
    """
    Return information about latest commit on a repository branch.

    Args:
        repository (str): <owner>/<repo> e.g. "microsoft/vscode"
        branch (str): name of branch e.g. "main"

    Returns:
        GitHubRepoState
    """
    repository = quote(repository, "/")
    branch = quote(branch, "/")
    url = f"https://api.github.com/repos/{repository}/commits?sha={branch}&per_page=1"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "gh-repo-watcher",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    request = Request(
        url,
        headers=headers,
        method="GET",
    )
    try:
        with urlopen(request, timeout=10) as response:
            resp = json.load(response)
    except HTTPError as error:
        print(
            f"Error while fetching latest commit for {repository}:{branch}: {error.code} {error.reason}"
        )
        return None

    if not resp or len(resp) == 0:
        print(f"Error: No commit found for {repository}:{branch}")
        return None

    commit = resp[0]
    return GitHubRepoState(
        last_seen_commit=commit["sha"],
        last_checked_at=commit["commit"]["author"]["date"],
    )


def get_is_new_and_commit(
    repository: str,
    branch: str,
    last_seen_commit: str,
) -> tuple[bool, GitHubRepoState | None]:
    latest_commit = get_latest_github_commit(repository, branch)
    if latest_commit is None:
        return False, None

    return latest_commit.last_seen_commit != last_seen_commit, latest_commit


# --- Telegram ---
def send_telegram_message(message: str) -> None:
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", None)
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", None)
    if not bot_token:
        print("TELEGRAM_BOT_TOKEN environment variable is not set.")
        return

    if not chat_id:
        print("TELEGRAM_CHAT_ID environment variable is not set.")
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = json.dumps(
        {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
    ).encode("utf-8")
    request = Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            resp = json.load(response)
        if not resp.get("ok", False):
            print("Failed to send Telegram message.")
    except Exception as _:
        print("Something went wrong here")


def construct_github_url(repo_name: str) -> str:
    return f"https://github.com/{repo_name}"


def format_repo_update_message(
    updates: dict[str, tuple[StalkedGitHubRepo, GitHubRepoState]],
) -> str:
    lines = ["Repositories with changes:"]
    for i, (repo_name, (repo, state)) in enumerate(updates.items(), start=1):
        repo_url = construct_github_url(repo_name)
        lines.append(f'{i}. <a href="{repo_url}">{escape(repo.friendly_name)}</a>')
    return "\n".join(lines)


# --- File utilities ---
def load_stalkee_json(path: Path = REPOS_JSON_PATH) -> list[StalkedGitHubRepo]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
        return [StalkedGitHubRepo.from_dict(repo) for repo in data["repositories"]]


def load_last_state_json(path: Path = STATE_JSON_PATH) -> dict[str, GitHubRepoState]:
    if not path.exists():
        return {}

    with open(path, "r", encoding="utf-8") as f:
        raw = f.read().strip()
    if not raw:
        return {}
    data = json.loads(raw)
    return {k: GitHubRepoState.from_dict(v) for k, v in data.items()}


def save_last_state_json(
    last_states: dict[str, GitHubRepoState], path: Path = STATE_JSON_PATH
) -> None:
    last_states = {name: state.to_dict() for name, state in last_states.items()}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(last_states, f, indent=2)
        f.write("\n")


def main():
    all_stalked_repos = load_stalkee_json()
    stalked_repos: list[StalkedGitHubRepo] = list(
        filter(lambda repo: repo.enabled, all_stalked_repos)
    )
    all_last_states = load_last_state_json()
    repo_names = {repo.repository for repo in stalked_repos}
    last_states = dict(
        filter(
            lambda state: state[0] in repo_names,
            all_last_states.items(),
        )
    )
    updates: dict[str, tuple[StalkedGitHubRepo, GitHubRepoState]] = {}

    for stalked_repo in stalked_repos:
        state = all_last_states.get(stalked_repo.repository, None)
        has_new_commit, newest_state = get_is_new_and_commit(
            stalked_repo.repository,
            stalked_repo.branch,
            state.last_seen_commit if state is not None else "",
        )
        if has_new_commit and newest_state is not None:
            updates[stalked_repo.repository] = (stalked_repo, newest_state)

    if updates:
        msg = format_repo_update_message(updates)
        send_telegram_message(msg)

    state_updates = {repository: state for repository, (_, state) in updates.items()}

    last_states.update(state_updates)
    save_last_state_json(last_states)


if __name__ == "__main__":
    main()
