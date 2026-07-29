# Publishing checklist

The repository uses the canonical repo-marketplace layout and is configured
for publication at `https://github.com/SpielSoft/codex-discord`. The manifest
identifies SpielSoft as the publisher, provides the developer contact
`spielman@spielsoft.com`, and declares the MIT license.

Before announcing the public GitHub release:

1. Create the `SpielSoft/codex-discord` GitHub repository and push `main`.
2. Verify the Python 3.9 and 3.12 GitHub Actions jobs.
3. Push a `v0.4.0` tag matching the manifest version.
4. Install from `SpielSoft/codex-discord` in a clean Codex profile and run the
   opt-in forum create/update smoke.
5. Decide whether public distribution needs hosted privacy-policy and
   terms-of-service URLs. The plugin sends user-requested message content,
   selected Codex task summaries, and project-directory names to the
   user-configured Discord webhook.
6. Add final icon, logo, and screenshot assets if the target directory or
   submission flow expects richer listing media.

Public universal-directory submission is separate from publishing a GitHub
repo marketplace. Follow the current OpenAI plugin submission process after
the GitHub package and legal metadata are final.
