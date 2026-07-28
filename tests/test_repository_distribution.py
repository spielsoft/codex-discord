import json
import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MARKETPLACE_FILE = (
    REPOSITORY_ROOT / ".agents" / "plugins" / "marketplace.json"
)
PLUGIN_ROOT = REPOSITORY_ROOT / "plugins" / "codex-discord"


class RepositoryDistributionTests(unittest.TestCase):
    def test_repo_marketplace_exposes_the_packaged_plugin(self):
        marketplace = json.loads(MARKETPLACE_FILE.read_text())

        self.assertEqual(marketplace["name"], "codex-discord")
        self.assertEqual(
            marketplace["interface"]["displayName"],
            "Codex Discord",
        )
        self.assertEqual(len(marketplace["plugins"]), 1)
        entry = marketplace["plugins"][0]
        self.assertEqual(entry["name"], "codex-discord")
        self.assertEqual(
            entry["source"],
            {
                "source": "local",
                "path": "./plugins/codex-discord",
            },
        )
        self.assertEqual(entry["policy"]["installation"], "AVAILABLE")
        self.assertEqual(entry["policy"]["authentication"], "ON_INSTALL")
        self.assertEqual(entry["category"], "Communication")
        self.assertTrue((PLUGIN_ROOT / ".codex-plugin" / "plugin.json").is_file())

    def test_public_readme_leads_with_install_and_first_run(self):
        readme = (REPOSITORY_ROOT / "README.md").read_text()

        self.assertLess(readme.index("## Install"), readme.index("## Development"))
        self.assertIn(
            "codex plugin marketplace add SpielSoft/codex-discord",
            readme,
        )
        self.assertIn("codex plugin add codex-discord@codex-discord", readme)
        self.assertIn("Set up Codex Discord notifications", readme)
        self.assertIn("does not require a pre-existing forum post", readme)

    def test_github_ci_and_community_guidance_are_present(self):
        workflow = (
            REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
        ).read_text()

        self.assertIn("python3 -m unittest discover -s tests -v", workflow)
        self.assertIn(
            "python3 -m json.tool "
            "plugins/codex-discord/.codex-plugin/plugin.json",
            workflow,
        )
        self.assertIn("diff -ru --exclude=__pycache__", workflow)
        self.assertTrue((REPOSITORY_ROOT / "CONTRIBUTING.md").is_file())
        self.assertTrue((REPOSITORY_ROOT / "SECURITY.md").is_file())

    def test_local_documentation_links_resolve(self):
        documents = [
            REPOSITORY_ROOT / "README.md",
            REPOSITORY_ROOT / "CONTRIBUTING.md",
            REPOSITORY_ROOT / "SECURITY.md",
            *sorted((REPOSITORY_ROOT / "docs").glob("*.md")),
            PLUGIN_ROOT / "README.md",
        ]

        for document in documents:
            for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", document.read_text()):
                if "://" in target or target.startswith(("#", "mailto:")):
                    continue
                path = target.split("#", 1)[0]
                with self.subTest(document=document.name, target=target):
                    self.assertTrue((document.parent / path).resolve().exists())


if __name__ == "__main__":
    unittest.main()
