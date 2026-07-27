# Publishing checklist

The repository already uses the canonical repo-marketplace layout and can be
installed from a local clone or Git-backed marketplace source.

Before publishing it as a public GitHub project:

1. Choose a repository owner and URL.
2. Choose an open-source or source-available license. Do not add one without
   the repository owner's explicit decision.
3. Add the final repository, homepage, publisher contact, and license fields to
   `plugins/codex-discord/.codex-plugin/plugin.json`.
4. Decide whether public distribution needs hosted privacy-policy and
   terms-of-service URLs. The plugin sends selected Codex task summaries and
   project-directory names to the user-configured Discord webhook.
5. Replace `owner/repository` in installation examples with the published
   GitHub shorthand.
6. Add final icon, logo, and screenshot assets if the target directory or
   submission flow expects richer listing media.
7. Push a version tag matching the manifest version and verify GitHub Actions.
8. Install from the GitHub marketplace source in a clean Codex profile and run
   the opt-in forum create/update smoke.

Public universal-directory submission is separate from publishing a GitHub
repo marketplace. Follow the current OpenAI plugin submission process after
the GitHub package and legal metadata are final.
