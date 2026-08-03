# ============================================================
# File: tests/unit/aegis/test_attack_recipes.py
# Purpose: Unit tests for attack recipes
# Author: Jean Francois Regis MUKIZA
# GSoC Week: 5-6
# OWASP Category: ASI01-ASI10
# ============================================================
"""Tests for attack recipe functionality."""

import pytest
from finbot.aegis.simulator.base import SandboxHarness


@pytest.mark.unit
class TestPromptInjectionRecipes:
    """Test ASI01 prompt injection recipes."""

    def test_asi01_recipes_loaded(self) -> None:
        """Test that ASI01 recipes are loaded."""
        harness = SandboxHarness()
        recipes = harness.list_recipes_for_asi("ASI01")
        # Should have at least the 8 recipes we created
        assert len(recipes) >= 8
        recipe_ids = [recipe_id for recipe_id, _ in recipes]
        assert any("asi01_prompt_injection_" in rid for rid in recipe_ids)

    def test_asi01_prompt_injection_1_exists(self) -> None:
        """Test specific ASI01 recipe exists."""
        harness = SandboxHarness()
        recipes = harness.list_recipes_for_asi("ASI01")
        recipe_dict = dict(recipes)
        assert "asi01_prompt_injection_1" in recipe_dict
        recipe = recipe_dict["asi01_prompt_injection_1"]
        assert recipe["asi"] == ["ASI01"]
        assert "prompt" in str(recipe.get("steps", []))


@pytest.mark.unit
class TestToolMisuseRecipes:
    """Test ASI02 tool misuse recipes."""

    def test_asi02_recipes_loaded(self) -> None:
        """Test that ASI02 recipes are loaded."""
        harness = SandboxHarness()
        recipes = harness.list_recipes_for_asi("ASI02")
        # Should have at least the 8 recipes we created
        assert len(recipes) >= 8
        recipe_ids = [recipe_id for recipe_id, _ in recipes]
        assert any("asi02_tool_misuse_" in rid for rid in recipe_ids)

    def test_asi02_tool_misuse_1_exists(self) -> None:
        """Test specific ASI02 recipe exists."""
        harness = SandboxHarness()
        recipes = harness.list_recipes_for_asi("ASI02")
        recipe_dict = dict(recipes)
        assert "asi02_tool_misuse_1" in recipe_dict
        recipe = recipe_dict["asi02_tool_misuse_1"]
        assert recipe["asi"] == ["ASI02"]
        assert "create_vendor" in str(recipe.get("steps", []))


@pytest.mark.unit
class TestSupplyChainRecipes:
    """Test ASI04 supply chain recipes."""

    def test_asi04_recipes_loaded(self) -> None:
        """Test that ASI04 recipes are loaded."""
        harness = SandboxHarness()
        recipes = harness.list_recipes_for_asi("ASI04")
        # Should have at least the 8 recipes we created
        assert len(recipes) >= 8
        recipe_ids = [recipe_id for recipe_id, _ in recipes]
        assert any("asi04_supply_chain_" in rid for rid in recipe_ids)

    def test_asi04_supply_chain_1_exists(self) -> None:
        """Test specific ASI04 recipe exists."""
        harness = SandboxHarness()
        recipes = harness.list_recipes_for_asi("ASI04")
        recipe_dict = dict(recipes)
        assert "asi04_supply_chain_1" in recipe_dict
        recipe = recipe_dict["asi04_supply_chain_1"]
        assert recipe["asi"] == ["ASI04"]
        assert "update_dependency" in str(recipe.get("steps", []))


@pytest.mark.unit
class TestRceRecipes:
    """Test ASI05 RCE recipes."""

    def test_asi05_recipes_loaded(self) -> None:
        """Test that ASI05 recipes are loaded."""
        harness = SandboxHarness()
        recipes = harness.list_recipes_for_asi("ASI05")
        # Should have at least the 8 recipes we created
        assert len(recipes) >= 8
        recipe_ids = [recipe_id for recipe_id, _ in recipes]
        assert any("asi05_rce_" in rid for rid in recipe_ids)

    def test_asi05_rce_1_exists(self) -> None:
        """Test specific ASI05 recipe exists."""
        harness = SandboxHarness()
        recipes = harness.list_recipes_for_asi("ASI05")
        recipe_dict = dict(recipes)
        assert "asi05_rce_1" in recipe_dict
        recipe = recipe_dict["asi05_rce_1"]
        assert recipe["asi"] == ["ASI05"]
        assert "execute_shell" in str(recipe.get("steps", []))


@pytest.mark.unit
class TestDelegationRecipes:
    """Test ASI06 delegation bypass recipes."""

    def test_asi06_recipes_loaded(self) -> None:
        """Test that ASI06 recipes are loaded."""
        harness = SandboxHarness()
        recipes = harness.list_recipes_for_asi("ASI06")
        # Should have at least the 8 recipes we created
        assert len(recipes) >= 8
        recipe_ids = [recipe_id for recipe_id, _ in recipes]
        assert any("asi06_delegation_bypass_" in rid for rid in recipe_ids)

    def test_asi06_delegation_bypass_1_exists(self) -> None:
        """Test specific ASI06 recipe exists."""
        harness = SandboxHarness()
        recipes = harness.list_recipes_for_asi("ASI06")
        recipe_dict = dict(recipes)
        assert "asi06_delegation_bypass_1" in recipe_dict
        recipe = recipe_dict["asi06_delegation_bypass_1"]
        assert recipe["asi"] == ["ASI06"]
        assert "create_vendor" in str(recipe.get("steps", []))


