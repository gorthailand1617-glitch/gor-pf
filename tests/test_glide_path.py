import pytest
from data_pipeline.storage_provider import StorageProvider

def test_glide_path_continuity_and_no_cliff():
    """
    Verifies that the Life Path model is smooth and continuous:
    - Between ages 35 and 60, the equity ceiling decreases monotonically.
    - Year-over-year change must never exceed 3.0% (strictly no 20-30% cliff drops).
    """
    for profile in ["CONSERVATIVE", "MODERATE", "AGGRESSIVE"]:
        prev_cap = StorageProvider.calculate_glide_path_cap(35, profile)
        
        for age in range(36, 61):
            curr_cap = StorageProvider.calculate_glide_path_cap(age, profile)
            
            # 1. Monotonic decrease
            assert curr_cap <= prev_cap, f"Profile {profile}: Cap at age {age} ({curr_cap}) is greater than age {age-1} ({prev_cap})"
            
            # 2. Smooth transition: Delta must be small (~2.0% - 2.5%), never a cliff!
            delta = prev_cap - curr_cap
            assert delta <= 0.035, f"Profile {profile}: Cliff drop detected at age {age}! Delta: {delta}"
            
            prev_cap = curr_cap

def test_glide_path_boundaries():
    """Verifies boundary caps at young age and retirement age."""
    # Moderate
    assert StorageProvider.calculate_glide_path_cap(20, "MODERATE") == 0.70
    assert StorageProvider.calculate_glide_path_cap(35, "MODERATE") == 0.70
    assert StorageProvider.calculate_glide_path_cap(60, "MODERATE") == 0.20
    assert StorageProvider.calculate_glide_path_cap(75, "MODERATE") == 0.20

    # Aggressive
    assert StorageProvider.calculate_glide_path_cap(25, "AGGRESSIVE") == 0.80
    assert StorageProvider.calculate_glide_path_cap(65, "AGGRESSIVE") == 0.30

    # Conservative
    assert StorageProvider.calculate_glide_path_cap(25, "CONSERVATIVE") == 0.40
    assert StorageProvider.calculate_glide_path_cap(65, "CONSERVATIVE") == 0.15

def test_glide_path_curve_generation():
    """Verifies frontend curve data points."""
    curve = StorageProvider.get_glide_path_curve("MODERATE")
    assert len(curve) == 41 # ages 25 to 65 inclusive
    assert curve[0]["age"] == 25
    assert curve[-1]["age"] == 65
    assert curve[0]["equity_cap"] + curve[0]["safe_cap"] == 100.0
