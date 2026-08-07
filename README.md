# gh-repo-stalker

This project uses GitHub actions to monitor "stalked" GitHub public repos of interest in a file called stalked.json. If there is a new commit, then the telegram bot will message the owner.

Bot token and owner telegram ID should be set up via GitHub secrets instead.

```
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

The project directory structure has the following:

- config/repositories.json
- state/last-seen.json
- src/stalker.py

The repositories.json file is user-supplied and contains the list of repositories you are interested in. The schema is as follows:

```json
{
  "repositories": [
    {
      "name": "vscode",
      "repository": "microsoft/vscode",
      "branch": "main",
      "enabled": true
    },
    {
      "name": "cpython",
      "repository": "python/cpython",
      "branch": "main",
      "enabled": true
    },
  ]
}
```

Adding a new repo is then as simple as adding a new entry. An entry with missing/incorrect schema will throw an error. Observe that there is both a `name` and `repository` schema entry. `name` is your own custom name/alias, whatever helps you remember the repo eaasier while `repository` is the official GitHub repo.

The last-seen.json file is updated per github actions workflow (if there is a change). (The project abuses GitHub-as-infra/database.) The schema is as follows:

```json
{
  "repositories": {
    "microsoft/vscode": {
      "last_seen_commit": "0123456789abcdef0123456789abcdef01234567",
      "last_checked_at": "2026-08-07T04:15:32Z"
    },
    "python/cpython": {
      "last_seen_commit": "abcdef0123456789abcdef0123456789abcdef01",
      "last_checked_at": "2026-08-07T04:15:35Z"
    }
  }
}
```