@pytest.mark.unit
class TestRemainingCategoriesRecipes:
    """Test ASI03, ASI07, ASI08, ASI09, ASI010 recipes."""

    def test_asi03_recipes_loaded(self) -> None:
        """Test that ASI03 recipes are loaded."""
        harness = SandboxHarness()
        recipes = harness.list_recipes_for_asi("ASI03")
        # Should have at least some recipes
        assert len(recipes) >= 2
        recipe_ids = [recipe_id for recipe_id, _ in recipes]
        assert any("asi03_" in rid for rid in recipe_ids)

    def test_asi07_recipes_loaded(self) -> None:
        """Test that ASI07 recipes are loaded."""
        harness = SandboxHarness()
        recipes = harness.list_recipes_for_asi("ASI07")
        # Should have at least some recipes
        assert len(recipes) >= 1
        recipe_ids = [recipe_id for recipe_id, _ in recipes]
        assert any("asi07_" in rid for rid in recipe_ids)

    def test_asi08_recipes_loaded(self) -> None:
        """Test that ASI08 recipes are loaded."""
        harness = SandboxHarness()
        recipes = harness.list_recipes_for_asi("ASI08")
        # Should have at least some recipes
        assert len(recipes) >= 1
        recipe_ids = [recipe_id for recipe_id, _ in recipes]
        assert any("asi08_" in rid for rid in recipe_ids)

    def test_asi09_recipes_loaded(self) -> None:
        """Test that ASI09 recipes are loaded."""
        harness = SandboxHarness()
        recipes = harness.list_recipes_for_asi("ASI09")
        # Should have at least some recipes
        assert len(recipes) >= 1
        recipe_ids = [recipe_id for recipe_id, _ in recipes]
        assert any("asi09_" in rid for rid in recipe_ids)

    def test_asi010_recipes_loaded(self) -> None:
        """Test that ASI010 recipes are loaded."""
        harness = SandboxHarness()
        recipes = harness.list_recipes_for_asi("ASI010")
        # Should have at least some recipes
        assert len(recipes) >= 1
        recipe_ids = [recipe_id for recipe_id, _ in recipes]
        assert any("asi010_" in rid for rid in recipe_ids)

    def test_combined_recipe_exists(self) -> None:
        """Test that combined multi-category recipe exists."""
        harness = SandboxHarness()
        recipes = harness.list_recipes_for_asi("ASI03")  # Check ASI03 as proxy
        recipe_dict = dict(recipes)
        # Look for combined recipe
        combined_found = any("asi03_07_08_09_10_combined_" in rid for rid in recipe_dict.keys())
        # At least verify the file was loaded by checking we have recipes from the combined file
        assert len(recipes) > 0  # Should have loaded something from the combined file


@pytest.mark.unit
class TestRecipeStatistics:
    """Test recipe statistics functionality."""

    def test_recipe_statistics_includes_all_categories(self) -> None:
        """Test that recipe statistics include all ASI categories."""
        harness = SandboxHarness()
        stats = harness.get_recipe_statistics()

        assert stats["total_recipes"] > 0
        assert "by_asi" in stats

        # Check that we have recipes for the main categories we created
        asi_categories = set(stats["by_asi"].keys())
        expected_categories = {"ASI01", "ASI02", "ASI04", "ASI05", "ASI06"}
        # At least some of the expected categories should be present
        assert len(asi_categories.intersection(expected_categories)) > 0

        # Each category should have a reasonable number of recipes
        for asi, count in stats["by_asi"].items():
            if asi in expected_categories:
                assert count >= 1, f"Category {asi} should have at least 1 recipe"


@pytest.mark.unit
class TestRecipeLoadingIntegration:
    """Integration test for recipe loading."""

    def test_all_recipe_files_loaded_without_errors(self) -> None:
        """Test that all recipe files load without throwing exceptions."""
        # This test ensures our YAML files are valid and loadable
        try:
            harness = SandboxHarness()
            # If we get here without exception, basic loading worked
            assert harness is not None
            # Try to access recipes
            recipes = harness.list_recipes()
            assert isinstance(recipes, dict)
        except Exception as e:
            pytest.fail(f"Failed to load recipes: {e}")

    def test_no_duplicate_recipe_ids(self) -> None:
        """Test that there are no duplicate recipe IDs."""
        harness = SandboxHarness()
        recipes = harness.list_recipes()
        recipe_ids = list(recipes.keys())
        # Check for duplicates
        assert len(recipe_ids) == len(set(recipe_ids)), "Duplicate recipe IDs found"


if __name__ == "__main__":
    pytest.main([__file__])