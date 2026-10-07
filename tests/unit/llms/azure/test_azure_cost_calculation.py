"""
Test Azure OpenAI cost calculator — service_tier pricing.
"""

from typing import Final, Literal, cast

import pytest

import litellm
from litellm.llms.azure.cost_calculation import cost_per_token
from litellm.litellm_core_utils.get_model_cost_map import GetModelCostMap
from litellm.types.utils import ModelInfo, ModelResponse, Usage


# Register a test model with tier-specific pricing
TEST_MODEL = "test-azure-gpt-4.1"
TEST_MODEL_COST = {
    TEST_MODEL: {
        "input_cost_per_token": 0.001,
        "output_cost_per_token": 0.002,
        "input_cost_per_token_priority": 0.01,
        "output_cost_per_token_priority": 0.02,
        "input_cost_per_token_flex": 0.0005,
        "output_cost_per_token_flex": 0.001,
        "litellm_provider": "azure",
        "max_tokens": 8192,
    }
}


class TestAzureServiceTierCostCalculation:
    """Test that service_tier is passed through Azure cost calculation."""

    @pytest.fixture(autouse=True)
    def register_test_model(self):
        litellm.register_model(model_cost=TEST_MODEL_COST)

    def test_service_tier_priority_higher_cost(self):
        """Priority tier should cost more than standard."""
        usage = Usage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)

        standard_prompt, standard_completion = cost_per_token(
            model=TEST_MODEL, usage=usage
        )
        priority_prompt, priority_completion = cost_per_token(
            model=TEST_MODEL, usage=usage, service_tier="priority"
        )

        assert priority_prompt > standard_prompt
        assert priority_completion > standard_completion

    def test_service_tier_flex_lower_cost(self):
        """Flex tier should cost less than standard."""
        usage = Usage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)

        standard_prompt, standard_completion = cost_per_token(
            model=TEST_MODEL, usage=usage
        )
        flex_prompt, flex_completion = cost_per_token(
            model=TEST_MODEL, usage=usage, service_tier="flex"
        )

        assert flex_prompt < standard_prompt
        assert flex_completion < standard_completion

    def test_service_tier_none_returns_standard(self):
        """service_tier=None should return standard pricing."""
        usage = Usage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)

        none_prompt, none_completion = cost_per_token(
            model=TEST_MODEL, usage=usage, service_tier=None
        )
        standard_prompt, standard_completion = cost_per_token(
            model=TEST_MODEL, usage=usage, service_tier="standard"
        )

        assert abs(none_prompt - standard_prompt) < 1e-10
        assert abs(none_completion - standard_completion) < 1e-10


@pytest.fixture
def local_azure_prices(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    monkeypatch.setattr(litellm, "model_cost", GetModelCostMap.load_local_model_cost_map())


@pytest.mark.parametrize(
    "model_name", ["gpt-5.5", "gpt-5.6-sol", "gpt-6-astra", "gpt-6.1-sol", "gpt-6-sol", "gpt-6-luna"]
)
@pytest.mark.parametrize("provider_prefix", ["", "azure/"])
@pytest.mark.parametrize("threshold_offset", [-1, 0, 1])
@pytest.mark.parametrize("use_cache", [False, True])
@pytest.mark.parametrize("calculator", ["token", "completion"])
def test_us_gpt_region_accounts_for_cache_and_context_tiers(
    local_azure_prices: None,
    model_name: str,
    provider_prefix: str,
    threshold_offset: int,
    use_cache: bool,
    calculator: Literal["token", "completion"],
) -> None:
    model: Final = f"{provider_prefix}{model_name}"
    prices: Final = cast(ModelInfo, litellm.model_cost[f"azure/us/{model_name}"])
    threshold_key: Final = next(key for key in prices if key.startswith("input_cost_per_token_above_"))
    threshold_label: Final = threshold_key.removeprefix("input_cost_per_token_above_").removesuffix("_tokens")
    threshold: Final = int(threshold_label.removesuffix("k")) * (1000 if threshold_label.endswith("k") else 1)
    rate_suffix: Final = f"_above_{threshold_label}_tokens" if threshold_offset > 0 else ""
    cache_read_tokens: Final = 101 if use_cache else 0
    cache_write_tokens: Final = 53 if use_cache and "cache_creation_input_token_cost" in prices else 0
    input_tokens: Final = threshold + threshold_offset
    output_tokens: Final = 37
    uncached_tokens: Final = input_tokens - cache_read_tokens - cache_write_tokens
    usage: Final = Usage(
        prompt_tokens=input_tokens,
        completion_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        cache_read_input_tokens=cache_read_tokens,
        cache_creation_input_tokens=cache_write_tokens,
    )
    expected_input: Final = (
        uncached_tokens * cast(float, prices[f"input_cost_per_token{rate_suffix}"])
        + cache_read_tokens * cast(float, prices[f"cache_read_input_token_cost{rate_suffix}"])
        + cache_write_tokens * cast(float, prices.get(f"cache_creation_input_token_cost{rate_suffix}", 0))
    )
    expected_output: Final = output_tokens * cast(float, prices[f"output_cost_per_token{rate_suffix}"])

    if calculator == "token":
        input_cost, output_cost = litellm.cost_per_token(
            model=model,
            custom_llm_provider="azure",
            region_name="us",
            usage_object=usage,
        )
        assert input_cost == pytest.approx(expected_input)
        assert output_cost == pytest.approx(expected_output)
        assert input_cost > 0 and output_cost > 0
        return

    response: Final = ModelResponse(model=model_name, choices=[], usage=usage)
    total_cost: Final = litellm.completion_cost(
        model=model,
        custom_llm_provider="azure",
        region_name="us",
        completion_response=response,
    )
    assert total_cost == pytest.approx(expected_input + expected_output)
    assert total_cost > 0
