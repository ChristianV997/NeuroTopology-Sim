from tools.integration_repair.fixture_audit import audit_refs


def test_fixture_audit_reports_missing_refs_without_synthesizing_them(tmp_path):
    import subprocess

    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    (tmp_path / "README.md").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "README.md"], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "-c", "user.name=tests", "-c",
         "user.email=tests@example.invalid", "commit", "-q", "-m", "fixture"],
        check=True,
    )

    result = audit_refs(tmp_path, ["refs/heads/missing", "refs/heads/main"])

    assert [item["ref"] for item in result] == [
        "refs/heads/main",
        "refs/heads/missing",
    ]
    assert result[0]["classification"] == "available"
    assert result[0]["present"] is True
    assert result[1]["classification"] == "fixture_inconsistency"
    assert result[1]["present"] is False
    assert result[1]["commit"] is None
