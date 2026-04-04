"""Tests to verify loreconvo-plugin/skills/ stays in sync with source skills.

MEG-041: The lore-onboard skill was added to ron_skills/loreconvo/skills/
but not copied to ron_skills/loreconvo-plugin/skills/. These tests catch
that class of omission by checking that new skills are properly added to
the user-facing plugin.

Background: The source skills dir has two types of skills:
- Internal/dev skills: exist only in source (e.g. 'loreconvo' was split into
  focused 'recall' + 'save' skills for the plugin). Exclusions listed below.
- User-facing skills: must exist in BOTH source and loreconvo-plugin/skills/.
  Any new skill added to source that is NOT in EXCLUDE_FROM_PLUGIN should
  also be added to loreconvo-plugin/skills/.

These tests run from the ron_skills/loreconvo/ directory but look at the
sibling loreconvo-plugin directory via relative path resolution.
"""
import os
from pathlib import Path

import pytest

# Locate the repo root (parent of ron_skills/loreconvo)
LORECONVO_DIR = Path(__file__).resolve().parent.parent
RON_SKILLS_DIR = LORECONVO_DIR.parent
PLUGIN_SKILLS_DIR = RON_SKILLS_DIR / "loreconvo-plugin" / "skills"
SOURCE_SKILLS_DIR = LORECONVO_DIR / "skills"

# Skills intentionally present in source but NOT in the user-facing plugin.
# The 'loreconvo' skill was split into focused 'recall' + 'save' skills
# for the public plugin. Document the reason when adding to this list.
EXCLUDE_FROM_PLUGIN = {
    "loreconvo",  # Dev/internal: replaced by focused 'recall' + 'save' in plugin
}


def _get_skill_names(skills_dir: Path) -> set:
    """Return the set of skill directory names in a skills directory."""
    if not skills_dir.exists():
        return set()
    return {
        entry.name
        for entry in skills_dir.iterdir()
        if entry.is_dir() and not entry.name.startswith(".")
    }


class TestPluginSkillsSync:
    """Verify loreconvo-plugin/skills/ contains all user-facing skills from source."""

    def test_plugin_skills_dir_exists(self):
        """The loreconvo-plugin skills directory must exist."""
        assert PLUGIN_SKILLS_DIR.exists(), (
            "ron_skills/loreconvo-plugin/skills/ does not exist. "
            "Create it and copy all user-facing skills from ron_skills/loreconvo/skills/."
        )

    def test_source_skills_dir_exists(self):
        """The source skills directory must exist."""
        assert SOURCE_SKILLS_DIR.exists(), (
            "ron_skills/loreconvo/skills/ not found. "
            "Test setup error."
        )

    def test_all_user_facing_source_skills_present_in_plugin(self):
        """Every non-excluded skill in the source must also exist in loreconvo-plugin.

        This is MEG-041: prevents Ron from adding a skill to the dev source
        without also adding it to the user-facing plugin.

        If a skill is intentionally dev/internal only, add it to EXCLUDE_FROM_PLUGIN
        at the top of this file (with a comment explaining why).
        """
        source_skills = _get_skill_names(SOURCE_SKILLS_DIR) - EXCLUDE_FROM_PLUGIN
        plugin_skills = _get_skill_names(PLUGIN_SKILLS_DIR)

        missing = source_skills - plugin_skills
        assert not missing, (
            "The following skill(s) are in ron_skills/loreconvo/skills/ but "
            "NOT in ron_skills/loreconvo-plugin/skills/:\n"
            + "\n".join("  - " + s for s in sorted(missing))
            + "\n\nRon must copy these skills to the user-facing plugin before release.\n"
            + "If the skill is intentionally dev-only, add it to EXCLUDE_FROM_PLUGIN in this file."
        )

    def test_each_source_skill_has_skill_md(self):
        """Every skill in the source must have a SKILL.md file."""
        if not SOURCE_SKILLS_DIR.exists():
            pytest.skip("Source skills directory does not exist")
        source_skills = _get_skill_names(SOURCE_SKILLS_DIR)
        missing_skill_md = []
        for skill_name in source_skills:
            skill_md = SOURCE_SKILLS_DIR / skill_name / "SKILL.md"
            if not skill_md.exists():
                missing_skill_md.append(skill_name)
        assert not missing_skill_md, (
            "Source skills missing SKILL.md: " + ", ".join(sorted(missing_skill_md))
        )

    def test_plugin_skills_have_skill_md(self):
        """Every skill in the plugin must have a SKILL.md file."""
        if not PLUGIN_SKILLS_DIR.exists():
            pytest.skip("Plugin skills directory does not exist")
        plugin_skills = _get_skill_names(PLUGIN_SKILLS_DIR)
        missing_skill_md = []
        for skill_name in plugin_skills:
            skill_md = PLUGIN_SKILLS_DIR / skill_name / "SKILL.md"
            if not skill_md.exists():
                missing_skill_md.append(skill_name)
        assert not missing_skill_md, (
            "Plugin skills missing SKILL.md: " + ", ".join(sorted(missing_skill_md))
        )

    def test_lore_onboard_skill_in_plugin(self):
        """Regression test for MEG-041: lore-onboard must exist in loreconvo-plugin.

        Ron built lore-onboard in dev source (9e6060f) but did not copy it
        to the user-facing plugin.
        """
        lore_onboard_plugin = PLUGIN_SKILLS_DIR / "lore-onboard"
        assert lore_onboard_plugin.exists(), (
            "ron_skills/loreconvo-plugin/skills/lore-onboard/ does not exist. "
            "MEG-041 regression: copy the skill from "
            "ron_skills/loreconvo/skills/lore-onboard/ to the plugin."
        )

    def test_exclude_list_is_accurate(self):
        """Skills in EXCLUDE_FROM_PLUGIN must actually exist in source (no stale entries)."""
        source_skills = _get_skill_names(SOURCE_SKILLS_DIR)
        stale_exclusions = EXCLUDE_FROM_PLUGIN - source_skills
        assert not stale_exclusions, (
            "EXCLUDE_FROM_PLUGIN contains skills that do not exist in source: "
            + ", ".join(sorted(stale_exclusions))
            + ". Remove stale entries from EXCLUDE_FROM_PLUGIN."
        )
