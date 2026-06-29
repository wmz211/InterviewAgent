from pathlib import Path

from app.core.reusable_materials import (
    get_reuse_options,
    get_reusable_jd,
    get_reusable_resume,
    save_reusable_materials,
)


def test_reusable_materials_are_saved_and_deduped_by_latest(tmp_path: Path):
    store_path = tmp_path / "materials.json"

    save_reusable_materials(
        user_id=7,
        session_id="old",
        candidate_name="Alice",
        resume_summary="same resume",
        jd_text="same jd",
        store_path=store_path,
    )
    save_reusable_materials(
        user_id=7,
        session_id="new",
        candidate_name="Alice New",
        resume_summary="same resume",
        jd_text="same jd",
        store_path=store_path,
    )

    options = get_reuse_options(7, store_path=store_path, sessions_dir=tmp_path / "sessions")

    assert [r["session_id"] for r in options["resumes"]] == ["new"]
    assert [j["session_id"] for j in options["jds"]] == ["new"]
    assert options["jds"][0]["jd_preview"] == "same jd"


def test_reusable_material_lookup_is_scoped_to_user(tmp_path: Path):
    store_path = tmp_path / "materials.json"
    save_reusable_materials(1, "s1", "Alice", "resume 1", "jd 1", store_path=store_path)
    save_reusable_materials(2, "s2", "Bob", "resume 2", "jd 2", store_path=store_path)

    assert get_reusable_resume(1, "s1", store_path=store_path)["resume_summary"] == "resume 1"
    assert get_reusable_resume(1, "s2", store_path=store_path) is None
    assert get_reusable_jd(2, "s2", store_path=store_path)["jd_text"] == "jd 2"
