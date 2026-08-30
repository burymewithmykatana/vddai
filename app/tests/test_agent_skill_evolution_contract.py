from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = REPOSITORY_ROOT / ".agents" / "skills"
LIFECYCLE_SKILLS = (
    "vddai-plan",
    "vddai-code",
    "vddai-review",
    "vddai-qa",
    "vddai-documentation",
)
PROCESS_FIELDS = (
    "`Observation`",
    "`Evidence`",
    "`Impact`",
    "`Recurrence`",
    "`Candidate improvement`",
    "`Authority note`",
)


def _skill_text(name: str) -> str:
    return (SKILLS_ROOT / name / "SKILL.md").read_text(encoding="utf-8")


def test_every_lifecycle_report_has_process_learning_evidence() -> None:
    for skill_name in LIFECYCLE_SKILLS:
        skill = _skill_text(skill_name)

        assert "## Append process-learning evidence" in skill
        assert "`## Process-learning evidence`" in skill
        for field in PROCESS_FIELDS:
            assert field in skill
        assert "does not authorize a skill or" in skill


def test_coder_report_has_detailed_bounded_process_telemetry() -> None:
    coder = _skill_text("vddai-code")

    assert "`## Coder process telemetry`" in coder
    assert "planned files and sequence compared with actual" in coder
    assert "elapsed duration when available" in coder
    assert "retry count" in coder
    assert "human gates and manual interventions" in coder
    assert "Use `not recorded` when a value is unavailable" in coder
    assert "not authorization, agent scoring, or an approval criterion" in coder


def test_skill_evolution_is_human_invoked_read_only_and_proposal_only() -> None:
    evolution = _skill_text("vddai-skill-evolution")

    assert "explicit human invocation" in evolution
    assert "Keep the repository read-only" in evolution
    assert "Do not write a Coder handoff" in evolution
    assert "invoke this skill recursively" in evolution
    assert "edit this skill, another skill" in evolution
    assert "invoke `$vddai-plan`" in evolution
    assert (
        "proposal -> Planner -> human plan approval -> Coder -> Reviewer -> QA -> "
        "Documentation -> human merge approval"
    ) in evolution


def test_repository_contract_requires_independent_skill_change_lifecycle() -> None:
    agents = (REPOSITORY_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    workflow = (
        REPOSITORY_ROOT / "docs" / "engineering" / "agent-workflow.md"
    ).read_text(encoding="utf-8")

    assert "## Agent Skill Evolution" in agents
    assert "No agent may autonomously modify the skill" in agents
    assert "independent `$vddai-plan` handoff" in agents
    assert "## Process-Learning Loop" in workflow
    assert "proposal only" in workflow
    assert "No role may use its own report" in workflow
    assert "## Process-Learning Evidence" in workflow


def test_skill_evolution_package_has_codex_interface_metadata() -> None:
    metadata = SKILLS_ROOT / "vddai-skill-evolution" / "agents" / "openai.yaml"

    assert metadata.is_file()
    text = metadata.read_text(encoding="utf-8")
    assert 'display_name: "VDDAI Skill Evolution"' in text
    assert "$vddai-skill-evolution" in text
